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

    def _register_downloads(self):
        def check_yolo_model():
            path = os.path.join(settings.MODEL_PATH, "photo-cls")
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading YOLO model SiYuan044/photo-cls to {path}...")
            return snapshot_download('SiYuan044/photo-cls', local_dir=path, revision='v0.1.1')

        def download_yolo_model():
            path = os.path.join(settings.MODEL_PATH, "photo-cls")
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading YOLO model SiYuan044/photo-cls to {path}...")
            return snapshot_download('SiYuan044/photo-cls', local_dir=path, revision='v0.1.1')

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
        Classify multiple base64 images using the YOLO model.
        Returns a list of prediction results.
        """
        if not model_downloader.is_ready("yolo_photo_cls"):
            raise Exception("YOLO model is not ready yet. Please try again later.")
            
        yolo_model = model_manager.get_model("yolo_photo_cls")
        
        results = []
        for b64 in images_base64:
            try:
                # Handle base64 header if present
                if ',' in b64:
                    b64 = b64.split(',')[1]
                image_data = base64.b64decode(b64)
                image = Image.open(io.BytesIO(image_data)).convert("RGB")
                
                # Run YOLO prediction
                preds = yolo_model(image)
                
                # Parse results
                img_result = []
                for pred in preds:
                    if hasattr(pred, 'probs') and pred.probs is not None:
                        probs = pred.probs
                        # YOLO classification typically gives top1 and top5
                        top5_indices = probs.top5
                        top5_conf = probs.top5conf
                        
                        for idx, conf in zip(top5_indices, top5_conf):
                            class_name = yolo_model.names[idx]
                            img_result.append({
                                "label": class_name,
                                "confidence": float(conf)
                            })
                results.append({"status": "success", "predictions": img_result})
            except Exception as e:
                logging.error(f"Error classifying image with YOLO: {e}\n{traceback.format_exc()}")
                results.append({"status": "error", "error": str(e)})
                
        return results

image_classification_service = ImageClassificationService()
