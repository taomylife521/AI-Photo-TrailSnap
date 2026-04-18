import logging
import traceback

from fastapi import APIRouter, HTTPException
from app.services.image_classification_service import image_classification_service
from pydantic import BaseModel
from typing import List

router = APIRouter()

class YoloClassifyRequest(BaseModel):
    images: List[str]

@router.post("/")
async def classify_images(request: YoloClassifyRequest):
    """
    Classify one or multiple images using YOLO model.
    Input images should be base64 encoded strings.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
    try:
        results = await image_classification_service.classify_yolo(request.images)
        return {"results": results}
    except Exception as e:
        logging.error(f"Error in YOLO classification API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))