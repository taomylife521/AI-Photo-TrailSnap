import os
import re
from typing import Optional
from .base import LivePhotoParser

"""
vivo 实况图解析器
"""
class VivoLivePhotoParser(LivePhotoParser):
    def is_supported(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in ['.jpg', '.jpeg', '.mp4', '.mov']

    def parse(self, file_path: str) -> Optional[str]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            return self._parse_image(file_path)
        elif ext == '.mp4' or ext == '.mov':
            return self._parse_video(file_path)
        return None

    def _parse_image(self, file_path: str) -> Optional[str]:
        return file_path.replace('.jpg', '').replace('.jpeg', '')

    def _parse_video(self, file_path: str) -> Optional[str]:
        return file_path.replace('.mp4', '').replace('.mov', '')
