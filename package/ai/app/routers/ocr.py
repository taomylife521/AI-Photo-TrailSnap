import logging
import traceback
from typing import List, Any, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.services.ocr_service import ocr_service

router = APIRouter()

class OCRRequest(BaseModel):
    images: List[str]

class OCRResult(BaseModel):
    prunedResult: Dict[str, Any] = {}
    ocrImage: str|None = ""
    docPreprocessingImage: str|None = ""
    inputImage: str|None = ""

class OCRResponse(BaseModel):
    results: List[Dict[str, Any]]

@router.post("/predict", response_model=OCRResponse, summary="OCR Prediction")
async def ocr_predict(request: OCRRequest):
    """
    Perform OCR prediction on multiple base64 encoded images.
    - **images**: List of base64 encoded image strings.
    Returns:
        OCRResponse: The OCR results and images.
        - **dataInfo**: Additional information about the OCR process.
        - **ocrResults**: The OCR results, including pruned results and images.
            - **prunedResult**: The pruned OCR result, containing the detected text and other relevant information.
                - **rec_texts**: (List[str]) 文本识别结果列表，仅包含置信度超过text_rec_score_thresh的文本
                - **rec_scores**: (List[float]) 文本识别的置信度列表，已按text_rec_score_thresh过滤
                - **rec_polys**: (List[List[int]]) 经过置信度过滤的文本检测框列表，文本检测的多边形框列表。每个检测框由4个顶点坐标构成的int数组表示，数组shape为(4, 2)，数据类型为int16
                - **rec_boxes**: (List[List[int]]) 检测框的矩形边界框列表，每个元素为一个4个整数的列表，分别表示矩形框的[x_min, y_min, x_max, y_max]坐标，其中(x_min, y_min)为左上角坐标，(x_max, y_max)为右下角坐标
            - **ocrImage**: The image of the OCR result.
            - **docPreprocessingImage**: The image of the document preprocessing step.
            - **inputImage**: The original input image.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
        
    import base64
    try:
        batch_results = []
        for b64 in request.images:
            if ',' in b64:
                b64 = b64.split(',')[1]
            contents = base64.b64decode(b64)
            results = ocr_service.detect_text(contents)
            batch_results.append({
                "ocrResults": results,
                "dataInfo": []
            })
        return OCRResponse(results=batch_results)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

