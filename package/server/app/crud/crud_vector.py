from sqlalchemy.orm import Session
from app.db.models.image_vector import ImageVector
from app.db.models.photo import Photo
from typing import List, Optional, Any
from uuid import UUID
from pgvector.sqlalchemy import Vector

def create_or_update_vector(db: Session, photo_id: UUID, embedding: List[float], model_name: str = "clip-ViT-B-32"):
    """
    Create or update an image vector.
    """
    db_obj = db.query(ImageVector).filter(ImageVector.photo_id == photo_id).first()
    if db_obj:
        db_obj.embedding = embedding
        db_obj.model_name = model_name
    else:
        db_obj = ImageVector(photo_id=photo_id, embedding=embedding, model_name=model_name)
        db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_vector(db: Session, photo_id: UUID) -> Optional[ImageVector]:
    return db.query(ImageVector).filter(ImageVector.photo_id == photo_id).first()

def search_similar_vectors(db: Session, embedding: List[float], limit: int = 10, offset: int = 0, threshold: float = None, user_id: UUID = None) -> list[
    type[ImageVector]]:
    """
    Search for similar vectors using cosine distance (l2_distance is default for pgvector but usually cosine is preferred for CLIP).
    Actually, for normalized vectors (like CLIP), L2 distance and Cosine distance are related.
    pgvector supports <=> (cosine distance), <-> (L2 distance), <#> (inner product).
    CLIP embeddings are usually normalized, so inner product is cosine similarity.
    However, pgvector's cosine distance operator <=> returns 1 - cosine_similarity.
    """
    # Using cosine distance operator <=>
    # Order by distance ascending
    distance = ImageVector.embedding.cosine_distance(embedding).label("distance")
    query = db.query(ImageVector, distance)

    if user_id:
        query = query.join(Photo, ImageVector.photo_id == Photo.id).filter(Photo.owner_id == user_id, Photo.is_deleted == False)

    query = query.order_by(distance).offset(offset).limit(limit)
    
    results = query.all()
    # Returns list of (ImageVector, distance) tuples
    return results
