import traceback
import logging
import os
import io
import base64
from typing import List
from PIL import Image

from app.config import settings
from app.services.model_downloader import model_downloader
from app.services.model_manager import model_manager
from app.services.ai_config_manager import ai_config_manager

class SentenceTransformerWrapper:
    def __init__(self, model_name="sentence-transformers/clip-ViT-B-32-multilingual-v1"):
        from sentence_transformers import SentenceTransformer
        import torch
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logging.info(f"Loading SentenceTransformer model {model_name} on {self.device}")
        self.model = SentenceTransformer(model_name, device=self.device, cache_folder=settings.MODEL_PATH)

class EmbeddingService:
    def __init__(self):
        self._register_models()
        self._register_downloads()

    def _get_model_info(self):
        selected = ai_config_manager.get_model_selection("classification")
        if selected == "clip-ViT-B-32":
            return {
                "text_model_repo": "sentence-transformers/clip-ViT-B-32-multilingual-v1",
                "image_model_repo": "sentence-transformers/clip-ViT-B-32",
                "text_dir_name": "clip-ViT-B-32-multilingual-v1",
                "image_dir_name": "clip-ViT-B-32"
            }
        return {
                "text_model_repo": "sentence-transformers/clip-ViT-B-32-multilingual-v1",
                "image_model_repo": "sentence-transformers/clip-ViT-B-32",
                "text_dir_name": "clip-ViT-B-32-multilingual-v1",
                "image_dir_name": "clip-ViT-B-32"
        }

    def _register_downloads(self):
        def check_image_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["image_dir_name"])
            return os.path.exists(path) and len(os.listdir(path)) > 0

        def download_image_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["image_dir_name"])
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading Image model {info['image_model_repo']} to {path}...")
            return snapshot_download(info['image_model_repo'], local_dir=path)

        def check_text_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["text_dir_name"])
            return os.path.exists(path) and len(os.listdir(path)) > 0

        def download_text_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["text_dir_name"])
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading Text model {info['text_model_repo']} to {path}...")
            return snapshot_download(info['text_model_repo'], local_dir=path)

        model_downloader.register_model("clip_text", check_text_model, download_text_model)
        model_downloader.register_model("clip_image", check_image_model, download_image_model)

    def _load_text_model(self):
        info = self._get_model_info()
        path = os.path.join(settings.MODEL_PATH, info["text_dir_name"])
        model_name = path if os.path.exists(path) else info["text_model_repo"]
        return SentenceTransformerWrapper(model_name)

    def _load_image_model(self):
        info = self._get_model_info()
        path = os.path.join(settings.MODEL_PATH, info["image_dir_name"])
        model_name = path if os.path.exists(path) else info["image_model_repo"]
        return SentenceTransformerWrapper(model_name)

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
        model_manager.register_model("clip_text", self._load_text_model, self._release_model)
        model_manager.register_model("clip_image", self._load_image_model, self._release_model)

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not model_downloader.is_ready("clip_text"):
             raise Exception("Models are not ready yet. Please try again later.")
        wrapper = model_manager.get_model("clip_text")
        try:
            # Encode texts
            text_embs = wrapper.model.encode(texts, convert_to_tensor=False)
            return text_embs.tolist()
        except Exception as e:
            logging.error(f"Error in text embedding: {e}\n{traceback.format_exc()}")
            raise e

    async def embed_images(self, images_base64: List[str]) -> List[List[float]]:
        if not model_downloader.is_ready("clip_image"):
             raise Exception("Models are not ready yet. Please try again later.")
        wrapper = model_manager.get_model("clip_image")
        try:
            images = []
            for b64 in images_base64:
                if ',' in b64:
                    b64 = b64.split(',')[1]
                image_data = base64.b64decode(b64)
                image = Image.open(io.BytesIO(image_data)).convert("RGB")
                images.append(image)
                
            # Encode images
            image_embs = wrapper.model.encode(images, convert_to_tensor=False)
            return image_embs.tolist()
        except Exception as e:
            logging.error(f"Error in image embedding: {e}\n{traceback.format_exc()}")
            raise e

embedding_service = EmbeddingService()
