import logging
import json
from typing import List, Dict, Set, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.system import SystemState
from app.crud import task as crud_task

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

        return crud_task.get_grouped_status(db, self.paused_categories)

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
        task = crud_task.add_task(db, type, payload, priority, owner_id)
        logging.info(f"Added task: {task.type} with priority {task.priority}")
        return task

    def add_tasks(self, db: Session, tasks_data: List[Dict], owner_id: UUID = None):
        """Batch add tasks"""
        crud_task.add_tasks(db, tasks_data, owner_id)
