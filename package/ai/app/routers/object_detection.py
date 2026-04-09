from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

router = APIRouter()

class ObjectDetectionRequest(BaseModel):
    images: List[str]

@router.post("/predict")
async def object_detection_predict(request: ObjectDetectionRequest):
    """
    Perform object detection on multiple base64 encoded images.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
    return {"message": "Object detection service not implemented yet"}
