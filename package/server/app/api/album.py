import logging
import traceback
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Form, BackgroundTasks
from sqlalchemy.orm import Session
import aiohttp

import app.crud.photo
from app.dependencies import get_db
from app.crud import album as crud
from app.schemas import album as schemas
from app.core.config_manager import config_manager
from app.service.tasks.album import scan_album_task
from app.api.deps import get_current_user
from app.db.models.user import User
from app.api.media import upload_photo_generic
from app.utils.embedding import async_get_embedding

router = APIRouter()

# Album Endpoints

@router.post("", response_model=schemas.Album)
async def create_album(album: schemas.AlbumCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query_embedding = None
    if album.type == 'smart' and album.description:
        query_embedding = await async_get_embedding(album.description, current_user.id, db)

    db_album = crud.create_album(db=db, album=album, query_embedding=query_embedding, user_id=current_user.id)
    
    # Trigger async scan for conditional/smart albums
    if db_album.type in ['conditional', 'smart']:
        background_tasks.add_task(scan_album_task, db_album.id)
        
    return db_album

@router.get("", response_model=List[schemas.Album])
def read_albums(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return crud.get_albums(db, skip=skip, limit=limit, user_id=current_user.id)

@router.get("/{album_id}", response_model=schemas.Album)
def read_album(album_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_album = crud.get_album(db, album_id=album_id, user_id=current_user.id)
    if db_album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    # Check if cover is set (relationship or ID)
    if db_album.cover_id is None:
        photos = app.crud.photo.get_photos(db, current_user.id, user_id=current_user.id)
        if photos:
            earliest = min(photos, key=lambda p: p.photo_time or p.upload_time)
            try:
                # Assign ID and refresh or assign object
                db_album.cover_id = earliest.id
                db_album.cover = earliest
                db.add(db_album)
                db.commit()
            except Exception:
                pass
    return db_album

@router.delete("/{album_id}", response_model=schemas.Album)
def delete_album(album_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check ownership first
    db_album = crud.get_album(db, album_id, user_id=current_user.id)
    if not db_album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if db_album.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this album")
        
    db_album = crud.delete_album(db, album_id=album_id)
    if db_album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return db_album

@router.put("/{album_id}", response_model=schemas.Album)
async def update_album(album_id: UUID, album: schemas.AlbumUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_album = crud.get_album(db, album_id, user_id=current_user.id)
    if not current_album:
        raise HTTPException(status_code=404, detail="Album not found")

    if current_album.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this album")

    query_embedding = None
    if current_album.type == 'smart':
        if album.description and album.description != current_album.description:
            query_embedding = await async_get_embedding(album.description, current_user.id, db)

    db_album = crud.update_album(db, album_id=album_id, album=album, query_embedding=query_embedding)
    
    # Trigger async scan for conditional/smart albums
    if db_album.type in ['conditional', 'smart']:
        background_tasks.add_task(scan_album_task, db_album.id)
        
    return db_album

@router.put("/{album_id}/cover", response_model=schemas.Album)
def set_album_cover(album_id: UUID, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    photo_id = payload.get('photo_id')
    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id required")
    db_album = crud.get_album(db, album_id=album_id, user_id=current_user.id)
    if not db_album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if db_album.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this album")

    photo = app.crud.photo.get_photo(db, UUID(str(photo_id)))
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    # Verify photo ownership if necessary, or assume if user can see photo they can set it?
    # For now, just check album ownership.
    
    db_album.cover_id = photo.id
    db_album.cover = photo
    db.commit()
    db.refresh(db_album)
    return db_album


@router.post("/{album_id}/photos", response_model=schemas.Photo)
async def upload_photo(
        album_id: UUID,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Check album permission
    album = crud.get_album(db, album_id, user_id=current_user.id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    if album.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to upload to this album")

    # Forward to generic handler
    # Note: upload_photo_generic needs to be imported if not available. 
    # It seems it was expected to be available or I need to import it.
    # Assuming it is available or will be imported.
    # Wait, I checked imports and it wasn't there. I should add import.
    # But for now, I update the signature.
    return await upload_photo_generic(album_id, file, db, current_user)


@router.get("/{album_id}/photos", response_model=List[schemas.Photo])
def read_photos(album_id: UUID, skip: int = 0, limit: int = 100, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return app.crud.photo.get_photos(db, album_id=album_id, skip=skip, limit=limit, start_time=start_time, end_time=end_time, user_id=current_user.id)


@router.delete("/{album_id}/photos/{photo_id}", response_model=schemas.Photo)
def delete_photo(album_id: UUID, photo_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check album ownership
    db_album = crud.get_album(db, album_id, user_id=current_user.id)
    if not db_album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if db_album.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to remove photos from this album")

    # Remove association
    count = crud.batch_update_album_association(db, [photo_id], album_id, 'remove_from_album')
    if count == 0:
        raise HTTPException(status_code=404, detail="Photo not in album or not found")

    return app.crud.photo.get_photo(db, photo_id)  # Return the photo