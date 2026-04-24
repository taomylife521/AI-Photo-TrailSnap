#!/usr/bin/env python
# -*- coding: utf-8 -*-
from uuid import UUID

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

class FlightTicketBase(BaseModel):
    """飞机票基础模型（用于请求和响应）"""
    flight_code: str = Field(..., description="航班号")
    departure_city: str = Field(..., description="出发地")
    arrival_city: str = Field(..., description="目的地")
    date_time: datetime = Field(..., description="出发日期时间")
    price: Decimal = Field(..., ge=0, description="票价")
    name: str = Field(..., description="乘车人姓名")
    total_mileage: Optional[Decimal] = Field(default=0, ge=0, description="里程")
    total_running_time: Optional[int] = Field(default=0, ge=0, description="飞行时长（分钟）")
    comments: Optional[str] = Field(None, description="备注信息")
    photo_id: Optional[UUID] = Field(None, description="关联照片ID")

class FlightTicketCreate(FlightTicketBase):
    """创建飞机票请求模型"""
    pass

class FlightTicketUpdate(BaseModel):
    """更新飞机票请求模型"""
    flight_code: Optional[str] = Field(None, description="航班号")
    departure_city: Optional[str] = Field(None, description="出发地")
    arrival_city: Optional[str] = Field(None, description="目的地")
    date_time: Optional[datetime] = Field(None, description="出发日期时间")
    price: Optional[Decimal] = Field(None, ge=0, description="票价")
    name: Optional[str] = Field(None, description="乘车人姓名")
    total_mileage: Optional[Decimal] = Field(None, ge=0, description="里程")
    total_running_time: Optional[int] = Field(None, ge=0, description="飞行时长（分钟）")
    comments: Optional[str] = Field(None, description="备注信息")
    photo_id: Optional[UUID] = Field(None, description="关联照片ID")

class FlightTicketResponse(FlightTicketBase):
    """飞机票响应模型"""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class FlightTicketListResponse(BaseModel):
    """飞机票列表响应模型"""
    total: int = Field(..., description="总记录数")
    items: List[FlightTicketResponse] = Field(..., description="飞机票列表")
