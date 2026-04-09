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

CATEGORY_MAP = {
    TaskType.SCAN_FOLDER: 'scanning',
    TaskType.PROCESS_BASIC: 'basic',
    TaskType.PROCESS_IMAGE: 'scanning', # Legacy
    TaskType.GENERATE_THUMBNAIL: 'scanning',
    TaskType.REBUILD_THUMBNAILS: 'scanning',

    TaskType.EXTRACT_METADATA: 'metadata',
    TaskType.REBUILD_METADATA: 'metadata',

    TaskType.RECOGNIZE_FACE: 'face',
    TaskType.RECOGNIZE_TICKET: 'tickets',
    TaskType.CLASSIFY_IMAGE: 'classification',
    TaskType.VISUAL_DESCRIPTION: 'ai',
    TaskType.OCR: 'ocr',
    TaskType.SIMILAR_PHOTO_CLUSTERING: 'similar',
    TaskType.FIND_DUPLICATE_PHOTOS: 'duplicate',
    TaskType.IMAGE_EMBEDDING: 'embedding',
}

CATEGORY_DESCRIPTION_MAP = {
    'scanning': '用于扫描文件夹中的文件',
    'basic': '用于基本文件处理',
    'metadata': '用于提取文件元数据（GPS位置、拍摄参数等）',
    'face': '用于识别图片中的人脸',
    'tickets': '用于识别火车票、飞机票等',
    'classification': '用于场景分类',
    'ai': '用于生成图片的视觉描述',
    'ocr': '用于识别图片中的文字',
    'similar': '用于相似照片聚类',
    'duplicate': '用于扫描重复照片',
    'embedding': '用于生成图片的特征向量',
}

CATEGORY_NAME_MAP = {
    'scanning': '扫描文件夹',
    'basic': '基本处理',
    'metadata': '元数据提取',
    'face': '人脸识别',
    'tickets': '车票识别',
    'classification': '场景识别',
    'ai': '大模型智能分析',
    'ocr': '文字识别',
    'similar': '相似照片清理',
    'duplicate': '重复照片清理',
    'embedding': '图片特征提取',
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
        self.category_map = CATEGORY_MAP

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
        categories = ['basic', 'metadata', 'face', 'classification', 'ocr', 'tickets', 'ai', 'embedding']

        # Priority map for categories (higher is better)
        cat_priority = {
            'basic': DEFAULT_PRIORITIES.get(TaskType.PROCESS_BASIC, 0),
            'metadata': DEFAULT_PRIORITIES.get(TaskType.EXTRACT_METADATA, 0),
            'face': DEFAULT_PRIORITIES.get(TaskType.RECOGNIZE_FACE, 0),
            'classification': DEFAULT_PRIORITIES.get(TaskType.CLASSIFY_IMAGE, 0),
            'ocr': DEFAULT_PRIORITIES.get(TaskType.OCR, 0),
            'tickets': DEFAULT_PRIORITIES.get(TaskType.RECOGNIZE_TICKET, 0),
            'ai': DEFAULT_PRIORITIES.get(TaskType.VISUAL_DESCRIPTION, 0),
            'similar': DEFAULT_PRIORITIES.get(TaskType.SIMILAR_PHOTO_CLUSTERING, 0),
            'duplicate': DEFAULT_PRIORITIES.get(TaskType.FIND_DUPLICATE_PHOTOS, 0),
            'embedding': DEFAULT_PRIORITIES.get(TaskType.IMAGE_EMBEDDING, 0),
        }

        for cat in categories:
            # Find types belonging to this category
            types = [t for t, c in self.category_map.items() if c == cat]
            pending = db.query(Task).filter(
                Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
                Task.type.in_(types)
            ).count()

            # Completed is always 0 as we delete them
            completed = 0

            failed = db.query(Task).filter(
                Task.status == TaskStatus.FAILED,
                Task.type.in_(types)
            ).count()

            stats.append({
                'task_name': CATEGORY_NAME_MAP.get(cat, cat),
                'category': cat,
                'pending': pending,
                'completed': completed,
                'failed': failed,
                'status': 'paused' if cat in self.paused_categories else 'active',
                'priority': cat_priority.get(cat, 0),
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
