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

from app.db.session import SessionLocal
from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.system import SystemState
from app.core.system_config import system_config
from app.service.task_manager import DEFAULT_SCAN_STATUS, CATEGORY_MAP, DEFAULT_PRIORITIES

from app.service.task_strategy import TaskStrategyFactory
from app.service.tasks import thumbnail, metadata

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

    @property
    def CPU_TASKS(self):
        return TaskStrategyFactory.get_tasks_by_category('CPU')

    @property
    def IO_TASKS(self):
        return TaskStrategyFactory.get_tasks_by_category('IO')

    @property
    def AI_TASKS(self):
        return TaskStrategyFactory.get_tasks_by_category('AI')

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
        TaskStrategyFactory.release_all_resources()

    def check_task_for_release(self):
        # Check for Module Resources
        idle_types = []
        for task_type in TaskType:
            if task_type not in self.last_active_time:
                continue

            last_run = self.last_active_time[task_type]
            if (datetime.now() - last_run).total_seconds() > 300:
                idle_types.append(task_type)
                
        if idle_types:
            TaskStrategyFactory.release_idle_resources(idle_types)
            for t in idle_types:
                del self.last_active_time[t]



    def _sync_system_state_if_needed(self):
        now = datetime.now()
        if not hasattr(self, '_last_sync'):
            self._last_sync = datetime.min
        if (now - self._last_sync).total_seconds() > 5:
            self._save_system_state('scan_status', self.scan_status)
            paused_list = self._load_system_state('paused_categories', [])
            self.paused_categories = set(paused_list)
            self.fast_mode = self._load_system_state('fast_mode', False)
            self._last_sync = now

    def _manage_pool_lifecycle(self):
        active_count = len(self.active_task_map)
        
        # Check for CPU Pool
        active_cpu_count = sum(1 for t in self.active_task_map.values() if t in self.CPU_TASKS)
        if active_cpu_count == 0 and self.process_pool:
            last_cpu_run = max([self.last_active_time.get(t, datetime.min) for t in self.CPU_TASKS], default=datetime.min)
            if (datetime.now() - last_cpu_run).total_seconds() > 300:
                self.process_pool.shutdown(wait=False)
                self.process_pool = None

        # Check for IO Pool
        active_io_count = sum(1 for t in self.active_task_map.values() if t in self.IO_TASKS)
        if active_io_count == 0 and self.thread_pool:
            last_io_run = max([self.last_active_time.get(t, datetime.min) for t in self.IO_TASKS], default=datetime.min)
            if (datetime.now() - last_io_run).total_seconds() > 300:
                self.thread_pool.shutdown(wait=False)
                self.thread_pool = None

        self.check_task_for_release()

        # Ensure pools exist
        if active_count > 0:
            if active_cpu_count > 0 and self.process_pool is None:
                logging.info(f"Restarting process pool")
                self.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count())
            if self.thread_pool is None and active_io_count > 0:
                max_workers = system_config.config.task.max_concurrent_tasks
                logging.info(f"Restarting thread pool")
                self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers * 2)

    def _calculate_allowed_task_types(self) -> List[str]:
        allowed_types = []
        active_count = len(self.active_task_map)
        
        if self.fast_mode:
            active_cpu = sum(1 for t in self.active_task_map.values() if t in self.CPU_TASKS)
            active_io = sum(1 for t in self.active_task_map.values() if t in self.IO_TASKS)
            active_ai = sum(1 for t in self.active_task_map.values() if t in self.AI_TASKS)

            max_cpu = os.cpu_count() or 4
            max_io = 30
            max_ai = 2

            if active_cpu < max_cpu:
                allowed_types.extend(self.CPU_TASKS)
            if active_io < max_io:
                allowed_types.extend(self.IO_TASKS)
            if active_ai < max_ai:
                allowed_types.extend(self.AI_TASKS)

            other_types = [t for t in TaskType if t not in self.CPU_TASKS and t not in self.IO_TASKS and t not in self.AI_TASKS]
            if active_cpu + active_io + active_ai < max_cpu + max_io + max_ai:
                allowed_types.extend(other_types)
        else:
            max_concurrency = system_config.config.task.max_concurrent_tasks
            active_ai = sum(1 for t in self.active_task_map.values() if t in self.AI_TASKS)
            max_ai = 2

            if active_count < max_concurrency:
                allowed_types = [t for t in TaskType if t not in self.AI_TASKS]
                if active_ai < max_ai:
                    allowed_types.extend(self.AI_TASKS)
                    
        return allowed_types

    def _fetch_and_dispatch_tasks_sync(self, allowed_types: List[str]) -> List[dict]:
        db = SessionLocal()
        dispatched_tasks = []
        try:
            paused_types = []
            for type_enum, cat in self.category_map.items():
                if cat in self.paused_categories:
                    paused_types.append(type_enum)

            query = db.query(Task).filter(Task.status == TaskStatus.PENDING)
            query = query.filter(Task.type.in_(allowed_types))

            if paused_types:
                query = query.filter(Task.type.notin_(paused_types))

            batch_size = 10
            active_count = len(self.active_task_map)
            if self.fast_mode:
                max_cpu = os.cpu_count() or 4
                max_io = 30
                max_ai = 2
                batch_size = max(1, (max_cpu + max_io + max_ai) - active_count)
            else:
                max_concurrency = system_config.config.task.max_concurrent_tasks
                batch_size = max(1, max_concurrency - active_count)
            
            batch_size = min(batch_size, 20)

            tasks = query.order_by(Task.priority.desc(), Task.created_at.asc()).limit(batch_size).all()

            if tasks:
                for task in tasks:
                    task.status = TaskStatus.PROCESSING
                    self.last_active_time[task.type] = datetime.now()
                    dispatched_tasks.append({'id': task.id, 'type': task.type})
                    self.scan_status['current_task'] = f"{task.type} - {task.id}"
                db.commit()
                
            return dispatched_tasks
        except Exception as e:
            logging.error(f"Error fetching tasks: {e}")
            return []
        finally:
            db.close()

    async def _fetch_and_dispatch_tasks(self, allowed_types: List[str]) -> int:
        # Run DB operation in thread pool to avoid blocking asyncio event loop
        tasks = await asyncio.to_thread(self._fetch_and_dispatch_tasks_sync, allowed_types)
        
        for task_info in tasks:
            future = asyncio.create_task(self.execute_task_wrapper(task_info['id'], task_info['type']))
            self.active_task_map[future] = task_info['type']
            
        return len(tasks)

    async def worker_loop(self):
        logging.info("TaskWorker loop started")
        self._idle_start_time = None
        self._backoff_delay = 1.0

        while self.running:
            try:
                # Clean up finished tasks
                done_futures = [f for f in self.active_task_map.keys() if f.done()]
                for f in done_futures:
                    del self.active_task_map[f]

                self._sync_system_state_if_needed()
                self._manage_pool_lifecycle()
                
                active_count = len(self.active_task_map)
                if active_count > 0:
                    self.scan_status['running'] = True
                    self._idle_start_time = None
                    self._backoff_delay = 1.0
                else:
                    if self._idle_start_time is None:
                        self._idle_start_time = datetime.now()
                        self.scan_status['running'] = False
                        self.scan_status['message'] = "Idle"
                        self._save_system_state('scan_status', self.scan_status)

                allowed_types = self._calculate_allowed_task_types()
                if not allowed_types:
                    await asyncio.sleep(0.1)
                    continue

                dispatched_count = await self._fetch_and_dispatch_tasks(allowed_types)
                
                if dispatched_count == 0:
                    if active_count == 0 and self._idle_start_time:
                        idle_duration = (datetime.now() - self._idle_start_time).total_seconds()
                        if idle_duration > 300: # 5 minutes
                            logging.info("Worker idle for 5 minutes, exiting to release resources...")
                            self.running = False
                            import sys
                            sys.exit(0)
                            
                    # Exponential backoff
                    await asyncio.sleep(self._backoff_delay)
                    self._backoff_delay = min(self._backoff_delay * 1.5, 10.0)
                else:
                    self._backoff_delay = 1.0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Unexpected error in worker loop: {e}")
                await asyncio.sleep(1)

    async def execute_task_wrapper(self, task_id: UUID, task_type: str):
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return

            try:
                # Wait for task completion with a timeout
                timeout = 120.0 if task_type in self.AI_TASKS else 300.0
                result = await asyncio.wait_for(self.process_task(task, db), timeout=timeout)
                
                if result and 'status' in result and result['status'] == 'failed':
                    # Enqueue failure result
                    await self.result_queue.put({
                        'task_id': task_id,
                        'task_type': task_type,
                        'status': TaskStatus.FAILED,
                        'error': result['error']
                    })
                else:
                    # Enqueue success result
                    await self.result_queue.put({
                        'task_id': task_id,
                        'task_type': task_type,
                        'status': TaskStatus.COMPLETED,
                        'result': result
                    })
            except asyncio.TimeoutError:
                logging.error(f"Task {task_id} timed out after {timeout} seconds")
                await self.result_queue.put({
                    'task_id': task_id,
                    'task_type': task_type,
                    'status': TaskStatus.FAILED,
                    'error': f"Task timed out after {timeout} seconds"
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
        strategy = TaskStrategyFactory.get_strategy(task.type)
        if strategy:
            return await strategy.process(self, task, db)
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
                    await self._flush_results(pending_items)
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

    async def _flush_results(self, items: List[Dict]):
        db = SessionLocal()
        try:
            # Group items by task_type
            items_by_type = {}
            for item in items:
                t_type = item['task_type']
                if t_type not in items_by_type:
                    items_by_type[t_type] = []
                items_by_type[t_type].append(item)

            # Call handle_completion for each strategy
            for t_type, type_items in items_by_type.items():
                strategy = TaskStrategyFactory.get_strategy(t_type)
                if strategy:
                    await strategy.handle_completion(self, type_items, db)

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
                failed_mappings = []
                for item in items:
                    if item['status'] == TaskStatus.FAILED:
                         failed_mappings.append({
                             'id': item['task_id'],
                             'status': TaskStatus.FAILED,
                             'error': item.get('error')
                         })
                if failed_mappings:
                    db.bulk_update_mappings(Task, failed_mappings)
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