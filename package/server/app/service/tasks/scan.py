from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import asyncio
import logging
import os
import re
import concurrent.futures
from typing import Set, Optional, Dict
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.photo import Photo, FileType
from app.db.models.index_log import IndexLog
from app.db.models.user import User
from app.service import storage
from app.core.config_manager import config_manager
from app.service.live_photo import live_photo_service

def scan_directory_recursive(path: str, exts: Set[str], filter_settings: Optional[Dict] = None) -> Set[str]:
    found = set()
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    if os.path.splitext(entry.name)[1].lower() in exts:
                        # Apply filters
                        if filter_settings and filter_settings.get('enable'):
                            # Filename patterns
                            patterns = filter_settings.get('filename_patterns', [])
                            should_skip = False
                            for pattern in patterns:
                                if not pattern:
                                    continue
                                try:
                                    if re.search(pattern, entry.name):
                                        should_skip = True
                                        break
                                except re.error:
                                    pass # Ignore invalid regex

                            if should_skip:
                                continue

                            # File size
                            min_size = filter_settings.get('min_size_kb', 0) * 1024
                            if min_size > 0 and entry.stat().st_size < min_size:
                                continue

                        found.add(entry.path)
                elif entry.is_dir():
                    found.update(scan_directory_recursive(entry.path, exts, filter_settings))
    except OSError:
        pass
    return found

@TaskStrategyFactory.register(TaskType.SCAN_FOLDER)
class ScanFolderStrategy(BaseTaskStrategy):
    async def process(self, worker, task: Task, db: Session):
        worker.scan_status['message'] = "Scanning folders..."
        scan_roots = task.payload.get('scan_roots')
        user_id = task.payload.get('user_id')

        user = None
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()

        if not scan_roots:
            if user:
                 scan_roots = user.settings.get('external_directories', []) if user.settings else []

            if not scan_roots and not user_id:
                root = storage._get_storage_root(str(user.id) if user else None, db)
                primary_uploads = os.path.join(root, 'uploads')
                # Fallback to empty if no user found (though user should be found or provided)
                external_dirs = []
                if user:
                     external_dirs = config_manager.get_user_config(user.id, db).storage.external_directories
                scan_roots = [primary_uploads] + external_dirs

        if scan_roots is None:
            scan_roots = []

        EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.tiff', '.gif', '.mp4', '.mov', '.avi', '.heic'}
        loop = asyncio.get_running_loop()
        logging.info(f"Scanning roots: {scan_roots}")

        token = None
        user_settings = dict(user.settings)
        filter_config = user_settings.get('filter', {})
        try:
            def parallel_scan_wrapper():
                found_files = set()
                work_items = []
                for root in scan_roots:
                    if not os.path.exists(root):
                        continue
                    work_items.append(root)
                    try:
                        with os.scandir(root) as it:
                            for entry in it:
                                if entry.is_dir():
                                    work_items.append(entry.path)
                    except OSError:
                        pass
                work_items = list(set(work_items))
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = {executor.submit(scan_directory_recursive, item, EXTS, filter_config): item for item in work_items}
                    for future in concurrent.futures.as_completed(futures):
                        found_files.update(future.result())
                return found_files

            files_on_disk = await loop.run_in_executor(None, parallel_scan_wrapper)

            existing_files = set()
            live_photo_files = set()
            live_photo_to_add = set()

            query = db.query(Photo.file_path, Photo.file_type).filter(Photo.owner_id==user_id)
            norm_paths = {os.path.normpath(path) for path in scan_roots}
            for p in query.all():
                is_exist = False
                for norm_path in norm_paths:
                    if os.path.normpath(p[0]).startswith(norm_path):
                        is_exist = True
                if not is_exist:
                    continue
                file_path = os.path.normpath(p[0]).lower()
                if p[1] == FileType.live_photo:
                    if file_path.endswith('.jpg'):
                        existing_files.add(p[0][:-3] + 'mp4')
                    elif file_path.endswith('.heic'):
                        existing_files.add(p[0][:-4] + 'MOV')
                elif file_path.endswith('.jpg') and (p[0][:-3] + 'mp4' in existing_files):
                    live_photo_to_add.add(p[0])
                elif file_path.endswith('.heic') and (p[0][:-4] + 'MOV' in existing_files):
                    live_photo_to_add.add(p[0])
                elif file_path.endswith('.mp4') and (p[0][:-3] + 'jpg' in existing_files):
                    live_photo_to_add.add(p[0])
                elif file_path.endswith('.mov') and (p[0][:-3] + 'HEIC' in existing_files):
                    live_photo_to_add.add(p[0])
                existing_files.add(p[0])
            # Determine new and deleted
            new_files = files_on_disk - existing_files
            deleted_files = existing_files - files_on_disk

            for lp in live_photo_to_add:
                if lp.endswith('.jpg'):
                    deleted_files.add(lp[:-3] + 'mp4')
                    new_files.add(lp[:-3] + 'mp4')
                elif lp.endswith('.mp4'):
                    deleted_files.add(lp[:-3] + 'jpg')
                    new_files.add(lp[:-3] + 'jpg')
                if lp.endswith('.HEIC'):
                    deleted_files.add(lp[:-4] + 'MOV')
                    new_files.add(lp[:-4] + 'MOV')
                elif lp.endswith('.MOV'):
                    deleted_files.add(lp[:-3] + 'HEIC')
                    new_files.add(lp[:-3] + 'HEIC')
                new_files.add(lp)
                deleted_files.add(lp)

            logging.info(f"Scan result: {len(new_files)} new, {len(deleted_files)} deleted")
            worker.scan_status['message'] = f"Found {len(new_files)} new, {len(deleted_files)} deleted"
            worker.scan_status['total_files'] += len(new_files)

            # Queue process tasks for new files
            new_tasks = []
            # Group files to identify Live Photos
            grouped_files = {}
            for fp in new_files:
                dirname, basename = os.path.split(fp)
                name, ext = os.path.splitext(basename)
                key = (dirname, name)
                if key not in grouped_files:
                    grouped_files[key] = {}
                grouped_files[key][ext.lower()] = fp

            processed_paths = set()
            for key, files in grouped_files.items():
                image_path = None
                video_path = None

                # Identify candidates for Live Photos
                if '.heic' in files:
                    image_path = files['.heic']
                elif '.jpg' in files:
                    image_path = files['.jpg']
                elif '.jpeg' in files:
                    image_path = files['.jpeg']

                if '.mov' in files:
                    video_path = files['.mov']
                elif '.mp4' in files:
                    video_path = files['.mp4']

                is_live = False
                final_video_path = None

                try:
                    # Must have both Image and Video, and they must share the Content Identifier
                    if image_path and video_path:
                         def check_live_pair(img, vid):
                             cid1 = live_photo_service.get_content_identifier(img)
                             cid2 = live_photo_service.get_content_identifier(vid)
                             return cid1 and cid2 and cid1 == cid2

                         if await loop.run_in_executor(None, check_live_pair, image_path, video_path):
                             is_live = True
                             final_video_path = video_path

                except Exception as e:
                    logging.error(f"Error checking live photo for {image_path}: {e}")

                if is_live:
                    new_tasks.append(Task(
                        type=TaskType.PROCESS_BASIC,
                        payload={
                            'file_path': image_path,
                            'live_photo_video_path': final_video_path,
                            'is_live_photo': True,
                            'user_id': user_id
                        },
                        priority=10,
                        status=TaskStatus.PENDING
                    ))
                    processed_paths.add(image_path)
                    if final_video_path:
                        processed_paths.add(final_video_path)

                # Add remaining files as individual tasks
                for ext, fp in files.items():
                    if fp not in processed_paths:
                        new_tasks.append(Task(
                            type=TaskType.PROCESS_BASIC,
                            payload={'file_path': fp, 'user_id': user_id},
                            priority=10,
                            status=TaskStatus.PENDING
                        ))
                        processed_paths.add(fp)

            if new_tasks:
                chunk_size = 1000
                for i in range(0, len(new_tasks), chunk_size):
                    db.bulk_save_objects(new_tasks[i:i+chunk_size])
                    db.commit()

            # Handle deleted
            if deleted_files:
                deleted_list = list(deleted_files)
                chunk_size = 500
                for i in range(0, len(deleted_list), chunk_size):
                    chunk = deleted_list[i:i+chunk_size]
                    photos_to_delete = db.query(Photo).filter(Photo.owner_id==user_id, Photo.file_path.in_(chunk)).all()
                    photo_ids_to_delete = []
                    for ph in photos_to_delete:
                        photo_ids_to_delete.append(ph.id)
                        db.add(IndexLog(action='deleted', file_path=ph.file_path, photo_id=ph.id, owner_id=user_id))
                
                    if photo_ids_to_delete:
                        from app.crud.photo import batch_delete_photos_db
                        batch_delete_photos_db(db, photo_ids_to_delete, is_delete_file=False, user_id=user_id)
                    
                    db.commit()
                    worker.scan_status['deleted'] += len(photos_to_delete)

            return {'new_files': len(new_files), 'deleted_files': len(deleted_files)}
        finally:
            if token:
                config_manager._user_config_ctx.reset(token)

def release_resources():
    pass
