import traceback
import logging
import os
import io
import base64
from typing import List, Dict, Optional
from PIL import Image

from app.config import settings
from app.services.model_downloader import model_downloader
from app.services.model_manager import model_manager

class ImageClassificationService:
    def __init__(self):
        self._register_models()
        self._register_downloads()
        self.version = 'v0.1.2'

    def _register_downloads(self):
        def check_yolo_model():
            try:
                path = os.path.join(settings.MODEL_PATH, "photo-cls")
                if not os.path.exists(path):
                    return False
                # Check if the model file exists
                model_path = os.path.join(path, "photo-cls-general.pt")
                if not os.path.exists(model_path):
                    return False
                version_file = os.path.join(path, ".mv")
                if not os.path.exists(version_file):
                    return False
                with open(version_file, 'r') as f:
                    version = f.read().strip().split(',')[0].split(':')[1]
                if version != self.version:
                    return False
                return True
            except:
                return False

        def download_yolo_model():
            path = os.path.join(settings.MODEL_PATH, "photo-cls")
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading YOLO model SiYuan044/photo-cls to {path}...")
            return snapshot_download('SiYuan044/photo-cls', local_dir=path, revision=self.version)

        model_downloader.register_model("yolo_photo_cls", check_yolo_model, download_yolo_model)

    def _load_yolo_model(self):
        path = os.path.join(settings.MODEL_PATH, "photo-cls")
        # Try to find a .pt file
        model_path = os.path.join(path, "photo-cls-general.pt")
        if not os.path.exists(model_path):
            pt_files = [f for f in os.listdir(path) if f.endswith('.pt')]
            if pt_files:
                model_path = os.path.join(path, pt_files[0])
            else:
                raise FileNotFoundError(f"No .pt file found in {path}")
        from ultralytics import YOLO
        logging.info(f"Loading YOLO model from {model_path}")
        return YOLO(model_path)

    def _release_model(self, wrapper):
        """Release resources associated with the model"""
        model_name = getattr(wrapper, 'model_name', 'unknown')
        logging.info(f"Releasing resources for {model_name}")
        
        if hasattr(wrapper, 'model'):
            del wrapper.model
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _register_models(self):
        model_manager.register_model("yolo_photo_cls", self._load_yolo_model, self._release_model)

    async def classify_yolo(self, images_base64: List[str]) -> List[dict]:
        """
        真正的 YOLO 批量分类推理（支持多张并行加速）
        """
        if not model_downloader.is_ready("yolo_photo_cls"):
            raise Exception("YOLO model is not ready yet. Please try again later.")

        yolo_model = model_manager.get_model("yolo_photo_cls")
        results = []
        valid_images = []
        valid_indices = []

        # 1. 先把所有 base64 解码成 PIL Image（保留顺序）
        for idx, b64 in enumerate(images_base64):
            try:
                if ',' in b64:
                    b64 = b64.split(',')[1]
                image_data = base64.b64decode(b64)
                image = Image.open(io.BytesIO(image_data)).convert("RGB")
                valid_images.append(image)
                valid_indices.append(idx)
                results.append({"status": "success", "predictions": []})
            except Exception as e:
                logging.error(f"Image decode error: {e}")
                results.append({"status": "error", "error": str(e)})

        # 2. 没有有效图片直接返回
        if not valid_images:
            return results

        # 3. ✅ 真正批量推理（一次送入所有图片）
        preds_batch = yolo_model(valid_images)

        # 4. 解析批量结果并放回原顺序
        for res_idx, pred in enumerate(preds_batch):
            idx = valid_indices[res_idx]
            img_result = []

            if hasattr(pred, 'probs') and pred.probs is not None:
                top5_indices = pred.probs.top5
                top5_conf = pred.probs.top5conf

                for cls_idx, conf in zip(top5_indices, top5_conf):
                    class_name = yolo_model.names[cls_idx]
                    img_result.append({
                        "label": class_name,
                        "confidence": float(conf)
                    })

            results[idx]["predictions"] = img_result

        return results
image_classification_service = ImageClassificationService()
