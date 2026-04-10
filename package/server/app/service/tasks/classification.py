from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import logging
import os
import aiohttp
from aiohttp import FormData
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.image_vector import ImageVector
from typing import Dict, Any, List
from app.core.config_manager import config_manager
from app.crud import tag as crud_tag

from app.service import storage

logger = logging.getLogger(__name__)

@TaskStrategyFactory.register(TaskType.CLASSIFY_IMAGE)
class ClassifyImageStrategy(BaseTaskStrategy):
    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        try:
            force = task.payload.get('force', False)
            
            if task.payload and 'photo_id' in task.payload:
                photo_id = task.payload['photo_id']
                photo = db.query(Photo).filter(Photo.id == photo_id).first()
                if not photo:
                    return {'status': 'skipped', 'reason': 'photo not found'}
                
                if not force:
                    tasks_status = photo.processed_tasks or {}
                    if tasks_status.get('classification'):
                         return {'status': 'skipped', 'reason': 'already processed'}

                return await self.process_single_photo(worker, photo, db)

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
                    should_process = False
                    if force:
                        should_process = True
                    else:
                        tasks_status = p.processed_tasks or {}
                        if not tasks_status.get('classification'):
                            should_process = True
                    
                    if should_process:
                        tasks_to_create.append({
                            'type': TaskType.CLASSIFY_IMAGE,
                            'payload': {'photo_id': str(p.id), 'force': force},
                            'priority': 3,
                            'owner_id': p.owner_id
                        })

                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)

                offset += batch_size

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} classification tasks'
            }

        except Exception as e:
            logger.error(f"Classification task failed: {e}")
            raise e

    async def process_single_photo(self, worker, photo: Photo, db: Session) -> Dict[str, Any]:
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

                api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/classification/"
                async with session.post(api_url, json=json_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        results = result.get('results', [])
                        if results and results[0].get('status') == 'success':
                            predictions = results[0].get('predictions', [])
                        else:
                            predictions = []

                        crud_tag.remove_tags_from_photo(db, photo.id, ai_generated=True)

                        # Save Tags
                        for res in predictions:
                            tag_name = res['label']
                            # if tag_name == 'others':
                            #     break
                            confidence = res['confidence'] - 0.01
                            if confidence < 0.65:
                                break
                            tag = db.query(PhotoTag).filter(PhotoTag.tag_name == tag_name).first()
                            if not tag:
                                tag = PhotoTag(tag_name=tag_name, type='yolo')
                                db.add(tag)
                                db.flush() # get id

                            # Check relation
                            rel = db.query(PhotoTagRelation).filter(
                                PhotoTagRelation.photo_id == photo.id,
                                PhotoTagRelation.tag_id == tag.id
                            ).first()

                            if not rel:
                                rel = PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=confidence)
                                db.add(rel)
                            else:
                                rel.confidence = confidence
                            break

                        tasks_status = dict(photo.processed_tasks or {})
                        tasks_status['classification'] = True
                        photo.processed_tasks = tasks_status
                        db.add(photo)
                        db.commit()
                        return {'status': 'success', 'tags_found': len(predictions)}
                    else:
                        return {'status': 'failed', 'error': f"AI Service error: {resp.status}"}
        except Exception as e:
            logger.error(f"Error processing Classification for photo {photo.id}: {e}")
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['classification'] = False
            photo.processed_tasks = tasks_status
            db.add(photo)
            db.commit()
            raise e

    async def handle_completion(self, worker, items: List[Dict], db: Session) -> None:
        from app.db.models.task import TaskStatus
        for item in items:
            if item['status'] == TaskStatus.COMPLETED:
                if 'classified' not in worker.scan_status:
                    worker.scan_status['classified'] = 0
                worker.scan_status['classified'] += 1

    def release_resources(self) -> None:
        pass
