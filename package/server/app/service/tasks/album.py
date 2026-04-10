import logging
from uuid import UUID
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.crud import album as crud_album
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import Photo
from app.db.models.task import Task, TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory

logger = logging.getLogger(__name__)

@TaskStrategyFactory.register(TaskType.SCAN_ALBUM)
class ScanAlbumStrategy(BaseTaskStrategy):
    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        """
        Background task to scan photos matching album conditions and update album_photos table.
        """
        album_id = UUID(task.payload.get('album_id'))
        try:
            album = crud_album.get_album(db, album_id)
            if not album:
                logger.warning(f"Album {album_id} not found during scan task")
                return {'status': 'skipped', 'reason': 'album not found'}

            # Only process conditional and smart albums
            # User albums are manually managed
            if album.type not in ['conditional', 'smart']:
                return {'status': 'skipped', 'reason': 'manual album'}

            logger.info(f"Starting scan for album {album_id} ({album.type})")

            # 1. Get photos matching the condition
            # This uses the dynamic query logic in crud.album
            query = crud_album._build_album_query(db, album)
            matching_photos = query.all()
            matching_photo_ids = {p.id for p in matching_photos}

            # 2. Get existing photos in album_photos
            existing_relations = db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album_id).all()
            existing_photo_ids = {r.photo_id for r in existing_relations}

            # 3. Calculate diff
            to_add = matching_photo_ids - existing_photo_ids
            to_remove = existing_photo_ids - matching_photo_ids

            logger.info(f"Album {album_id}: Found {len(matching_photo_ids)} matches. Adding {len(to_add)}, removing {len(to_remove)}")

            # 4. Add new
            if to_add:
                new_relations = [
                    AlbumPhoto(album_id=album_id, photo_id=pid)
                    for pid in to_add
                ]
                db.add_all(new_relations)

            # 5. Remove old
            if to_remove:
                db.query(AlbumPhoto).filter(
                    AlbumPhoto.album_id == album_id,
                    AlbumPhoto.photo_id.in_(to_remove)
                ).delete(synchronize_session=False)

            # Commit changes to album_photos
            db.commit()

            # 6. Update album stats (num_photos)
            # Refresh album to ensure we have latest state
            db.refresh(album)
            album.num_photos = len(matching_photo_ids)

            # 7. Update cover if needed (if no cover set, use the earliest photo)
            if matching_photos and  (not album.cover_id or album.cover_id not in matching_photo_ids):
                # Find earliest
                earliest = min(matching_photos, key=lambda p: p.photo_time or p.upload_time)
                album.cover_id = earliest.id

            if not matching_photos:
                album.cover_id = None

            db.add(album)
            db.commit()

            logger.info(f"Finished scan for album {album_id}")
            return {'status': 'success', 'added': len(to_add), 'removed': len(to_remove)}

        except Exception as e:
            logger.error(f"Error scanning album {album_id}: {e}")
            db.rollback()
            raise e
