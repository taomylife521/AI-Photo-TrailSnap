from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.dependencies import get_db
from app.db.models.task import Task, TaskStatus, TaskType
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from app.service.task_manager import TaskManager
from app.crud import task as crud_task

router = APIRouter()

class TaskSchema(BaseModel):
    """任务详情返回模型"""
    id: UUID
    type: str
    status: str
    priority: int
    created_at: datetime
    updated_at: Optional[datetime]
    error: Optional[str]
    payload: Optional[Dict[str, Any]]
    total_items: Optional[int]
    processed_items: Optional[int]

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    """创建任务请求体"""
    type: str
    payload: Optional[Dict[str, Any]] = {}


@router.get("/", response_model=List[TaskSchema], summary="获取任务列表")
def list_tasks(
    status: str = None,
    type: str = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    分页查询任务列表，可按状态和类型过滤。
    默认按创建时间倒序返回前 50 条。
    """
    return crud_task.list_tasks(db, status=status, type=type, limit=limit)


@router.post("/fast-mode", summary="设置快速模式")
def set_fast_mode(enabled: bool = Body(..., embed=True)):
    """
    开启或关闭快速模式。
    快速模式下，系统将尝试同时运行 IO 密集型和 CPU 密集型任务，
    以最大化利用系统资源。
    """
    TaskManager.get_instance().set_fast_mode(enabled)
    return {"status": "success", "fast_mode": enabled}


@router.get("/status", summary="获取全局任务状态")
def get_status(db: Session = Depends(get_db)):
    """
    获取当前扫描状态和快速模式状态。
    """
    # return "hello world"
    return TaskManager.get_instance().get_status()


@router.get("/grouped-status", summary="按状态分组统计任务")
def get_grouped_status(db: Session = Depends(get_db)):
    """
    调用 TaskManager 获取按状态分组的任务统计信息。
    """
    return TaskManager.get_instance().get_grouped_status(db)


@router.post("/categories/{category}/pause", summary="暂停指定分类任务")
def pause_category(category: str):
    """
    暂停某一分类（category）下的所有待处理任务。
    """
    TaskManager.get_instance().pause_category(category)
    return {"status": "success"}


@router.post("/categories/{category}/resume", summary="恢复指定分类任务")
def resume_category(category: str):
    """
    恢复之前被暂停的某一分类（category）下的任务。
    """
    TaskManager.get_instance().resume_category(category)
    return {"status": "success"}


@router.get("/{task_id}", response_model=TaskSchema, summary="根据 ID 获取任务详情")
def get_task(task_id: UUID, db: Session = Depends(get_db)):
    """
    根据任务 UUID 返回任务详情；若任务不存在则返回空任务。
    """
    task = crud_task.get_task(db, task_id)
    if not task:
        # 任务不存在，返回空任务
        task = Task(
            id=task_id, status=TaskStatus.COMPLETED,
            priority = 0,
            type=TaskType.PROCESS_BASIC,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    return task


@router.post("/", response_model=TaskSchema, summary="创建新任务")
def create_task(task_in: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    创建一个新任务。
    - type：任务类型，需为系统支持的 TaskType 枚举值。
    - payload：可选，任务附加数据。
    若 type 非法则返回 400。
    """
    # Validate type
    task_in.payload['user_id'] = str(current_user.id)  # Ensure user_id is included in payload
    try:
        task_type = TaskType(task_in.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_in.type}")

    task = TaskManager.get_instance().add_task(db, task_in.type, task_in.payload, owner_id=current_user.id)
    return task


@router.post("/{task_id}/cancel", response_model=TaskSchema, summary="取消任务")
def cancel_task(task_id: UUID, db: Session = Depends(get_db)):
    """
    将指定任务状态置为 CANCELLED。
    仅允许取消处于待处理或运行中的任务；已完成、已失败或已取消的任务将返回 400。
    """
    task = crud_task.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Task is already finished")

    return crud_task.cancel_task(db, task)


@router.post("/{task_id}/retry", response_model=TaskSchema, summary="重试任务")
def retry_task(task_id: UUID, db: Session = Depends(get_db)):
    """
    重试失败的任务。
    """
    task = crud_task.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.FAILED:
         raise HTTPException(status_code=400, detail="Only failed tasks can be retried")
    
    task = TaskManager.get_instance().retry_task(db, task)
    return task


@router.post("/retry-all-failed", summary="重试所有失败任务")
def retry_all_failed_tasks(
    types: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """
    重试所有失败的任务。可选指定任务类型。
    """
    result = TaskManager.get_instance().retry_all_failed_tasks(db, types)
    return result


@router.delete("/failed", summary="删除失败任务")
def delete_failed_tasks(
    types: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """
    删除所有失败的任务。可选指定任务类型。
    """
    count = crud_task.delete_failed_tasks(db, types)
    return {"message": f"Deleted {count} failed tasks", "count": count}
