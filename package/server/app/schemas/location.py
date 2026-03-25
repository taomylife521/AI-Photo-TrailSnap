from typing import Optional, List, Union
from uuid import UUID

from pydantic import BaseModel
from app.schemas.photo import Photo

class LocationBase(BaseModel):
    name: str
    level: str
    count: int

class LocationStatistics(BaseModel):
    province_count: int
    city_count: int
    district_count: int
    country_count: int

class Location(LocationBase):
    id: Optional[str] = None
    is_custom: Optional[bool] = None
    cover: Optional[Photo] = None

    class Config:
        from_attributes = True

class MapMarker(BaseModel):
    id: str
    lat: float
    lng: float

class LocationValue(BaseModel):
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

class LocationSearchItem(BaseModel):
    label: str
    value: LocationValue

class TimelineNode(BaseModel):
    type: str = "default"
    startDate: str
    endDate: str
    locationName: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    photoCount: int = 0
    coverId: Optional[UUID] = None
    
class TimelineResponse(BaseModel):
    nodes: List[TimelineNode]
    total: int
