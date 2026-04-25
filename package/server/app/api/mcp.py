#!/usr/bin/env python
# -*- coding: utf-8 -*-

from mcp.server.fastmcp import FastMCP
import asyncio
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models.user import User
from app.db.models.trip import TrainTicket
from app.crud import crud_vector
from app.crud.photo import get_photo
from app.utils.embedding import async_get_embedding
import json

mcp_server = FastMCP("trailsnap-mcp", host="0.0.0.0")

def get_default_user(db: Session) -> User:
    """获取默认用户上下文（针对多用户相册环境，选择拥有照片的用户）"""
    users = db.query(User).all()
    for user in users:
        # 简单策略：选择相册中有照片的用户
        from app.db.models.photo import Photo
        if db.query(Photo).filter(Photo.owner_id == user.id).first():
            return user
    
    # 如果都没照片，返回第一个
    if users:
        return users[0]
        
    raise ValueError("数据库中没有找到用户。")

@mcp_server.tool()
async def search_photos(query: str, limit: int = 5) -> str:
    """
    Search for photos using natural language query or keywords via TrailSnap's AI vector search.
    Returns a JSON string containing matched photo filenames, paths, and creation times.
    """
    db = SessionLocal()
    try:
        user = get_default_user(db)
        
        # 1. 获取查询语句的文本向量
        embedding = await async_get_embedding(query, user.id, db)
        
        # 2. 向量相似度检索
        results = crud_vector.search_similar_vectors(db, embedding, limit=limit, user_id=user.id)
        
        response_data = []
        for vector, distance in results:
            score = 1 - distance
            # 过滤掉相似度太低的照片
            if score < 0.15:
                continue
                
            photo = get_photo(db, vector.photo_id)
            if photo:
                response_data.append({
                    "filename": photo.filename,
                    "path": photo.file_path,
                    "time": photo.photo_time.strftime("%Y-%m-%d %H:%M:%S") if photo.photo_time else None,
                    "similarity_score": round(score, 3)
                })
        
        if not response_data:
            return f"No photos found matching '{query}'."
            
        return json.dumps(response_data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error searching photos: {str(e)}"
    finally:
        db.close()

@mcp_server.tool()
async def get_train_tickets(destination: str, limit: int = 5) -> str:
    """
    Search the user's train tickets by arrival station/destination.
    Returns a JSON string containing train code, departure, arrival, and time.
    """
    db = SessionLocal()
    try:
        user = get_default_user(db)
        
        # 使用 SQLAlchemy ilike 进行模糊匹配
        tickets = db.query(TrainTicket).filter(
            TrainTicket.owner_id == user.id,
            TrainTicket.arrival_station.ilike(f"%{destination}%")
        ).order_by(TrainTicket.date_time.desc()).limit(limit).all()
        
        if not tickets:
            return f"No train tickets found to '{destination}'."
            
        response_data = []
        for t in tickets:
            response_data.append({
                "train_code": t.train_code,
                "departure_station": t.departure_station,
                "arrival_station": t.arrival_station,
                "date_time": t.date_time.strftime("%Y-%m-%d %H:%M") if t.date_time else None,
                "seat": f"{t.carriage}车 {t.seat_num}" if t.carriage and t.seat_num else "Unknown",
                "price": t.price
            })
            
        return json.dumps(response_data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error getting train tickets: {str(e)}"
    finally:
        db.close()

# 暴露给 main.py 挂载使用的 ASGI App
mcp_app = mcp_server.sse_app()
