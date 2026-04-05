from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any

from app.api.deps import get_current_user
from app.db.models.user import User
from app.dependencies import get_db
from app.db.models.photo import Photo
from app.db.models.task import TaskType, TaskStatus, Task
from app.service.task_manager import TaskManager
from app.schemas.photo import PhotoDetail as PhotoSchema
from pydantic import BaseModel

class DuplicatePhotoGroup(BaseModel):
    md5: str
    photos: List[PhotoSchema]

router = APIRouter()

@router.post("/duplicate-photos/scan")
def scan_duplicate_photos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    触发重复照片扫描任务。
    """
    # Check if there's already a pending or processing task
    existing_task = db.query(Task).filter(
        Task.owner_id == current_user.id,
        Task.type == TaskType.FIND_DUPLICATE_PHOTOS,
        Task.status.in_([TaskStatus.PENDING.value, TaskStatus.PROCESSING.value])
    ).first()

    if existing_task:
        return existing_task

    task = TaskManager.get_instance().add_task(
        db,
        type=TaskType.FIND_DUPLICATE_PHOTOS,
        payload={},
        owner_id=current_user.id
    )
    return task

@router.get("/duplicate-photos", response_model=List[DuplicatePhotoGroup])
def get_duplicate_photos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取重复照片列表，返回按 MD5 分组（组内照片数 > 1）的照片列表。
    """
    # Find MD5s that have more than 1 photo
    md5_counts = db.query(
        Photo.md5,
        func.count(Photo.id).label('count')
    ).filter(
        Photo.owner_id == current_user.id,
        Photo.md5.isnot(None),
        Photo.md5 != ""
    ).group_by(
        Photo.md5
    ).having(
        func.count(Photo.id) > 1
    ).all()

    if not md5_counts:
        return []

    duplicate_md5s = [row.md5 for row in md5_counts]

    # Fetch all photos with these MD5s
    photos = db.query(Photo).filter(
        Photo.owner_id == current_user.id,
        Photo.md5.in_(duplicate_md5s)
    ).order_by(Photo.photo_time.desc()).all()

    # Group photos by MD5
    grouped_photos: Dict[str, List[PhotoSchema]] = {}
    for photo in photos:
        md5 = photo.md5
        if md5 not in grouped_photos:
            grouped_photos[md5] = []
        # Convert DB model to Schema dict/object. We can just use the Pydantic model dump
        # Fastapi will automatically serialize Pydantic models returned in a list/dict, 
        # but here we construct the dict structure manually.
        grouped_photos[md5].append(photo)

    # Convert to list of groups
    result = []
    for md5, photo_list in grouped_photos.items():
        result.append({
            "md5": md5,
            "photos": photo_list
        })

    return result