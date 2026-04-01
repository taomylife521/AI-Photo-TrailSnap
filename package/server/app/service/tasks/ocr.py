import logging
import os
import aiohttp
from aiohttp import FormData
import json
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType
from app.db.models.ocr import OCR
from typing import Dict, Any, List
from app.crud import ocr as crud_ocr
from app.core.config_manager import config_manager
from PIL import Image

from app.schemas.ocr import OCRCreate

logger = logging.getLogger(__name__)

async def handle_ocr_task(task_manager, task: Task, db: Session) -> Dict[str, Any]:
    """
    Handle OCR task
    """
    try:
        force = task.payload.get('force', False)
        
        # 1. Single Photo Mode
        if task.payload and 'photo_id' in task.payload:
            photo_id = task.payload['photo_id']
            photo = db.query(Photo).filter(Photo.id == photo_id).first()
            if not photo:
                return {'status': 'skipped', 'reason': 'photo not found'}
            
            # Check if already processed (unless force)
            if not force:
                tasks_status = photo.processed_tasks or {}
                if tasks_status.get('ocr'):
                     return {'status': 'skipped', 'reason': 'already processed'}

            return await process_single_photo(task_manager, photo, db)

        # 2. Generator Mode (Scan all)
        photos_to_process = []
        batch_size = 1000
        offset = 0
        
        generated_count = 0
        
        while True:
            batch = db.query(Photo).offset(offset).limit(batch_size).all()
            if not batch:
                break

            tasks_to_create = []
            for p in batch:
                if p.file_type == FileType.video:
                    continue
                
                should_process = False
                if force:
                    should_process = True
                else:
                    tasks_status = p.processed_tasks or {}
                    if not tasks_status.get('ocr'):
                        should_process = True
                
                if should_process:
                    tasks_to_create.append({
                        'type': TaskType.OCR,
                        'payload': {'photo_id': str(p.id), 'force': force},
                        'priority': 1,
                        'owner_id': p.owner_id
                    })

            if tasks_to_create:
                task_manager.add_tasks(db, tasks_to_create)
                generated_count += len(tasks_to_create)

            offset += batch_size

        return {
            'processed': 0,
            'generated_tasks': generated_count,
            'message': f'Generated {generated_count} OCR tasks'
        }

    except Exception as e:
        logger.error(f"OCR task failed: {e}")
        raise e

async def process_single_photo(task_manager, photo: Photo, db: Session) -> Dict[str, Any]:
    from app.service import storage

    try:
        # 1. Resolve file path
        # Prefer original file for OCR to get best quality
        target_path = storage.get_preview_path(photo.owner_id, photo.id)
        if not os.path.exists(target_path):
            # Fallback to preview if original not available (unlikely for local)
            target_path = photo.file_path
            if not target_path or not os.path.exists(target_path):
                return {'status': 'failed', 'error': 'file not found'}

        # 读取图片实际宽高
        with Image.open(target_path) as img:
            width, height = img.size

        async with aiohttp.ClientSession() as session:
            # 1. Read file
            with open(target_path, 'rb') as f:
                file_data = f.read()

            form_data = FormData()
            form_data.add_field(
                name='file',
                value=file_data,
                filename=photo.filename,
                content_type='image/jpeg'
            )

            # 3. Call AI Service
            # Assuming AI service has /ocr/predict endpoint
            api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/ocr/predict"
            async with session.post(
                api_url,
                data=form_data,
                timeout=aiohttp.ClientTimeout(total=60) # OCR might be slow
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    # Response structure:
                    # {
                    #   "dataInfo": ...,
                    #   "ocrResults": {
                    #     "prunedResult": {
                    #       "rec_texts": [...],
                    #       "rec_scores": [...],
                    #       "rec_polys": [[[x,y],...], ...]
                    #     }
                    #   }
                    # }
                    ocr_results = result.get('ocrResults', [])
                    if ocr_results:
                        ocr_results = ocr_results[0]  # Assuming single image per request
                    else:
                        ocr_results = {}
                    pruned_result = ocr_results.get('prunedResult', {})
                    rec_texts = pruned_result.get('rec_texts', [])
                    rec_scores = pruned_result.get('rec_scores', [])
                    rec_polys = pruned_result.get('rec_polys', [])

                    # Clean up old OCR results for this photo
                    crud_ocr.delete_ocr_by_photo_id(db, photo.id)

                    count = 0

                    for i, text in enumerate(rec_texts):
                        score = rec_scores[i] if i < len(rec_scores) else 0.0
                        poly = rec_polys[i] if i < len(rec_polys) else []
                        # Normalize polygon
                        norm_poly = []
                        if width and height and width > 0 and height > 0:
                            for point in poly:
                                norm_poly.append([
                                    point[0] / width,
                                    point[1] / height
                                ])
                        else:
                            # If no dimensions, store absolute or 0?
                            # User requested relative coordinates.
                            # We'll skip normalization if dimensions are missing,
                            # but frontend might expect 0-1.
                            # Let's hope dimensions are there.
                            norm_poly = poly

                        ocr_record = crud_ocr.create_ocr(
                            db,
                            OCRCreate(
                                photo_id=photo.id,
                                text=text,
                                text_score=score,
                                polygon=norm_poly
                            )
                        )
                        count += 1

                    # Update Status
                    tasks_status = dict(photo.processed_tasks or {})
                    tasks_status['ocr'] = True
                    photo.processed_tasks = tasks_status
                    db.add(photo)
                    db.commit()
                    # Use a separate counter or just log
                    # task_manager.scan_status['processed_files'] += 1
                    return {'status': 'success', 'texts_found': count}
                else:
                    return {'status': 'failed', 'error': f"AI Service error: {resp.status}"}
    except Exception as e:
        logger.error(f"Error processing OCR for photo {photo.id}: {e}")
        tasks_status = dict(photo.processed_tasks or {})
        tasks_status['ocr'] = False
        photo.processed_tasks = tasks_status
        db.add(photo)
        db.commit()
        raise e

def release_resources():
    pass