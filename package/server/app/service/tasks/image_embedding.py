import logging
import os
import aiohttp
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType
from app.db.models.image_vector import ImageVector
from typing import Dict, Any, List
from app.core.config_manager import config_manager
from app.service import storage

logger = logging.getLogger(__name__)

async def handle_image_embedding(task_manager, task: Task, db: Session) -> Dict[str, Any]:
    try:
        force = task.payload.get('force', False)
        
        if task.payload and 'photo_id' in task.payload:
            photo_id = task.payload['photo_id']
            photo = db.query(Photo).filter(Photo.id == photo_id).first()
            if not photo:
                return {'status': 'skipped', 'reason': 'photo not found'}
            
            if not force:
                tasks_status = photo.processed_tasks or {}
                if tasks_status.get('image_embedding'):
                     return {'status': 'skipped', 'reason': 'already processed'}

            return await process_single_photo(task_manager, photo, db)

        # Generator Mode
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
                    if not tasks_status.get('image_embedding'):
                        should_process = True
                
                if should_process:
                    tasks_to_create.append({
                        'type': TaskType.IMAGE_EMBEDDING,
                        'payload': {'photo_id': str(p.id), 'force': force},
                        'priority': 3,
                        'owner_id': p.owner_id
                    })

            if tasks_to_create:
                task_manager.add_tasks(db, tasks_to_create)
                generated_count += len(tasks_to_create)

            offset += batch_size

        return {
            'processed': 0,
            'generated_tasks': generated_count,
            'message': f'Generated {generated_count} image embedding tasks'
        }

    except Exception as e:
        logger.error(f"Image embedding task failed: {e}")
        raise e

async def process_single_photo(task_manager, photo: Photo, db: Session) -> Dict[str, Any]:
    try:
        target_path = storage.get_preview_path(photo.owner_id, photo.id)
        if not os.path.exists(target_path):
            target_path = photo.file_path
            if not target_path or not os.path.exists(target_path):
                return {'status': 'failed', 'error': 'file not found'}

        async with aiohttp.ClientSession() as session:
            with open(target_path, 'rb') as f:
                file_data = f.read()

            import base64
            b64_data = base64.b64encode(file_data).decode('utf-8')
            json_data = {"images": [b64_data]}

            api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/embedding/image"
            async with session.post(api_url, json=json_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    # Response is List[List[float]]
                    if result and len(result) > 0:
                        embedding = result[0]
                        
                        # Save Embedding
                        vector = db.query(ImageVector).filter(ImageVector.photo_id == photo.id).first()
                        if not vector:
                            vector = ImageVector(photo_id=photo.id)
                            db.add(vector)
                        vector.embedding = embedding

                        tasks_status = dict(photo.processed_tasks or {})
                        tasks_status['image_embedding'] = True
                        photo.processed_tasks = tasks_status
                        db.add(photo)
                        db.commit()
                        return {'status': 'success', 'embedding_size': len(embedding)}
                    else:
                        return {'status': 'failed', 'error': 'No embedding returned'}
                else:
                    text = await resp.text()
                    logger.error(f"AI Service error: {resp.status} {text}")
                    return {'status': 'failed', 'error': f"AI Service error: {resp.status}"}
    except Exception as e:
        logger.error(f"Error processing Image Embedding for photo {photo.id}: {e}")
        tasks_status = dict(photo.processed_tasks or {})
        tasks_status['image_embedding'] = False
        photo.processed_tasks = tasks_status
        db.add(photo)
        db.commit()
        raise e

def release_resources():
    pass
