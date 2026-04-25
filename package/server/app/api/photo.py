#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/12/7 23:20
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-photo.py
@Description : 
"""
import logging
import time
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

import app.crud.photo
from app.core.config_manager import config_manager
from app.crud.photo import save_and_create_photo
from app.dependencies import get_db
from app.crud import album as crud_album
from app.crud import face as crud_face
from app.crud import tag as crud_tag
from app.crud import task as crud_task

from app.schemas import photo as schemas
from app.schemas.metadata import PhotoMetadata, PhotoMetadataUpdate, PhotoDetail
from app.schemas import tag as tag_schemas
from app.service import storage
from app.service.task_manager import TaskManager
from app.db.models.task import TaskType
from app.api.deps import get_current_user
from app.db.models.user import User
import uuid
import os
import shutil

from app.db.models.image_description import ImageDescription as ImageDescriptionModel
from app.schemas.image_description import ImageDescription as ImageDescriptionSchema
from app.db.models.photo import Photo
from app.service.similar_photo import SimilarPhotoService
from app.db.models.task import Task, TaskType, TaskStatus
from app.schemas.task import TaskResponse
from app.db.models.cluster import ImageCluster, PhotoCluster

router = APIRouter()

# Photo Endpoints

@router.post("/similar/tasks", response_model=TaskResponse)
def create_similar_photo_task(
    threshold: float = 0.9,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new similar photo clustering task
    """
    task = TaskManager.get_instance().add_task(
        db,
        type=TaskType.SIMILAR_PHOTO_CLUSTERING,
        payload={"threshold": threshold},
        owner_id=current_user.id
    )
    return task

@router.get("/similar/tasks/latest", response_model=Optional[TaskResponse])
def get_latest_similar_task(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the latest similar photo clustering task
    """
    task = crud_task.get_latest_task_by_type_and_owner(
        db, TaskType.SIMILAR_PHOTO_CLUSTERING, current_user.id,
        [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]
    )
    
    if task:
        return task

    # If no pending/processing task, check ImageCluster for the latest task_id
    latest_cluster = db.query(ImageCluster).join(
        PhotoCluster, ImageCluster.cluster_id == PhotoCluster.cluster_id
    ).join(
        Photo, PhotoCluster.photo_id == Photo.id
    ).filter(
        Photo.owner_id == current_user.id,
        ImageCluster.cluster_type == "SIMILARITY"
    ).order_by(ImageCluster.created_at.desc()).first()

    if latest_cluster and latest_cluster.task_id:
        try:
            task_id_uuid = UUID(latest_cluster.task_id)
        except ValueError:
            return None
            
        return TaskResponse(
            id=task_id_uuid,
            type=TaskType.SIMILAR_PHOTO_CLUSTERING,
            status=TaskStatus.COMPLETED.value,
            created_at=latest_cluster.created_at,
            updated_at=latest_cluster.created_at,
            total_items=0,
            processed_items=0,
            result=None
        )
        
    return None

@router.get("/similar/tasks/{task_id}", response_model=TaskResponse)
def get_similar_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the status of a specific similar photo clustering task
    """
    task = crud_task.get_task_by_id_and_owner(db, task_id, current_user.id)
    
    if task:
        return task
        
    # If not in Task table, it was either completed or deleted.
    # We assume it's completed.
    return TaskResponse(
        id=task_id,
        type=TaskType.SIMILAR_PHOTO_CLUSTERING,
        status=TaskStatus.COMPLETED.value,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        total_items=0,
        processed_items=0,
        result=None
    )

@router.get("/similar/tasks/{task_id}/result", response_model=List[List[schemas.Photo]])
def get_similar_task_result(
    task_id: UUID,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the result of a similar photo clustering task
    """
    result = []
    current_skip = skip
    # Safety break to avoid infinite loops
    max_loops = 100 
    loop_count = 0
    
    while len(result) < limit and loop_count < max_loops:
        loop_count += 1
        
        # Calculate how many more we need
        remaining_needed = limit - len(result)
        # Fetch at least 20 or remaining_needed to be efficient
        fetch_limit = max(remaining_needed, 20)
        
        clusters = db.query(ImageCluster).filter(
            ImageCluster.task_id == str(task_id),
            ImageCluster.cluster_type == "SIMILARITY"
        ).order_by(ImageCluster.created_at.desc()).offset(current_skip).limit(fetch_limit).all()

        if not clusters:
            break

        processed_count = 0
        deleted_count = 0
        
        for cluster in clusters:
            # If we have enough results, we stop adding to result,
            # but we simply break and let the offset calculation handle the next page start.
            if len(result) >= limit:
                break
                
            processed_count += 1
            
            photo_clusters = db.query(PhotoCluster).filter(PhotoCluster.cluster_id == cluster.cluster_id).all()
            photo_ids = [pc.photo_id for pc in photo_clusters]

            should_delete = False
            cluster_photos = []
            
            if not photo_ids:
                should_delete = True
            else:
                photos_query = db.query(Photo, ImageDescriptionModel).outerjoin(
                    ImageDescriptionModel, Photo.id == ImageDescriptionModel.photo_id
                ).filter(
                    Photo.id.in_(photo_ids),
                    Photo.owner_id == current_user.id
                ).all()

                for photo, desc in photos_query:
                    score = 0
                    if desc:
                        score = (desc.memory_score or 0) + (desc.quality_score or 0)
                    
                    cluster_photos.append((photo, score))
                
                # Sort by score desc, then photo_time desc
                cluster_photos.sort(key=lambda x: (x[1], x[0].photo_time or datetime.min), reverse=True)
                
                if len(cluster_photos) < 2:
                    should_delete = True
            
            if should_delete:
                # Delete invalid cluster
                db.delete(cluster)
                # Commit to ensure DB state reflects deletion for next query or consistency
                db.commit() 
                deleted_count += 1
            else:
                result.append([x[0] for x in cluster_photos])
        
        # Update current_skip for the next iteration or next page logic
        # logic: we advanced 'processed_count' positions in the original list,
        # but 'deleted_count' items were removed, so the DB shifts.
        # Next item is at 'current_skip + processed_count - deleted_count'
        current_skip = current_skip + processed_count - deleted_count

    return result

@router.delete("/similar/tasks/{task_id}")
def cancel_similar_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cancel/Delete a similar photo clustering task
    """
    task = crud_task.get_task_by_id_and_owner(db, task_id, current_user.id)
    
    if task:
        if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            task.status = TaskStatus.CANCELLED
            # Note: This doesn't stop the running thread immediately if it's processing, 
            # but TaskWorker should handle cancellation check.
        crud_task.delete_task(db, task)
    else:
        # Check if it exists in ImageCluster
        clusters = db.query(ImageCluster).filter(ImageCluster.task_id == str(task_id)).all()
        if not clusters:
            raise HTTPException(status_code=404, detail="Task not found")
        for cluster in clusters:
            db.delete(cluster)
            
    db.commit()
    return {"message": "Task deleted"}

@router.get("/similar", response_model=List[List[schemas.SimilarPhoto]], deprecated=True)
def get_similar_photos(
    threshold: float = 0.9,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"Getting similar photos with threshold {threshold} for user {current_user.id}")
    service = SimilarPhotoService(db, str(current_user.id))
    return service.get_similar_groups(threshold)

@router.get("/recycle-bin", response_model=List[schemas.Photo])
def get_recycle_bin(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return app.crud.photo.get_recycle_bin_photos(db, user_id=current_user.id, skip=skip, limit=limit)

@router.post("/recycle-bin/restore")
def restore_recycle_bin_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not batch_data.photo_ids:
        raise HTTPException(status_code=400, detail="No photo IDs provided")
    count = app.crud.photo.restore_photos(db, batch_data.photo_ids, user_id=current_user.id)
    return {"message": f"Successfully restored {count} photos"}

@router.delete("/recycle-bin/permanent")
def permanently_delete_recycle_bin_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not batch_data.photo_ids:
        raise HTTPException(status_code=400, detail="No photo IDs provided")
    count = app.crud.photo.batch_delete_photos_db(db, batch_data.photo_ids, is_delete_file=True, user_id=current_user.id)
    return {"message": f"Successfully permanently deleted {count} photos"}

@router.get("/cleanup", response_model=List[schemas.Photo])
def get_photos_for_cleanup(
    skip: int = 0,
    limit: int = 50,
    sort_by: str = "asc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Join with ImageDescription to access scores
    query = db.query(Photo).join(ImageDescriptionModel, Photo.id == ImageDescriptionModel.photo_id).filter(Photo.owner_id == current_user.id, Photo.is_deleted == False)

    # Calculate score: memory_score + quality_score
    # We use coalesce to treat nulls as 0
    score_expr = func.coalesce(ImageDescriptionModel.memory_score, 0) + func.coalesce(ImageDescriptionModel.quality_score, 0)

    if sort_by == "desc":
        query = query.order_by(score_expr.desc())
    else:
        query = query.order_by(score_expr.asc())

    photos = query.offset(skip).limit(limit).all()
    return photos


@router.get("", response_model=List[schemas.Photo])
def read_all_photos(
        skip: int = 0,
        limit: int = 100,
        album_id: Optional[UUID] = None,
        album_ids: Optional[List[UUID]] = Query(None),
        face_id: Optional[UUID] = None,
        face_ids: Optional[List[UUID]] = Query(None),
        tag_id: Optional[UUID] = None,
        tag_ids: Optional[List[UUID]] = Query(None),
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        years: Optional[List[int]] = Query(None),
        city: Optional[str] = None,
        cities: Optional[List[str]] = Query(None),
        province: Optional[str] = None,
        provinces: Optional[List[str]] = Query(None),
        country: Optional[str] = None,
        countries: Optional[List[str]] = Query(None),
        make: Optional[str] = None,
        makes: Optional[List[str]] = Query(None),
        model: Optional[str] = None,
        models: Optional[List[str]] = Query(None),
        image_type: Optional[str] = None,
        image_types: Optional[List[str]] = Query(None),
        file_type: Optional[str] = None,
        file_types: Optional[List[str]] = Query(None),
        tag: Optional[str] = None,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lng_min: Optional[float] = None,
        lng_max: Optional[float] = None,
        radius: Optional[float] = None,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        ids: Optional[List[UUID]] = Query(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    st_time = time.time()
    photos = app.crud.photo.get_all_photos(
        db, skip=skip, limit=limit, start_time=start_time, end_time=end_time,
        years=years, city=city, cities=cities, province=province, provinces=provinces, country=country, countries=countries, 
        make=make, makes=makes, model=model, models=models, 
        image_type=image_type, image_types=image_types, 
        file_type=file_type, file_types=file_types,
        tag=tag, album_id=album_id, album_ids=album_ids,
        face_id=face_id, face_ids=face_ids, tag_id=tag_id, tag_ids=tag_ids,
        lat_min=lat_min, lat_max=lat_max, lng_min=lng_min, lng_max=lng_max,
        radius=radius, center_lat=center_lat, center_lng=center_lng,
        ids=ids, user_id=current_user.id
    )
    logging.info(f"read_all_photos time: {time.time() - st_time}")
    return photos


@router.post("/batch/create")
def batch_create_photos(
    batch_data: schemas.BatchPhotoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Convert schema to dict list expected by crud
    photos_data = []
    for item in batch_data.items:
        photos_data.append({
            'photo': item.photo,
            'file_path': item.file_path,
            'photo_id': item.photo_id,
        })
    try:
        count = app.crud.photo.batch_create_photos(db, photos_data, user_id=current_user.id)
        return {"message": f"Successfully created {count} photos"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
def batch_update_photos(
        batch_data: schemas.BatchPhotoUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if batch_data.action in ['add_to_album', 'remove_from_album']:

        if not batch_data.album_id:
            raise HTTPException(status_code=400, detail="Album ID required for this action")

        if batch_data.action == 'add_to_album':
            # Verify album exists
            db_album = crud_album.get_album(db, album_id=batch_data.album_id, user_id=current_user.id)
            if not db_album:
                raise HTTPException(status_code=404, detail="Target album not found")

        count = crud_album.batch_update_album_association(db, batch_data.photo_ids, batch_data.album_id, batch_data.action, user_id=current_user.id)
        return {"message": f"Successfully updated {count} photos"}

    elif batch_data.action == 'delete':
        app.crud.photo.batch_soft_delete_photos(db, batch_data.photo_ids, user_id=current_user.id)
        return {"message": "Photos moved to recycle bin successfully"}

    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@router.delete("/batch")
def batch_delete_photos(
    batch_data: schemas.BatchPhotoDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    count = app.crud.photo.batch_soft_delete_photos(db, batch_data.photo_ids, user_id=current_user.id)
    return {"message": f"Successfully moved {count} photos to recycle bin"}


@router.delete("/{photo_id}", response_model=schemas.Photo)
def delete_photo_global(photo_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    app.crud.photo.batch_soft_delete_photos(db, [photo_id], user_id=current_user.id)
    # Fetch it again to return, or just return an empty response. Wait, return the deleted photo object.
    db_photo = app.crud.photo.get_photo(db, photo_id, include_deleted=True)
    return db_photo


@router.put("/{photo_id}", response_model=schemas.Photo)
def update_photo(photo_id: UUID, photo: schemas.PhotoUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_photo = app.crud.photo.update_photo(db, photo_id, photo, user_id=current_user.id)
    if not db_photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return db_photo


# Metadata Endpoints

@router.get("/{photo_id}/metadata", response_model=PhotoMetadata)
def get_photo_metadata(photo_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_metadata = app.crud.photo.get_photo_metadata(db, photo_id=photo_id, user_id=current_user.id)

    if not db_metadata:
        raise HTTPException(status_code=404, detail="Metadata not found")
    photo = app.crud.photo.get_photo(db, photo_id=photo_id, include_deleted=True)
    albums = crud_album.get_albums_by_photo_id(db, photo_id=photo_id)
    faces_identities = crud_face.get_identities_by_photo_id(db, photo_id=photo_id)
    tags = crud_tag.get_photo_tags(db, photo_id=photo_id, owner_id=current_user.id)

    photo_metadata = PhotoMetadata.model_validate(db_metadata)
    photo_metadata.file_path = photo.file_path
    photo_metadata.albums = albums
    photo_metadata.faces_identities = faces_identities
    photo_metadata.tags = tags

    return photo_metadata


@router.put("/{photo_id}/metadata", response_model=PhotoMetadata)
def update_photo_metadata(
        photo_id: UUID,
        metadata: PhotoMetadataUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    result = app.crud.photo.update_photo_metadata(db, photo_id=photo_id, metadata=metadata, user_id=current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Photo not found or access denied")
    return result


# Tag Endpoints

@router.get("/{photo_id}/tags", response_model=List[tag_schemas.PhotoTagResponse])
def get_photo_tags(photo_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return crud_tag.get_photo_tags(db, photo_id, owner_id=current_user.id)


@router.post("/{photo_id}/tags", response_model=tag_schemas.PhotoTagResponse)
def add_photo_tag(photo_id: UUID, tag_data: tag_schemas.PhotoTagAdd, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    photo = app.crud.photo.get_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    return crud_tag.add_tag_to_photo(db, photo_id, tag_data.tag_name, tag_data.confidence, owner_id=current_user.id)


@router.delete("/{photo_id}/tags/{tag_id}")
def delete_photo_tag(photo_id: UUID, tag_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    photo = app.crud.photo.get_photo(db, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    crud_tag.remove_tag_from_photo(db, photo_id, tag_id)
    return {"message": "Tag deleted successfully"}

@router.get("/{photo_id}/description", response_model=Optional[ImageDescriptionSchema], summary="获取图片描述")
def get_photo_description(
    photo_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    desc = db.query(ImageDescriptionModel).filter(
        ImageDescriptionModel.photo_id == photo_id
    ).first()
    
    # Check ownership via photo
    if desc:
        photo = db.query(Photo).filter(Photo.id == photo_id).first()
        if not photo or photo.owner_id != current_user.id:
             raise HTTPException(status_code=403, detail="Not authorized")
    
    return desc


@router.get("/on-this-day", response_model=List[PhotoDetail])
def get_on_this_day_photos(
    month: Optional[int] = None,
    day: Optional[int] = None,
    year: Optional[int] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取那年今日的照片
    """
    if month is None or day is None or year is None:
        now = datetime.now()
        month = month or now.month
        day = day or now.day
        year = year or now.year

    return app.crud.photo.get_on_this_day_photos(db, user_id=current_user.id, month=month, day=day, year=year, limit=limit)
