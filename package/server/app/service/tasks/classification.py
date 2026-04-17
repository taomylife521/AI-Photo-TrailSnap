from app.service.task_manager import DEFAULT_PRIORITIES
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, TaskStatus
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

_tag_cache: Dict[str, PhotoTag] = {}

@TaskStrategyFactory.register(TaskType.CLASSIFY_IMAGE)
class ClassifyImageStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

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


    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        generator_tasks = []
        photo_tasks = []

        for task in tasks:
            if task.payload and 'photo_id' in task.payload:
                photo_tasks.append(task)
            else:
                generator_tasks.append(task)

        # Process generator tasks normally
        for task in generator_tasks:
            try:
                res = await self.process(worker, task, db)
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed' if res and isinstance(res, dict) and res.get('status') == 'failed' else 'completed',
                    'result': res,
                    'error': res.get('error') if res and isinstance(res, dict) else None
                })
            except Exception as e:
                logger.error(f"Error processing generator task {task.id}: {e}")
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed',
                    'error': str(e)
                })

        if not photo_tasks:
            return results

        # Group photo tasks by owner_id
        tasks_by_owner = {}
        for task in photo_tasks:
            owner_id = task.owner_id
            if owner_id not in tasks_by_owner:
                tasks_by_owner[owner_id] = []
            tasks_by_owner[owner_id].append(task)

        import base64
        for owner_id, owner_tasks in tasks_by_owner.items():
            try:
                photo_ids = [t.payload['photo_id'] for t in owner_tasks]
                photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
                photo_map = {str(p.id): p for p in photos}

                valid_tasks = []
                b64_images = []
                valid_photos = []

                for task in owner_tasks:
                    photo_id = str(task.payload['photo_id'])
                    photo = photo_map.get(photo_id)
                    force = task.payload.get('force', False)

                    if not photo:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'photo not found'}})
                        continue

                    if not force:
                        tasks_status = photo.processed_tasks or {}
                        if tasks_status.get('classification'):
                            results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'already processed'}})
                            continue

                    target_path = storage.get_preview_path(photo.owner_id, photo.id)
                    if not os.path.exists(target_path):
                        target_path = photo.file_path

                    if not target_path or not os.path.exists(target_path):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': 'file not found'})
                        continue

                    try:
                        with open(target_path, 'rb') as f_img:
                            b64_data = base64.b64encode(f_img.read()).decode('utf-8')
                        b64_images.append(b64_data)
                        valid_tasks.append(task)
                        valid_photos.append(photo)
                    except Exception as e:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': f'read file error: {e}'})

                if not valid_tasks:
                    continue

                # Batch AI request
                api_url = f"{config_manager.get_user_config(owner_id, db).ai.ai_api_url}/classification/"
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, json={"images": b64_images}) as resp:
                        if resp.status == 200:
                            result_data = await resp.json()
                            ai_results = result_data.get('results', [])
                            photos_to_ticket = []

                            all_tag_names = set()
                            photo_tag_data = []
                            for idx, task in enumerate(valid_tasks):
                                photo = valid_photos[idx]
                                res_item = ai_results[idx] if idx < len(ai_results) else {}
                                predictions = res_item.get('predictions', []) if res_item.get('status') == 'success' else []

                                selected_tag = None
                                for res in predictions:
                                    tag_name = res['label']
                                    confidence = res['confidence'] - 0.01
                                    if confidence < 0.75 or tag_name == 'others':
                                        break
                                    if tag_name in ['火车票', '机票', '电影票', '火车票截图']:
                                        photos_to_ticket.append(photo)
                                        break
                                    selected_tag = (photo, tag_name, confidence)
                                    all_tag_names.add(tag_name)
                                    break

                                photo_tag_data.append((task, photo, selected_tag))

                            if all_tag_names:
                                existing_tags = db.query(PhotoTag).filter(
                                    PhotoTag.tag_name.in_(all_tag_names)
                                ).all()
                                tag_map = {t.tag_name: t for t in existing_tags}

                                tags_to_create = []
                                for tag_name in all_tag_names:
                                    if tag_name not in tag_map:
                                        tags_to_create.append(PhotoTag(tag_name=tag_name, type='yolo'))
                                if tags_to_create:
                                    db.add_all(tags_to_create)
                                    db.flush()
                                    for tag in tags_to_create:
                                        tag_map[tag.tag_name] = tag

                                for task, photo, tag_data in photo_tag_data:
                                    if tag_data:
                                        _, tag_name, confidence = tag_data
                                        tag = tag_map[tag_name]

                                        crud_tag.remove_tags_from_photo(db, photo.id, ai_generated=True)

                                        rel = db.query(PhotoTagRelation).filter(
                                            PhotoTagRelation.photo_id == photo.id,
                                            PhotoTagRelation.tag_id == tag.id
                                        ).first()

                                        if rel:
                                            rel.confidence = confidence
                                        else:
                                            db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=confidence))

                                        tasks_status = dict(photo.processed_tasks or {})
                                        tasks_status['classification'] = True
                                        photo.processed_tasks = tasks_status
                                        db.add(photo)

                                        results.append({
                                            'task_id': task.id,
                                            'task_type': task.type,
                                            'status': 'completed',
                                            'result': {'status': 'success', 'tags_found': 1}
                                        })
                                    else:
                                        tasks_status = dict(photo.processed_tasks or {})
                                        tasks_status['classification'] = True
                                        photo.processed_tasks = tasks_status
                                        db.add(photo)
                                        results.append({
                                            'task_id': task.id,
                                            'task_type': task.type,
                                            'status': 'completed',
                                            'result': {'status': 'success', 'tags_found': 0}
                                        })

                            else:
                                for idx, task in enumerate(valid_tasks):
                                    photo = valid_photos[idx]
                                    tasks_status = dict(photo.processed_tasks or {})
                                    tasks_status['classification'] = True
                                    photo.processed_tasks = tasks_status
                                    db.add(photo)
                                    results.append({
                                        'task_id': task.id,
                                        'task_type': task.type,
                                        'status': 'completed',
                                        'result': {'status': 'success', 'tags_found': 0}
                                    })
                            new_tasks = []
                            for photo in photos_to_ticket:
                                new_tasks.append(
                                    Task(
                                        type=TaskType.RECOGNIZE_TICKET,
                                        payload={'file_path': photo.file_path, 'photo_id': str(photo.id)},
                                        priority=DEFAULT_PRIORITIES.get(TaskType.RECOGNIZE_TICKET, 2),
                                        status=TaskStatus.PENDING,
                                        owner_id=photo.owner_id
                                    )
                                )
                            db.add_all(new_tasks)
                            db.commit()
                        else:
                            err_msg = f"AI Service error: {resp.status}"
                            for task in valid_tasks:
                                results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': err_msg})

            except Exception as e:
                logger.error(f"Error processing batch for owner {owner_id}: {e}")
                for task in owner_tasks:
                    if not any(r['task_id'] == task.id for r in results):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': str(e)})

        return results

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
                            if tag_name == 'others':
                                break
                            confidence = res['confidence'] - 0.01
                            if confidence < 0.75:
                                break
                            global _tag_cache
                            tag = _tag_cache.get(tag_name)
                            if not tag:
                                tag = db.query(PhotoTag).filter(PhotoTag.tag_name == tag_name).first()
                                if not tag:
                                    tag = PhotoTag(tag_name=tag_name, type='yolo')
                                    db.add(tag)
                                    db.flush()
                                _tag_cache[tag_name] = tag

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
        global _tag_cache
        _tag_cache.clear()
