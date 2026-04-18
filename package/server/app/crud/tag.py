from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.schemas import tag as schemas
import uuid

def get_tag_by_name(db: Session, tag_name: str, owner_id: Optional[UUID] = None):
    query = db.query(PhotoTag).filter(PhotoTag.tag_name == tag_name, PhotoTag.is_deleted != True)
    if owner_id:
        query = query.filter((PhotoTag.owner_id == owner_id) | (PhotoTag.owner_id == None))
    else:
        query = query.filter(PhotoTag.owner_id == None)
    return query.first()

def create_tag(db: Session, tag_name: str, tag_type: str = None, owner_id: Optional[UUID] = None):
    db_tag = PhotoTag(tag_name=tag_name, type = tag_type, owner_id=owner_id)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

def get_photo_tags(db: Session, photo_id: UUID, owner_id: Optional[UUID] = None) -> List[schemas.PhotoTagResponse]:
    # Join PhotoTagRelation and PhotoTag
    query = db.query(PhotoTag, PhotoTagRelation.confidence)\
        .join(PhotoTagRelation, PhotoTag.id == PhotoTagRelation.tag_id)\
        .filter(PhotoTagRelation.photo_id == photo_id, PhotoTagRelation.is_deleted == False)

    if owner_id:
        query = query.filter((PhotoTag.owner_id == owner_id) | (PhotoTag.owner_id == None))
    else:
        query = query.filter(PhotoTag.owner_id == None)
        
    results = query.all()

    tags = []
    for tag, confidence in results:
        tags.append(schemas.PhotoTagResponse(
            id=tag.id,
            tag_name=tag.tag_name,
            confidence=confidence
        ))
    return tags

def add_tag_to_photo(db: Session, photo_id: UUID, tag_name: str, confidence: float = 1.0, owner_id: Optional[UUID] = None) -> schemas.PhotoTagResponse:
    # Check if tag exists
    tag = get_tag_by_name(db, tag_name, owner_id)
    if not tag:
        tag = create_tag(db, tag_name, 'custom', owner_id)

    # Check if relation exists
    relation = db.query(PhotoTagRelation).filter(
        PhotoTagRelation.photo_id == photo_id,
        PhotoTagRelation.tag_id == tag.id
    ).first()

    if relation:
        if relation.is_deleted:
            relation.is_deleted = False
            relation.confidence = confidence
            db.commit()
        else:
            # If manually added (confidence=1.0), overwrite existing confidence
            # Or if new confidence > old confidence (optional logic, but let's stick to simple override if manual)
            if confidence == 1.0:
                relation.confidence = 1.0
                db.commit()
        db.refresh(relation)
    else:
        relation = PhotoTagRelation(photo_id=photo_id, tag_id=tag.id, confidence=confidence)
        db.add(relation)
        db.commit()
        db.refresh(relation)
    
    return schemas.PhotoTagResponse(id=tag.id, tag_name=tag.tag_name, confidence=relation.confidence)

def remove_tag_from_photo(db: Session, photo_id: UUID, tag_id: UUID):
    relation = db.query(PhotoTagRelation).filter(
        PhotoTagRelation.photo_id == photo_id,
        PhotoTagRelation.tag_id == tag_id,
    ).first()

    if relation:
        db.delete(relation)
        db.commit()
    return True

def remove_tags_from_photo(db: Session, photo_id: UUID | str | List[UUID] | List[str], ai_generated: bool = False):
    if ai_generated:
        db.query(PhotoTagRelation).filter(
            (PhotoTagRelation.photo_id.in_(photo_id) if isinstance(photo_id, list) else PhotoTagRelation.photo_id == photo_id),
            PhotoTagRelation.confidence < 1.0
        ).delete()
    else:
        db.query(PhotoTagRelation).filter(
            (PhotoTagRelation.photo_id.in_(photo_id) if isinstance(photo_id, list) else PhotoTagRelation.photo_id == photo_id)
        ).delete()
    db.commit()
    return True

from sqlalchemy import func, desc
from app.db.models.photo import Photo

def get_tags_with_stats(db: Session, owner_id: UUID, skip: int = 0, limit: int = 100):
    # Subquery to count photos per tag
    subquery = db.query(
        PhotoTagRelation.tag_id,
        func.count(PhotoTagRelation.photo_id).label('count')
    ).join(Photo).filter(
        Photo.owner_id == owner_id,
        PhotoTagRelation.is_deleted == False
    ).group_by(PhotoTagRelation.tag_id).subquery()

    # Query tags joined with count
    tags_with_count = db.query(PhotoTag, subquery.c.count)\
        .join(subquery, PhotoTag.id == subquery.c.tag_id)\
        .filter(PhotoTag.is_deleted == False)\
        .order_by(desc(subquery.c.count))\
        .offset(skip).limit(limit).all()

    result = []
    for tag, count in tags_with_count:
        # Get latest photo for cover
        cover = None
        cover = db.query(Photo).filter(Photo.owner_id == owner_id).join(PhotoTagRelation, Photo.id == PhotoTagRelation.photo_id).filter(PhotoTagRelation.tag_id == tag.id).first()

        result.append(schemas.TagStats(
            id=tag.id,
            tag_name=tag.tag_name,
            count=count,
            cover=cover
        ))

    return result

def get_photos_by_tag_name(db: Session, owner_id: UUID, tag_name: str, skip: int = 0, limit: int = 50):
    tag = get_tag_by_name(db, tag_name, owner_id)
    if not tag:
        return []

    photos = db.query(Photo)\
        .join(PhotoTagRelation, Photo.id == PhotoTagRelation.photo_id)\
        .filter(
            Photo.owner_id == owner_id,
            PhotoTagRelation.tag_id == tag.id,
            PhotoTagRelation.is_deleted == False
        ).order_by(desc(Photo.photo_time))\
        .offset(skip).limit(limit).all()

    return photos
