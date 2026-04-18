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
    _LABEL_TO_CHINESE: Dict[str, str] = {
        "animal": "动物",
        "dog": "狗",
        "cat": "猫",
        "bird": "鸟",
        "person": "人物",
        "children": "儿童",
        "people": "人物",
        "selfie": "自拍",
        "scenery": "风景",
        "architecture": "建筑",
        "sunset": "日落",
        "night": "夜景",
        "moon": "月亮",
        "document": "文档",
        "id_card": "卡证",
        "train_ticket": "火车票",
        "train_ticket_screenshot": "火车票截图",
        "flight_ticket_screenshot": "机票截图",
        "movie_ticket": "电影票",
        "movie_ticket_screenshot": "电影票截图",
        "food": "食物",
        "car": "汽车",
        "plant": "植物",
        "electronics": "电子产品",
    }

    def __init__(self):
        self._category_model_map = self._discover_category_models()
        self._register_models()
        self._register_downloads()
        self.version = 'v0.1.3'

    def _translate_label(self, label: str) -> str:
        return self._LABEL_TO_CHINESE.get(label, label)

    def _discover_category_models(self) -> Dict[str, str]:
        path = os.path.join(settings.MODEL_PATH, "photo-cls")
        if not os.path.exists(path):
            return {}
        category_map = {}
        for f in os.listdir(path):
            if f.startswith("photo-cls-") and f.endswith(".pt") and f != "photo-cls-general.pt":
                category = f.replace("photo-cls-", "").replace(".pt", "")
                category_map[category] = f
        return category_map

    def _register_downloads(self):

        def check_general_model():
            try:
                path = os.path.join(settings.MODEL_PATH, "photo-cls")
                if not os.path.exists(path):
                    return False
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

        def download_general_model():
            path = os.path.join(settings.MODEL_PATH, "photo-cls")
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading YOLO model SiYuan044/photo-cls to {path}...")
            return snapshot_download('SiYuan044/photo-cls', local_dir=path, revision=self.version)

        model_downloader.register_model("yolo_photo_cls_general", check_general_model, download_general_model)

        for category, model_file in self._category_model_map.items():
            model_key = f"yolo_photo_cls_{category}"

            def make_check(model_file=model_file):
                def check():
                    try:
                        path = os.path.join(settings.MODEL_PATH, "photo-cls")
                        model_path = os.path.join(path, model_file)
                        return os.path.exists(model_path)
                    except:
                        return False
                return check

            def make_download(model_file=model_file):
                def download():
                    return os.path.join(settings.MODEL_PATH, "photo-cls", model_file)
                return download

            model_downloader.register_model(model_key, make_check(), make_download())

    def _load_general_model(self):
        path = os.path.join(settings.MODEL_PATH, "photo-cls")
        model_path = os.path.join(path, "photo-cls-general.pt")
        if not os.path.exists(model_path):
            pt_files = [f for f in os.listdir(path) if f.endswith('.pt') and 'general' in f]
            if pt_files:
                model_path = os.path.join(path, pt_files[0])
            else:
                raise FileNotFoundError(f"No general model found in {path}")
        from ultralytics import YOLO
        logging.info(f"Loading YOLO general model from {model_path}")
        return YOLO(model_path)

    def _load_category_model(self, category: str):
        model_file = self._category_model_map.get(category)
        if not model_file:
            return None
        path = os.path.join(settings.MODEL_PATH, "photo-cls")
        model_path = os.path.join(path, model_file)
        if not os.path.exists(model_path):
            return None
        from ultralytics import YOLO
        logging.info(f"Loading YOLO {category} model from {model_path}")
        return YOLO(model_path)

    def _release_model(self, wrapper):
        model_name = getattr(wrapper, 'model_name', 'unknown')
        logging.info(f"Releasing resources for {model_name}")

        if hasattr(wrapper, 'model'):
            del wrapper.model
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _register_models(self):
        model_manager.register_model("yolo_photo_cls_general", self._load_general_model, self._release_model)
        for category in self._category_model_map.keys():
            model_manager.register_model(f"yolo_photo_cls_{category}", lambda c=category: self._load_category_model(c), self._release_model)

    def _get_top_prediction(self, pred, model):
        if hasattr(pred, 'probs') and pred.probs is not None:
            top5_indices = pred.probs.top5
            top5_conf = pred.probs.top5conf
            if len(top5_indices) > 0:
                cls_idx = top5_indices[0]
                conf = top5_conf[0]
                return model.names[cls_idx], float(conf)
        return None, None

    def _normalize_label(self, label: Optional[str], confidence: float) -> str:
        if label is None or confidence < 0.8:
            return "others"
        return label

    def _classify_single(self, image: Image.Image):
        general_model = model_manager.get_model("yolo_photo_cls_general")
        general_pred = general_model(image)[0]
        big_category, confidence = self._get_top_prediction(general_pred, general_model)
        big_category = self._normalize_label(big_category, confidence)

        if big_category == "others":
            return {"label": "others", "confidence": confidence}

        small_model_key = f"yolo_photo_cls_{big_category}"
        if big_category in self._category_model_map and model_downloader.is_ready(small_model_key):
            small_model = model_manager.get_model(small_model_key)
            small_pred = small_model(image)[0]
            final_label, final_conf = self._get_top_prediction(small_pred, small_model)
            final_label = self._normalize_label(final_label, final_conf)
            return {"label": final_label, "confidence": final_conf}

        return {"label": big_category, "confidence": confidence}

    async def classify_yolo(self, images_base64: List[str]) -> List[dict]:
        if not model_downloader.is_ready("yolo_photo_cls_general"):
            raise Exception("General model is not ready yet. Please try again later.")

        results = []
        valid_images = []
        valid_indices = []

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

        if not valid_images:
            return results

        general_model = model_manager.get_model("yolo_photo_cls_general")
        preds_batch = general_model(valid_images)

        category_groups: Dict[str, List[int]] = {}
        final_results: Dict[int, dict] = {}

        for res_idx, pred in enumerate(preds_batch):
            idx = valid_indices[res_idx]
            big_category, confidence = self._get_top_prediction(pred, general_model)
            normalized_label = self._normalize_label(big_category, confidence)

            if normalized_label == "others":
                final_results[idx] = {"label": "others", "confidence": confidence}
            else:
                if normalized_label not in category_groups:
                    category_groups[normalized_label] = []
                category_groups[normalized_label].append((idx, res_idx))

        for category, indices in category_groups.items():
            small_model_key = f"yolo_photo_cls_{category}"
            if category in self._category_model_map and model_downloader.is_ready(small_model_key):
                small_model = model_manager.get_model(small_model_key)
                group_images = [valid_images[i[1]] for i in indices]
                small_preds = small_model(group_images)

                for i, small_pred in enumerate(small_preds):
                    idx = indices[i][0]
                    final_label, final_conf = self._get_top_prediction(small_pred, small_model)
                    final_label = self._normalize_label(final_label, final_conf)
                    final_results[idx] = {"label": self._translate_label(final_label), "confidence": final_conf}
            else:
                for i in indices:
                    idx = i[0]
                    final_results[idx] = {"label": self._translate_label(category), "confidence": 1.0}

        for idx, result in final_results.items():
            result["label"] = self._translate_label(result["label"])
            results[idx]["predictions"] = [result]

        return results

image_classification_service = ImageClassificationService()
