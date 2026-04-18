import logging
import json
from typing import List, Dict, Set, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.system import SystemState

DEFAULT_PRIORITIES = {
    TaskType.SCAN_FOLDER: 100,
    TaskType.PROCESS_BASIC: 99,
    TaskType.GENERATE_THUMBNAIL: 98,
    TaskType.EXTRACT_METADATA: 97,
    TaskType.REBUILD_METADATA: 96,
    TaskType.REBUILD_THUMBNAILS: 95,
    TaskType.RECOGNIZE_FACE: 10,
    TaskType.CLASSIFY_IMAGE: 9,
    TaskType.IMAGE_EMBEDDING: 8,
    TaskType.OCR: 7,
    TaskType.RECOGNIZE_TICKET:4,
    TaskType.VISUAL_DESCRIPTION: 1,
    TaskType.SIMILAR_PHOTO_CLUSTERING: 1000,
    TaskType.FIND_DUPLICATE_PHOTOS: 1000,
}

DEFAULT_SCAN_STATUS = {
    'running': False,
    'progress': 0.0,
    'added': 0,
    'deleted': 0,
    'errors': 0,
    'current_task': None,
    'message': 'Idle',
    'total_files': 0,
    'processed_files': 0,
    'classified': 0
}

CATEGORY_DESCRIPTION_MAP = {
    TaskType.SCAN_FOLDER: '用于扫描文件夹中的文件',
    TaskType.PROCESS_BASIC: '用于基本文件处理',
    TaskType.EXTRACT_METADATA: '用于提取文件元数据（GPS位置、拍摄参数等）',
    TaskType.RECOGNIZE_FACE: '用于识别图片中的人脸',
    TaskType.RECOGNIZE_TICKET: '用于识别火车票、飞机票等',
    TaskType.CLASSIFY_IMAGE: '用于场景分类',
    TaskType.VISUAL_DESCRIPTION: '用于生成图片的视觉描述',
    TaskType.OCR: '用于识别图片中的文字',
    TaskType.SIMILAR_PHOTO_CLUSTERING: '用于相似照片聚类',
    TaskType.FIND_DUPLICATE_PHOTOS: '用于扫描重复照片',
    TaskType.IMAGE_EMBEDDING: '用于生成图片的特征向量',
}

CATEGORY_NAME_MAP = {
    TaskType.SCAN_ALBUM: '扫描文件夹',
    TaskType.PROCESS_BASIC: '基本处理',
    TaskType.EXTRACT_METADATA: '元数据提取',
    TaskType.RECOGNIZE_FACE: '人脸识别',
    TaskType.RECOGNIZE_TICKET: '车票识别',
    TaskType.CLASSIFY_IMAGE: '场景识别',
    TaskType.VISUAL_DESCRIPTION: '大模型智能分析',
    TaskType.OCR: '文字识别',
    TaskType.SIMILAR_PHOTO_CLUSTERING: '相似照片清理',
    TaskType.FIND_DUPLICATE_PHOTOS: '重复照片清理',
    TaskType.IMAGE_EMBEDDING: '图片特征提取',
}

class TaskManager:
    """
    Task Producer / Manager (Runs in API process)
    Responsible for:
    1. Creating tasks
    2. Querying task status
    3. Managing pause/resume state via DB
    """
    _instance = None
    
    def __init__(self):
        self.paused_categories: Set[str] = set()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TaskManager()
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

    def get_status(self):
        """Get global scan status from DB"""
        return {
            'fast_mode': self._load_system_state('fast_mode', False)
        }

    def get_grouped_status(self, db: Session):
        """Get task counts grouped by category"""
        # Always refresh paused categories from DB
        paused_list = self._load_system_state('paused_categories', [])
        self.paused_categories = set(paused_list)

        stats = []
        # Define categories to show
        categories = [
            TaskType.PROCESS_BASIC,TaskType.EXTRACT_METADATA,
            TaskType.RECOGNIZE_FACE,TaskType.RECOGNIZE_TICKET,
            TaskType.CLASSIFY_IMAGE,TaskType.VISUAL_DESCRIPTION,
            TaskType.OCR,TaskType.IMAGE_EMBEDDING
        ]

        for cat in categories:
            # Find types belonging to this category
            pending = db.query(Task).filter(
                Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
                Task.type == cat
            ).count()

            # Completed is always 0 as we delete them
            completed = 0

            failed = db.query(Task).filter(
                Task.status == TaskStatus.FAILED,
                Task.type == cat
            ).count()

            stats.append({
                'task_name': CATEGORY_NAME_MAP.get(cat, cat),
                'category': cat,
                'pending': pending,
                'completed': completed,
                'failed': failed,
                'status': 'paused' if cat in self.paused_categories else 'active',
                'priority': DEFAULT_PRIORITIES.get(cat, 0),
                'description': CATEGORY_DESCRIPTION_MAP.get(cat, '')
            })

        # Sort by priority desc
        stats.sort(key=lambda x: x['priority'], reverse=True)
        return stats

    def pause_category(self, category: str):
        # Refresh first
        paused_list = self._load_system_state('paused_categories', [])
        self.paused_categories = set(paused_list)

        self.paused_categories.add(category)
        self._save_system_state('paused_categories', list(self.paused_categories))
        logging.info(f"Paused task category: {category}")

    def resume_category(self, category: str):
        # Refresh first
        paused_list = self._load_system_state('paused_categories', [])
        self.paused_categories = set(paused_list)

        if category in self.paused_categories:
            self.paused_categories.remove(category)
            self._save_system_state('paused_categories', list(self.paused_categories))
            logging.info(f"Resumed task category: {category}")

    def set_fast_mode(self, enabled: bool):
        self._save_system_state('fast_mode', enabled)
        logging.info(f"Fast Mode set to {enabled} via TaskManager")

    def add_task(self, db: Session, type: str, payload: dict, priority: int = 0, owner_id: UUID = None):
        if priority == 0:
            priority = DEFAULT_PRIORITIES.get(type, 0)

        task = Task(type=type, payload=payload, priority=priority, status=TaskStatus.PENDING, owner_id=owner_id)
        logging.info(f"Added task: {task.type} with priority {task.priority}")
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

            # Use task specific owner_id if present, otherwise use the common owner_id
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
