import os
import asyncio
import logging
import concurrent.futures
import json
from re import S
from typing import List, Dict, Set, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

import app.crud.photo
from app.db.session import SessionLocal
from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.index_log import IndexLog
from app.db.models.system import SystemState
from app.crud import album as album_crud
from app.core.config_manager import config_manager
from app.core.system_config import system_config
from app.service.task_manager import DEFAULT_SCAN_STATUS, CATEGORY_MAP, DEFAULT_PRIORITIES

# Import handlers
from app.service.tasks import thumbnail, metadata, scan, face, ocr, classification, tickets, visual_description, basic, similar, duplicate, image_embedding

CPU_TASKS = {
    TaskType.GENERATE_THUMBNAIL,
    TaskType.REBUILD_THUMBNAILS,
    TaskType.PROCESS_BASIC,
    TaskType.SIMILAR_PHOTO_CLUSTERING,
}

IO_TASKS = {
    TaskType.PROCESS_IMAGE,
    TaskType.EXTRACT_METADATA,
    TaskType.REBUILD_METADATA,
    TaskType.SCAN_FOLDER,
    TaskType.RECOGNIZE_FACE,
    TaskType.OCR,
    TaskType.CLASSIFY_IMAGE,
    TaskType.RECOGNIZE_TICKET,
    TaskType.FIND_DUPLICATE_PHOTOS,
    TaskType.IMAGE_EMBEDDING,
}

AI_TASKS = {
    TaskType.VISUAL_DESCRIPTION,
}

class TaskWorker:
    """
    Task Consumer / Worker (Runs in Background Process)
    Responsible for:
    1. Monitoring task queue
    2. Executing tasks
    3. Managing resources (pools)
    4. Updating system status
    """
    _instance = None
    def __init__(self):
        self.running = False
        self.worker_task = None
        self.result_task = None
        self.process_pool = None
        self.thread_pool = None
        self.result_queue = asyncio.Queue()
        self.scan_status = DEFAULT_SCAN_STATUS.copy()
        
        self.paused_categories: Set[str] = set()
        self.category_map = CATEGORY_MAP
        self.fast_mode = False
        self.active_task_map: Dict[Any, str] = {} # future -> task_type
        self.last_active_time: Dict[str, datetime] = {} # task_type -> last active time

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TaskWorker()
        return cls._instance

    def _save_system_state(self, key: str, value: Any):
        db = SessionLocal()
        try:
            state = db.query(SystemState).filter(SystemState.key == key).first()
            if not state:
                state = SystemState(key=key)
                db.add(state)

            if isinstance(value, (set, list, dict)):
                state.value = json.dumps(value, default=str)
            else:
                state.value = str(value)
            db.commit()
        except Exception as e:
            logging.error(f"Failed to save system state {key}: {e}")
        finally:
            db.close()

    def _load_system_state(self, key: str, default: Any = None):
        db = SessionLocal()
        try:
            state = db.query(SystemState).filter(SystemState.key == key).first()
            if state:
                try:
                    return json.loads(state.value)
                except:
                    return state.value
            return default
        except Exception as e:
            # logging.error(f"Failed to load system state {key}: {e}")
            return default
        finally:
            db.close()

    def start(self):
        if self.running:
            return
        self.running = True
        self._recover_unfinished_tasks()

        # Load fast_mode state
        self.fast_mode = self._load_system_state('fast_mode', False)

        # Use config for max_workers
        # For max_workers, we don't have a user context yet. 
        # We can either use a default or pick the first admin user's config?
        # Or just hardcode a reasonable default for system-wide setting.
        # Since this is a system-level resource setting, it shouldn't really be per-user.
        # But if it was in config.json, it was system-wide.
        # Let's assume default 10 if not found, or maybe we can fetch from a "system" user if one exists?
        # For now, let's use a safe default as we removed system config.
        max_workers = system_config.config.task.max_concurrent_tasks
        self.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count())
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers * 2) # More threads for IO

        self.worker_task = asyncio.create_task(self.worker_loop())
        self.result_task = asyncio.create_task(self.result_loop())
        logging.info(f"TaskWorker started. Fast Mode: {self.fast_mode}")

    def stop(self):
        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
        if self.result_task:
            self.result_task.cancel()
        if self.process_pool:
            self.process_pool.shutdown(wait=False)
            self.process_pool = None
        if self.thread_pool:
            self.thread_pool.shutdown(wait=False)
            self.thread_pool = None

        # Save final status
        self.scan_status['fast_mode'] = self.fast_mode
        self._save_system_state('scan_status', self.scan_status)
        logging.info("TaskWorker stopped")

    def release_resources(self):
        """Release all resources"""
        if self.process_pool:
            logging.info("Shutting down process pool to release resources")
            self.process_pool.shutdown(wait=False)
            self.process_pool = None
        if self.thread_pool:
            logging.info("Shutting down thread pool to release resources")
            self.thread_pool.shutdown(wait=False)
            self.thread_pool = None
        thumbnail.release_resources()
        metadata.release_resources()
        ocr.release_resources()
        scan.release_resources()
        face.release_resources()

    def check_task_for_release(self):
        # Check for Module Resources
        for task_type in TaskType:
            if task_type not in self.last_active_time:
                continue

            last_run = self.last_active_time[task_type]
            if (datetime.now() - last_run).total_seconds() > 30:
                # Release module specific resources
                if task_type == TaskType.PROCESS_BASIC:
                    thumbnail.release_resources()
                elif task_type == TaskType.EXTRACT_METADATA:
                    metadata.release_resources()
                elif task_type == TaskType.OCR:
                    if hasattr(ocr, 'release_resources'): ocr.release_resources()
                elif task_type == TaskType.RECOGNIZE_FACE:
                    if hasattr(face, 'release_resources'): face.release_resources()
                elif task_type == TaskType.CLASSIFY_IMAGE:
                    if hasattr(classification, 'release_resources'): classification.release_resources()
                del self.last_active_time[task_type]


    async def worker_loop(self):
        logging.info("TaskWorker loop started")
        # active_tasks set is replaced by self.active_task_map keys
        idle_start_time = None

        last_sync = datetime.now()

        while self.running:
            try:
                # Sync status periodically (every 5s)
                now = datetime.now()
                if (now - last_sync).total_seconds() > 5:
                    # Reload config if changed
                    # config_manager.reload()
                    
                    self._save_system_state('scan_status', self.scan_status)
                    # Refresh paused categories
                    paused_list = self._load_system_state('paused_categories', [])
                    self.paused_categories = set(paused_list)
                    # Refresh fast_mode
                    self.fast_mode = self._load_system_state('fast_mode', False)
                    last_sync = now

                # Clean up finished tasks
                done_futures = [f for f in self.active_task_map.keys() if f.done()]
                for f in done_futures:
                    del self.active_task_map[f]

                active_count = len(self.active_task_map)

                # Update status
                if active_count > 0:
                    self.scan_status['running'] = True
                    idle_start_time = None

                # Manage Pool Lifecycle (Resource Release)
                # Check for CPU Pool
                active_cpu_count = sum(1 for t in self.active_task_map.values() if t in CPU_TASKS)
                if active_cpu_count == 0 and self.process_pool:
                    # Check if all CPU tasks have been idle for > 30s
                    # If any CPU task has run recently, keep pool
                    last_cpu_run = max([self.last_active_time.get(t, datetime.min) for t in CPU_TASKS], default=datetime.min)
                    if (datetime.now() - last_cpu_run).total_seconds() > 30:
                        # logging.info("Shutting down process pool (CPU) due to inactivity")
                        self.process_pool.shutdown(wait=False)
                        self.process_pool = None

                # Check for IO Pool
                active_io_count = sum(1 for t in self.active_task_map.values() if t in IO_TASKS)
                if active_io_count == 0 and self.thread_pool:
                     # Check if all IO tasks have been idle for > 30s
                    last_io_run = max([self.last_active_time.get(t, datetime.min) for t in IO_TASKS], default=datetime.min)
                    if (datetime.now() - last_io_run).total_seconds() > 30:
                        # logging.info("Shutting down thread pool (IO) due to inactivity")
                        self.thread_pool.shutdown(wait=False)
                        self.thread_pool = None

                self.check_task_for_release()

                if active_count == 0:
                    if idle_start_time is None:
                        idle_start_time = datetime.now()
                        self.scan_status['running'] = False
                        self.scan_status['message'] = "Idle"
                        self._save_system_state('scan_status', self.scan_status)
                else:
                    # Ensure pools exist (re-create if needed)
                    if active_cpu_count > 0:
                        if self.process_pool is None:
                            logging.info(f"Restarting process pool")
                            self.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count())
                    if self.thread_pool is None and active_io_count > 0:
                        max_workers = system_config.config.task.max_concurrent_tasks
                        logging.info(f"Restarting thread pool")
                        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers * 2)

                # Scheduling Logic
                allowed_types = []

                if self.fast_mode:
                    # Fast Mode: Smart Scheduling
                    active_cpu = sum(1 for t in self.active_task_map.values() if t in CPU_TASKS)
                    active_io = sum(1 for t in self.active_task_map.values() if t in IO_TASKS)
                    active_ai = sum(1 for t in self.active_task_map.values() if t in AI_TASKS)

                    max_cpu = os.cpu_count() or 4
                    max_io = 30 # Allow up to 10 concurrent IO tasks
                    max_ai = 2  # Max concurrent AI tasks

                    if active_cpu < max_cpu:
                        allowed_types.extend(CPU_TASKS)
                    if active_io < max_io:
                        allowed_types.extend(IO_TASKS)
                    if active_ai < max_ai:
                        allowed_types.extend(AI_TASKS)

                    # Also include any other types not in CPU/IO/AI sets
                    other_types = [t for t in TaskType if t not in CPU_TASKS and t not in IO_TASKS and t not in AI_TASKS]
                    if active_cpu + active_io + active_ai < max_cpu + max_io + max_ai:
                        allowed_types.extend(other_types)
                else:
                    # Normal Mode: Strict Concurrency Limit
                    max_concurrency = system_config.config.task.max_concurrent_tasks
                    active_ai = sum(1 for t in self.active_task_map.values() if t in AI_TASKS)
                    max_ai = 2

                    if active_count < max_concurrency:
                        allowed_types = [t for t in TaskType if t not in AI_TASKS] # All types except AI
                        if active_ai < max_ai:
                            allowed_types.extend(AI_TASKS)

                if not allowed_types:
                    await asyncio.sleep(0.1)
                    continue

                db = SessionLocal()
                try:
                    # Determine paused types
                    paused_types = []
                    for type_enum, cat in self.category_map.items():
                        if cat in self.paused_categories:
                            paused_types.append(type_enum)

                    # Poll for tasks
                    query = db.query(Task).filter(Task.status == TaskStatus.PENDING)
                    
                    # Filter by allowed types
                    query = query.filter(Task.type.in_(allowed_types))

                    if paused_types:
                        query = query.filter(Task.type.notin_(paused_types))

                    task = query.order_by(Task.priority.desc(), Task.created_at.asc()).first()

                    if task:
                        # Lock task
                        task.status = TaskStatus.PROCESSING
                        db.commit()
                        self.scan_status['current_task'] = f"{task.type} - {task.id}"
                        # Update last active time
                        self.last_active_time[task.type] = datetime.now()
                        # Launch async wrapper
                        future = asyncio.create_task(self.execute_task_wrapper(task.id, task.type))
                        self.active_task_map[future] = task.type
                    else:
                        if active_count == 0:
                            self.scan_status['running'] = False
                            self.scan_status['message'] = "Idle"
                            if idle_start_time:
                                idle_duration = (datetime.now() - idle_start_time).total_seconds()
                                if idle_duration > 300: # 5 minutes
                                    logging.info("Worker idle for 5 minutes, exiting to release resources...")
                                    self.running = False
                                    import sys
                                    sys.exit(0)
                                elif idle_duration > 60:
                                    await asyncio.sleep(5)
                                elif idle_duration > 10:
                                    await asyncio.sleep(2)
                                else:
                                    await asyncio.sleep(1)
                            else:
                                await asyncio.sleep(1)
                        else:
                            await asyncio.sleep(1)
                except Exception as e:
                    logging.error(f"Error in worker loop: {e}")
                    await asyncio.sleep(5)
                finally:
                    db.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Unexpected error in worker loop: {e}")
                await asyncio.sleep(1)

    async def execute_task_wrapper(self, task_id: UUID, task_type: str):
        db = SessionLocal()
        token = None
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return
            
            # Set User Context for this task execution
            if task.owner_id:
                try:
                    user_config = config_manager.get_user_config(task.owner_id, db)
                except Exception as e:
                    logging.error(f"Failed to set user context for task {task_id}: {e}")

            try:
                result = await self.process_task(task, db)
                # Enqueue success result
                await self.result_queue.put({
                    'task_id': task_id,
                    'task_type': task_type,
                    'status': TaskStatus.COMPLETED,
                    'result': result
                })
            except Exception as e:
                logging.error(f"Task {task_id} failed: {e}", exc_info=True)
                # Enqueue failure result
                await self.result_queue.put({
                    'task_id': task_id,
                    'task_type': task_type,
                    'status': TaskStatus.FAILED,
                    'error': str(e)
                })
        except Exception as e:
            logging.error(f"Error in task wrapper for {task_id}: {e}")
        finally:
            # We don't strictly need to reset token as the task is ending,
            # but it's good practice if we were reusing the task (which we aren't).
            # Also ContextVar is task-local so it won't leak.
            db.close()

    async def process_task(self, task: Task, db: Session):
        if task.type == TaskType.SCAN_FOLDER:
            return await scan.handle_scan_folder(self, task, db)
        elif task.type == TaskType.PROCESS_BASIC:
            return await basic.handle_process_basic(self, task, db)
        elif task.type == TaskType.GENERATE_THUMBNAIL:
            return await thumbnail.handle_generate_thumbnail(self, task, db)
        elif task.type == TaskType.REBUILD_THUMBNAILS:
            return await thumbnail.handle_rebuild_thumbnails(self, task, db)
        elif task.type == TaskType.REBUILD_METADATA:
            return await metadata.handle_rebuild_metadata(self, task, db)
        elif task.type == TaskType.EXTRACT_METADATA:
            return await metadata.handle_extract_metadata(self, task, db)
        elif task.type == TaskType.RECOGNIZE_FACE:
            return await face.handle_recognize_face(self, task, db)
        elif task.type == TaskType.RECOGNIZE_TICKET:
            return await tickets.handle_ticket_task(self, task, db)
        elif task.type == TaskType.OCR:
            return await ocr.handle_ocr_task(self, task, db)
        elif task.type == TaskType.CLASSIFY_IMAGE:
            return await classification.handle_classify_image(self, task, db)
        elif task.type == TaskType.VISUAL_DESCRIPTION:
            return await visual_description.handle_visual_description_task(self, task, db)
        elif task.type == TaskType.SIMILAR_PHOTO_CLUSTERING:
            return await similar.handle_similar_task(self, task, db)
        elif task.type == TaskType.FIND_DUPLICATE_PHOTOS:
            return await duplicate.handle_duplicate_task(self, task, db)
        elif task.type == TaskType.IMAGE_EMBEDDING:
            return await image_embedding.handle_image_embedding(self, task, db)
        else:
            return {'status': 'not_implemented', 'type': task.type}

    async def result_loop(self):
        logging.info("TaskWorker result loop started")
        pending_items = []
        last_flush = datetime.now()
        while self.running:
            try:
                try:
                    # Collect items with short timeout
                    item = await asyncio.wait_for(self.result_queue.get(), timeout=0.5)
                    pending_items.append(item)
                except asyncio.TimeoutError:
                    pass
                now = datetime.now()
                should_flush = len(pending_items) >= 50 or ((now - last_flush).total_seconds() > 1 and pending_items)
                if should_flush:
                    logging.info(f"Flushing {len(pending_items)} results")
                    self._flush_results(pending_items)
                    pending_items = []
                    last_flush = now
                    # Update status in DB
                    self._save_system_state('scan_status', self.scan_status)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in result loop: {e}")
                await asyncio.sleep(1)

    def _recover_unfinished_tasks(self):
        """启动时恢复未完成的任务：重置PROCESSING为PENDING，统计未完成任务数"""
        db = SessionLocal()
        try:
            # 1. 统计未完成任务（PENDING + PROCESSING）
            pending_tasks = db.query(Task).filter(Task.status == TaskStatus.PENDING).count()
            processing_tasks = db.query(Task).filter(Task.status == TaskStatus.PROCESSING).count()
            total_unfinished = pending_tasks + processing_tasks

            if total_unfinished == 0:
                logging.info("No unfinished tasks to recover")
                return

            # 2. 重置PROCESSING任务为PENDING（服务重启后，PROCESSING的任务已中断）
            if processing_tasks > 0:
                # 获取所有PROCESSING状态的任务
                processing_task_list = db.query(Task).filter(Task.status == TaskStatus.PROCESSING).all()
                for task in processing_task_list:
                    # 检查payload中是否包含force=True
                    if task.payload and task.payload.get('force') is True:
                        # 如果是强制任务，重置时移除force标记，避免无限循环重复处理
                        new_payload = task.payload.copy()
                        new_payload['force'] = False
                        task.payload = new_payload
                        logging.info(f"Reset task {task.id} payload: removed force=True")
                    task.status = TaskStatus.PENDING
                db.commit()
                logging.info(f"Reset {processing_tasks} PROCESSING tasks to PENDING (recovered)")

            # 3. 初始化扫描状态（标记有未完成任务，更新统计）
            self.scan_status['running'] = True
            self.scan_status['message'] = f"Recovered {total_unfinished} unfinished tasks"
            self.scan_status['total_files'] = max(self.scan_status['total_files'], total_unfinished)
            logging.info(f"Recovered total {total_unfinished} unfinished tasks (pending: {pending_tasks}, processing: {processing_tasks})")
            self._save_system_state('scan_status', self.scan_status)
            paused_list = self._load_system_state('paused_categories', [])
            self.paused_categories = set(paused_list)

        except Exception as e:
            logging.error(f"Failed to recover unfinished tasks: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    def _flush_results(self, items: List[Dict]):
        db = SessionLocal()
        try:
            # 1. Prepare batch photo inserts
            photos_to_create = {} # user_id -> list of data
            index_logs = []

            # Map of temp photo_id to file_path for task chaining
            processed_photos = {} # photo_id -> {path: file_path, owner_id: user_id}

            for item in items:
                task_type = item['task_type']
                status = item['status']

                # Handle PROCESS_BASIC (and legacy PROCESS_IMAGE if needed)
                if status == TaskStatus.COMPLETED and (task_type == TaskType.PROCESS_BASIC or task_type == TaskType.PROCESS_IMAGE):
                    res = item['result']
                    if 'photo_create_data' in res:
                        data = res['photo_create_data']
                        user_id = data.get('user_id')
                        if user_id not in photos_to_create:
                            photos_to_create[user_id] = []
                        photos_to_create[user_id].append(data)
                        index_logs.append(IndexLog(action='added', file_path=data['file_path'], photo_id=data['photo_id'], owner_id=user_id))
                        # Store for chaining
                        processed_photos[str(data['photo_id'])] = {'path': data['file_path'], 'owner_id': user_id}
                        # Update stats
                        self.scan_status['added'] += 1
                        self.scan_status['processed_files'] += 1
                elif status == TaskStatus.COMPLETED and task_type == TaskType.CLASSIFY_IMAGE:
                    if 'classified' not in self.scan_status:
                        self.scan_status['classified'] = 0
                    self.scan_status['classified'] += 1

            # Batch insert photos
            if photos_to_create:
                for uid, photos in photos_to_create.items():
                    app.crud.photo.batch_create_photos(db, photos, user_id=uid)
                db.add_all(index_logs)

                # Now chain subsequent tasks for newly created photos
                for photo_id, info in processed_photos.items():
                    file_path = info['path']
                    owner_id = info['owner_id']

                    # 1. Metadata Task (High Priority)
                    db.add(Task(
                        type=TaskType.EXTRACT_METADATA,
                        payload={'file_path': file_path, 'photo_id': photo_id},
                        priority=DEFAULT_PRIORITIES[TaskType.EXTRACT_METADATA],
                        status=TaskStatus.PENDING,
                        owner_id=owner_id
                    ))
                    # 2. Face Recognition Task (Low Priority)
                    db.add(Task(
                        type=TaskType.RECOGNIZE_FACE,
                        payload={'file_path': file_path, 'photo_id': photo_id},
                        priority=DEFAULT_PRIORITIES[TaskType.RECOGNIZE_FACE],
                        status=TaskStatus.PENDING,
                        owner_id=owner_id
                    ))
                    # 3. OCR Task (Low Priority)
                    db.add(Task(
                        type=TaskType.OCR,
                        payload={'file_path': file_path, 'photo_id': photo_id},
                        priority=DEFAULT_PRIORITIES[TaskType.OCR],
                        status=TaskStatus.PENDING,
                        owner_id=owner_id
                    ))
                    # 4. Classification Task (Low Priority)
                    db.add(Task(
                        type=TaskType.CLASSIFY_IMAGE,
                        payload={'file_path': file_path, 'photo_id': photo_id},
                        priority=DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE],
                        status=TaskStatus.PENDING,
                        owner_id=owner_id
                    ))
                    # 5. Ticket Recognition Task (Low Priority)
                    db.add(Task(
                        type=TaskType.RECOGNIZE_TICKET,
                        payload={'file_path': file_path, 'photo_id': photo_id},
                        priority=DEFAULT_PRIORITIES.get(TaskType.RECOGNIZE_TICKET, 2),
                        status=TaskStatus.PENDING,
                        owner_id=owner_id
                    ))
                    # 6. Visual Description Task (Low Priority)
                    db.add(Task(
                        type=TaskType.VISUAL_DESCRIPTION,
                        payload={'file_path': file_path, 'photo_id': photo_id},
                        priority=DEFAULT_PRIORITIES.get(TaskType.VISUAL_DESCRIPTION, 2),
                        status=TaskStatus.PENDING,
                        owner_id=owner_id
                    ))
                    # 7. Embedding Generation Task (Low Priority)
                    db.add(Task(
                        type=TaskType.IMAGE_EMBEDDING,
                        payload={'file_path': file_path, 'photo_id': photo_id},
                        priority=DEFAULT_PRIORITIES.get(TaskType.IMAGE_EMBEDDING, 2),
                        status=TaskStatus.PENDING,
                        owner_id=owner_id
                    ))

            # Mark tasks as completed/failed in DB?
            # Actually, execute_task_wrapper doesn't update Task status in DB, it only puts result in queue.
            # And _flush_results here only handles success for chaining.
            # We MUST update task status in DB.

            task_ids_completed = []
            task_ids_failed = []

            # Tasks that should be preserved in DB after completion
            PRESERVED_TASK_TYPES = set()

            for item in items:
                if item['status'] == TaskStatus.COMPLETED:
                    # Only delete if not in preserved types
                    if item['task_type'] not in PRESERVED_TASK_TYPES:
                        task_ids_completed.append(item['task_id'])
                    else:
                        logging.info(f"Preserving completed task {item['task_id']} of type {item['task_type']}")
                else:
                    task_ids_failed.append(item['task_id'])

            if task_ids_completed:
                db.query(Task).filter(Task.id.in_(task_ids_completed)).delete(synchronize_session=False)

            if task_ids_failed:
                # Update failed tasks
                # Bulk update might be hard if we want to save error message
                # For simplicity, iterate
                for item in items:
                    if item['status'] == TaskStatus.FAILED:
                         t = db.query(Task).filter(Task.id == item['task_id']).first()
                         if t:
                             t.status = TaskStatus.FAILED
                             t.error = item.get('error')
            db.commit()
        except Exception as e:
            logging.error(f"Failed to flush results: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    def add_task(self, db: Session, type: str, payload: dict, priority: int = 0, owner_id: UUID = None):
        if priority == 0:
            priority = DEFAULT_PRIORITIES.get(type, 0)

        task = Task(type=type, payload=payload, priority=priority, owner_id=owner_id)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def add_tasks(self, db: Session, tasks_data: List[Dict], owner_id: UUID = None):
        """Batch add tasks"""
        if not tasks_data:
            return

        tasks = []
        for t_data in tasks_data:
            priority = t_data.get('priority', 0)
            if priority == 0:
                priority = DEFAULT_PRIORITIES.get(t_data['type'], 0)

            task_owner_id = t_data.get('owner_id', owner_id)

            tasks.append(Task(
                type=t_data['type'],
                payload=t_data.get('payload', {}),
                priority=priority,
                status=TaskStatus.PENDING,
                owner_id=task_owner_id
            ))

        db.bulk_save_objects(tasks)
        db.commit()