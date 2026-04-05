import asyncio
import logging
import os
import json
from uuid import UUID, uuid4
from PIL import Image
from pillow_heif import register_heif_opener

from app.core.config_manager import config_manager

# Register HEIF opener to enable HEIC/HEIF support in Pillow
register_heif_opener()
from sqlalchemy.orm import Session

from app.db.models.task import Task
from app.db.models.photo import FileType
from app.schemas.metadata import PhotoMetadataCreate
from app.service import storage
from app.utils import exif
from app.utils.hash import calculate_file_md5
from app.schemas import photo as photo_schemas
from app.utils import motion_photo

def process_basic_cpu_job(file_path: str, file_id: UUID, storage_root: str, user_id: str):
    """
    CPU-intensive task running in a separate process.
    Generates thumbnails and extracts BASIC metadata (no heavy geolocation).
    """
    try:
        # Initialize storage root cache in this process
        storage.update_storage_root_cache(user_id, storage_root)

        # Open image once if possible to reduce IO
        image_obj = None
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.heic'):
             try:
                 image_obj = Image.open(file_path)
             except Exception:
                 pass

        # 1. Generate thumbnail
        thumb_path = storage.generate_thumbnail(user_id, file_path, file_id, image_obj=image_obj)

        # 2. Extract metadata (BASIC ONLY)
        file_name = os.path.basename(file_path)
        meta = exif.extract_metadata(file_path, file_name, image_obj=image_obj, extract_location_details=False)
        if meta.get("exif_info"):
            # Serialize for storage
            # Convert non-serializable objects to string
            def default_serializer(obj):
                if isinstance(obj, (bytes, bytearray)):
                    return str(obj)
                return str(obj)
            meta['exif_info'] = json.dumps(meta["exif_info"], default=default_serializer, ensure_ascii=False)
        # 3. Get dimensions/size
        size = storage.get_file_size(file_path)
        width, height, duration = storage.get_image_dimensions(file_path, image_obj=image_obj)

        if image_obj:
            image_obj.close()

        # 4. Calculate MD5
        md5_hash = calculate_file_md5(file_path)

        # Check for Google Motion Photo and extract video
        is_motion_photo = False
        if ext in ('.jpg', '.jpeg'):
            video_path = motion_photo.extract_video(file_path, video_path=thumb_path[:-4] + '.mp4')
            if video_path:
                is_motion_photo = True

        return {
            "success": True,
            "thumb_path": thumb_path,
            "meta": meta,
            "size": size,
            "width": width,
            "height": height,
            "duration": duration,
            "file_name": file_name,
            "photo_create_data": None, # Placeholder
            "is_motion_photo": is_motion_photo,
            "md5_hash": md5_hash
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def handle_process_basic(task_manager, task: Task, db: Session):
    file_path = task.payload.get('file_path')
    live_photo_video_path = task.payload.get('live_photo_video_path')
    is_live_photo = task.payload.get('is_live_photo', False)
    user_id = task.payload.get('user_id')
    # Use task owner_id as fallback if user_id not in payload
    if not user_id and task.owner_id:
        user_id = str(task.owner_id)
        
    if not file_path or not os.path.exists(file_path):
        return {'status': 'skipped', 'reason': 'file not found'}

    photo_id = uuid4()
    storage_root = storage._get_storage_root(user_id, db)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        task_manager.thread_pool,
        process_basic_cpu_job,
        file_path,
        photo_id,
        storage_root,
        user_id
    )
    # result = process_basic_cpu_job(file_path, photo_id, storage_root)
    if not result['success']:
        raise Exception(result.get('error', 'Unknown error'))

    # Check resolution filter
    filter_config = config_manager.get_user_config(user_id, db).filter
    if filter_config.enable:
        if filter_config.min_width > 0 and result['width'] < filter_config.min_width:
             return {'status': 'skipped', 'reason': 'filtered_by_width'}
        if filter_config.min_height > 0 and result['height'] < filter_config.min_height:
             return {'status': 'skipped', 'reason': 'filtered_by_height'}

    # Construct PhotoCreate data for bulk insert in TaskManager
    meta = result['meta']
    ext = os.path.splitext(result['file_name'])[1]
    file_type = FileType.image
    if ext.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
        file_type = FileType.video
    if is_live_photo or result.get('is_motion_photo'):
        file_type = FileType.live_photo
    # We need to return raw data, not schemas, because bulk_create_photos expects dicts or similar?
    # Actually album_crud.batch_create_photos expects schemas.PhotoCreate
    photo_create = photo_schemas.PhotoCreate(
        file_type=file_type,
        size=result['size'],
        width=result['width'],
        height=result['height'],
        duration=result['duration'],
        filename=result['file_name'],
        photo_time=meta["photo_time"],
        md5=result.get('md5_hash')
    )

    metadata_create = PhotoMetadataCreate(
        exif_info=meta["exif_info"],
        # Basic task doesn't have location details yet
    )

    return {
        'photo_create_data': {
            'photo': photo_create,
            'metadata': metadata_create,
            'photo_id': photo_id,
            'file_path': file_path,
            'user_id': user_id
        }
    }

def release_resources():
    pass
