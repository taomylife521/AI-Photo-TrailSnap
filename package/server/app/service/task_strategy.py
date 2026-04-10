import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Type
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType

class BaseTaskStrategy(ABC):
    """
    Base strategy class for processing background tasks.
    Each specific task type should implement its own strategy inheriting from this class.
    """

    @abstractmethod
    async def process(self, worker, task: Task, db: Session) -> Any:
        """
        Process a single task. This method should handle the actual execution of the task.
        It should return a result dictionary, or raise an exception on failure.
        """
        pass

    async def handle_completion(self, worker, items: List[Dict], db: Session) -> None:
        """
        Callback triggered when a batch of tasks of this type has completed.
        Can be used to process successful results, create subsequent tasks, update stats, etc.
        `items` contains a list of dictionaries with keys: 'task_id', 'task_type', 'status', 'result', 'error'.
        """
        pass

    def release_resources(self) -> None:
        """
        Release any resources (like memory, loaded models) specific to this task type.
        Called when the task type has been idle for a period of time.
        """
        pass

class TaskStrategyFactory:
    """
    Factory for managing and retrieving task strategies.
    """
    _strategies: Dict[TaskType, BaseTaskStrategy] = {}

    @classmethod
    def register(cls, task_type: TaskType):
        """
        Decorator to register a strategy class for a specific task type.
        """
        def wrapper(strategy_cls: Type[BaseTaskStrategy]):
            cls._strategies[task_type] = strategy_cls()
            return strategy_cls
        return wrapper

    @classmethod
    def get_strategy(cls, task_type: TaskType) -> BaseTaskStrategy:
        """
        Retrieve the strategy instance for a given task type.
        """
        return cls._strategies.get(task_type)

    @classmethod
    def release_all_resources(cls):
        """
        Release resources for all registered strategies.
        """
        for strategy in cls._strategies.values():
            try:
                strategy.release_resources()
            except Exception as e:
                logging.error(f"Error releasing resources for strategy: {e}")
