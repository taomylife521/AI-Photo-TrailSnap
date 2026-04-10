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
from app.db.models.face import Face
from app.service.face_cluster import FaceClusterService, crud_face
from typing import Dict, Any, List
from app.core.config_manager import config_manager
from app.service import storage

logger = logging.getLogger(__name__)

@TaskStrategyFactory.register(TaskType.RECOGNIZE_FACE)
class RecognizeFaceStrategy(BaseTaskStrategy):
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
                    if tasks_status.get('face'):
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
                    if p.file_type == FileType.video:
                        continue
                    
                    should_process = False
                    if force:
                        should_process = True
                    else:
                        tasks_status = p.processed_tasks or {}
                        if not tasks_status.get('face'):
                            should_process = True
                    
                    if should_process:
                        tasks_to_create.append({
                            'type': TaskType.RECOGNIZE_FACE,
                            'payload': {'photo_id': str(p.id), 'force': force},
                            'priority': 2,
                            'owner_id': p.owner_id
                        })

                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)

                offset += batch_size

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} face recognition tasks'
            }

        except Exception as e:
            logger.error(f"Face task failed: {e}")
            raise e

    async def process_single_photo(self, worker, photo: Photo, db: Session) -> Dict[str, Any]:
        try:
            cluster_service = FaceClusterService(db, photo.owner_id)
            target_path = storage.get_preview_path(photo.owner_id, photo.id)
            if not os.path.exists(target_path):
                target_path = photo.file_path
                if not target_path or not os.path.exists(target_path):
                    return {'status': 'failed', 'error': 'file not found'}

            async with aiohttp.ClientSession() as session:
                with open(target_path, 'rb') as f:
                    file_data = f.read()
                width, height, _ = storage.get_image_dimensions(target_path)

                import base64
                b64_data = base64.b64encode(file_data).decode('utf-8')
                json_data = {"images": [b64_data]}

                api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/face/face-recognition"
                async with session.post(api_url, json=json_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        results = result.get('results', [])
                        faces = results[0].get('faces', []) if results else []

                        # Clean up old faces
                        crud_face.delete_faces_by_photo(db, photo.id)

                        count = 0
                        has_unassigned = False
                        for face_data in faces:
                            if face_data.get('det_score') < config_manager.get_user_config(photo.owner_id, db).ai.face_recognition_threshold:
                                continue

                            # Normalize face_rect (bbox) to 0-1 relative coordinates
                            bbox = face_data.get('bbox')
                            if bbox and len(bbox) == 4 and width and height and width > 0 and height > 0:
                                bbox = [
                                    min(max(bbox[0] / width, 0.0), 1.0),
                                    min(max(bbox[1] / height, 0.0), 1.0),
                                    min(max(bbox[2] / width, 0.0), 1.0),
                                    min(max(bbox[3] / height, 0.0), 1.0)
                                ]

                            face = Face(
                                photo_id=photo.id,
                                face_feature=face_data.get('embedding'),
                                face_rect=bbox,
                                face_confidence=face_data.get('det_score'),
                                recognize_confidence=0.0 # Placeholder
                            )
                            db.add(face)
                            # Flush to get ID
                            db.flush()

                            count += 1
                            if face.face_feature:
                                try:
                                    assigned_id = cluster_service.assign_face_to_identity(face.id, face.face_feature)
                                    if not assigned_id:
                                        has_unassigned = True
                                except Exception as ce:
                                    logging.error(f"Clustering failed for face {face.id}: {ce}")

                        if has_unassigned:
                             # Commit faces first to ensure they exist for clustering
                             db.commit()
                             try:
                                 cluster_service.process_unassigned_faces(photo.owner_id)
                             except Exception as ce:
                                 logging.error(f"Batch clustering failed: {ce}")

                        tasks_status = dict(photo.processed_tasks or {})
                        tasks_status['face'] = True
                        photo.processed_tasks = tasks_status
                        db.add(photo)
                        db.commit()
                        
                        if photo.owner_id:
                            from app.crud.album import trigger_conditional_albums_update
                            trigger_conditional_albums_update(db, photo.owner_id, [photo.id])
                            
                        return {'status': 'success', 'faces_found': count}
                    else:
                        return {'status': 'failed', 'error': f"AI Service error: {resp.status}"}
        except Exception as e:
            logger.error(f"Error processing Face for photo {photo.id}: {e}")
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['face'] = False
            photo.processed_tasks = tasks_status
            db.add(photo)
            db.commit()
            raise e

    def release_resources(self) -> None:
        pass
