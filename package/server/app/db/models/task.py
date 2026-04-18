from sqlalchemy import Column, String, Integer, JSON, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(str, enum.Enum):
    SCAN_FOLDER = "SCAN_FOLDER"
    PROCESS_BASIC = "PROCESS_BASIC"  # Basic info, thumbnail, preview
    # PROCESS_IMAGE = "PROCESS_IMAGE"  # Deprecated or Full Legacy
    GENERATE_THUMBNAIL = "GENERATE_THUMBNAIL"
    EXTRACT_METADATA = "EXTRACT_METADATA" # Heavy metadata, geolocation
    CLASSIFY_IMAGE = "CLASSIFY_IMAGE"
    RECOGNIZE_FACE = "RECOGNIZE_FACE"
    RECOGNIZE_TICKET = "RECOGNIZE_TICKET"
    REBUILD_THUMBNAILS = "REBUILD_THUMBNAILS"
    REBUILD_METADATA = "REBUILD_METADATA"
    OCR = "OCR"
    VISUAL_DESCRIPTION = "VISUAL_DESCRIPTION"
    SIMILAR_PHOTO_CLUSTERING = "SIMILAR_PHOTO_CLUSTERING"
    FIND_DUPLICATE_PHOTOS = "FIND_DUPLICATE_PHOTOS"
    IMAGE_EMBEDDING = "IMAGE_EMBEDDING"
    SCAN_ALBUM = "SCAN_ALBUM"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50), nullable=False)
    status = Column(String(20), default=TaskStatus.PENDING.value)
    priority = Column(Integer, default=0) # Higher number = Higher priority
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # Progress tracking
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)

    __table_args__ = (
        Index('ix_tasks_status_priority_created', 'status', 'priority', 'created_at'),
        Index('ix_tasks_type_status', 'type', 'status'),
    )

    def __str__(self):
        return f"Task(id: {self.id}, type: {self.type}, status: {self.status}, priority: {self.priority})"
