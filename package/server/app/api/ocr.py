from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.dependencies import get_db, BaseResponse
from app.crud import ocr as crud
from app.schemas import ocr as schemas
from app.db.models.photo import Photo

router = APIRouter()

@router.get("", response_model=BaseResponse[schemas.OCRResponse], summary="Get OCR records")
def get_ocr_records(
    photo_id: UUID = Query(..., description="The ID of the photo to retrieve OCR records for"),
    db: Session = Depends(get_db)
):
    """
    Get all OCR recognition records for a specific photo.
    Returns the text, confidence score, and polygon coordinates for each detected text region.
    """
    records = crud.get_ocr_by_photo_id(db, photo_id)
    return BaseResponse(
        code = 200,
        msg = '',
        data = {
            "count": len(records),
            "records": records
        }
    )

@router.delete("/{photo_id}", summary="Delete OCR records")
def delete_ocr_records(
    photo_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Delete all OCR recognition records for a specific photo.
    """
    # Verify photo exists (optional, but good practice)
    # count = crud.delete_ocr_by_photo_id(db, photo_id)
    
    # We can also update the photo's processed_tasks status if we want to be consistent
    # But usually re-running OCR will overwrite.
    # Let's just delete the records.
    
    # Update photo task status
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if photo and photo.processed_tasks:
        tasks = dict(photo.processed_tasks)
        if 'ocr' in tasks:
            tasks['ocr'] = False
            photo.processed_tasks = tasks
            db.add(photo)
            
    count = crud.delete_ocr_by_photo_id(db, photo_id)
    
    return BaseResponse(
        code = 200,
        msg = "success",
        data = {"status": "success", "deleted_count": count}
    )
