from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import asyncio
import logging
import os
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.photo import Photo
from app.service import storage

def rebuild_thumbnail_cpu_job(user_id: str, file_path: str, file_id: UUID, storage_root: str):
    try:
        storage.update_storage_root_cache(user_id, storage_root)
        thumb_path = storage.generate_thumbnail(user_id, file_path, file_id, db=None)
        return {"success": True, "thumb_path": thumb_path}
    except Exception as e:
        return {"success": False, "error": str(e)}

@TaskStrategyFactory.register(TaskType.GENERATE_THUMBNAIL)
class GenerateThumbnailStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'CPU'

    async def process(self, worker, task: Task, db: Session):
        """Single item thumbnail generation"""
        photo_id_str = task.payload.get('photo_id')
        if not photo_id_str:
            return {'status': 'skipped', 'reason': 'missing photo_id'}
    
        try:
            photo_id = UUID(photo_id_str)
        except:
            return {'status': 'failed', 'reason': 'invalid uuid'}

        photo = db.query(Photo).filter(Photo.id == photo_id).first()
        if not photo:
             return {'status': 'skipped', 'reason': 'photo not found'}
    
        if not os.path.exists(photo.file_path):
            return {'status': 'failed', 'reason': 'file not found'}

        storage_root = storage._get_storage_root(photo.owner_id, db)
        loop = asyncio.get_running_loop()
    
        res = await loop.run_in_executor(
            worker.thread_pool,
            rebuild_thumbnail_cpu_job,
            photo.owner_id,
            photo.file_path,
            photo.id,
            storage_root
        )
    
        if res['success']:
            # Mark as processed
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['thumbnail'] = True
            photo.processed_tasks = tasks_status
            db.add(photo)
            db.commit()
            return {'status': 'success'}
        else:
            raise Exception(res.get('error'))

@TaskStrategyFactory.register(TaskType.REBUILD_THUMBNAILS)
class RebuildThumbnailsStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'CPU'

    async def process(self, worker, task: Task, db: Session):
        scope = task.payload.get('scope', 'all')
        force = task.payload.get('force', False)
    
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
                    if not tasks_status.get('thumbnail'):
                        should_process = True
            
                if should_process:
                    tasks_to_create.append({
                        'type': TaskType.GENERATE_THUMBNAIL,
                        'payload': {'photo_id': str(p.id)},
                        'priority': 8,
                        'owner_id': p.owner_id
                    })
        
            if tasks_to_create:
                worker.add_tasks(db, tasks_to_create)
                generated_count += len(tasks_to_create)
            
            offset += batch_size
    
        return {
            'processed': 0,
            'generated_tasks': generated_count,
            'message': f'Generated {generated_count} thumbnail generation tasks'
        }

def release_resources():
    pass