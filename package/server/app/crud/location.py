from sqlalchemy.orm import Session
from uuid import UUID
from sqlalchemy import func, desc, extract, case
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene

def get_location_years(db: Session, owner_id: UUID):
    years = db.query(extract('year', Photo.photo_time))\
        .filter(Photo.photo_time.isnot(None), Photo.owner_id == owner_id)\
        .distinct()\
        .order_by(desc(extract('year', Photo.photo_time)))\
        .all()
    return [int(y[0]) for y in years if y[0] is not None]

def get_locations(db: Session, owner_id: UUID, level: str = 'city', skip: int = 0, limit: int = 100, year: int = None):
    is_scene = False
    if level == 'city':
        group_col = PhotoMetadata.city
    elif level == 'province':
        group_col = PhotoMetadata.province
    elif level == 'district':
        group_col = PhotoMetadata.district
    elif level == 'scene':
        group_col = Scene.name
        is_scene = True
    else:
        return []

    # Group by location and count
    if is_scene:
        query = db.query(
            Scene.name,
            Scene.id,
            Scene.is_custom,
            func.count(Photo.id).label('count')
        ).filter(Photo.owner_id == owner_id).outerjoin(
            PhotoMetadata, Scene.id == PhotoMetadata.scene_id
        ).outerjoin(
            Photo, Photo.id == PhotoMetadata.photo_id
        )
    else:
        query = db.query(
            group_col,
            func.count(Photo.id).label('count')
        ).filter(Photo.owner_id == owner_id).join(
            PhotoMetadata, Photo.id == PhotoMetadata.photo_id
        )

    # if is_scene:
    #     query = query.join(Scene, PhotoMetadata.scene_id == Scene.id)

    if is_scene:
        # For scenes, we don't filter out None/empty names if they are defined in the Scene table
        pass
    else:
        query = query.filter(
            group_col.is_not(None),
            group_col != ''
        )

    if year:
        query = query.filter(extract('year', Photo.photo_time) == year)

    if is_scene:
        query = query.group_by(Scene.name, Scene.id, Scene.is_custom)
    else:
        query = query.group_by(group_col)
    
    query = query.order_by(
        desc('count')
    ).offset(skip).limit(limit)

    results = query.all()

    if not results:
        return []

    # Get list of location names from current page results
    names = [r[0] for r in results]

    # Batch fetch cover photos using DISTINCT ON to avoid N+1 queries
    # Optimized for PostgreSQL
    cover_query = db.query(
        Photo,
        group_col
    ).filter(Photo.owner_id == owner_id).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    )

    if is_scene:
        cover_query = cover_query.join(Scene, PhotoMetadata.scene_id == Scene.id)

    if year:
        cover_query = cover_query.filter(extract('year', Photo.photo_time) == year)

    covers = cover_query.filter(
        group_col.in_(names)
    ).distinct(
        group_col
    ).order_by(
        group_col,
        desc(Photo.photo_time)
    ).all()

    # Map location name to cover photo
    cover_map = {loc_name: photo for photo, loc_name in covers}

    locations = []
    if is_scene:
        for name, sid, is_custom, count in results:
            locations.append({
                "name": name,
                "id": str(sid),
                "is_custom": is_custom,
                "level": level,
                "count": count,
                "cover": cover_map.get(name)
            })
    else:
        for name, count in results:
            locations.append({
                "name": name,
                "level": level,
                "count": count,
                "cover": cover_map.get(name)
            })
        
    return locations

def get_location_photos(db: Session, owner_id: UUID, name: str, level: str = 'city', skip: int = 0, limit: int = 50, year: int = None):
    query = db.query(Photo).options(joinedload(Photo.metadata_info)).filter(Photo.owner_id == owner_id)
    if level == 'city':
        col = PhotoMetadata.city
        query = query.join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
    elif level == 'province':
        col = PhotoMetadata.province
        query = query.join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
    elif level == 'district':
        col = PhotoMetadata.district
        query = query.join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
    elif level == 'scene':
        col = Scene.name
        query = query.join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)\
                  .join(Scene, PhotoMetadata.scene_id == Scene.id)
    else:
        return []
        
    if year:
        query = query.filter(extract('year', Photo.photo_time) == year)

    return query.filter(
        col == name
    ).order_by(
        desc(Photo.photo_time)
    ).offset(skip).limit(limit).all()

def get_map_markers(db: Session, owner_id: UUID, year: int = None):
    query = db.query(
        Photo.id,
        PhotoMetadata.latitude,
        PhotoMetadata.longitude
    ).join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)\
     .filter(PhotoMetadata.latitude.isnot(None))\
     .filter(PhotoMetadata.longitude.isnot(None))\
     .filter(Photo.owner_id == owner_id)
     
    if year:
        query = query.filter(extract('year', Photo.photo_time) == year)

    results = query.all()
     
    return [
        {"id": str(r[0]), "lat": float(r[1]), "lng": float(r[2])}
        for r in results
    ]

def get_timeline_nodes(db: Session, owner_id: UUID, skip: int = 0, limit: int = 100, year: int = None):
    from datetime import datetime
    from app.schemas.location import TimelineResponse, TimelineNode

    query = db.query(Photo, PhotoMetadata, Scene.name.label("scene_name")) \
              .join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id) \
              .outerjoin(Scene, PhotoMetadata.scene_id == Scene.id) \
              .filter(Photo.owner_id == owner_id) \
              .filter(PhotoMetadata.latitude.isnot(None)) \
              .filter(PhotoMetadata.longitude.isnot(None)) \
              .filter(Photo.photo_time.isnot(None))

    if year:
        query = query.filter(extract('year', Photo.photo_time) == year)

    query = query.order_by(desc(Photo.photo_time))
    results = query.all()

    nodes = []
    
    for photo_obj, meta_obj, scene_name in results:
        date_str = photo_obj.photo_time.strftime('%Y-%m-%d')
        
        # 确定位置名称：优先景区，其次城市，然后区县，省份
        loc_name = "未知位置"
        if scene_name and scene_name.strip():
            loc_name = scene_name.strip()
        elif meta_obj.city and meta_obj.city.strip():
            loc_name = meta_obj.city.strip()
        elif meta_obj.district and meta_obj.district.strip():
            loc_name = meta_obj.district.strip()
        elif meta_obj.province and meta_obj.province.strip():
            loc_name = meta_obj.province.strip()
            
        lat = float(meta_obj.latitude)
        lng = float(meta_obj.longitude)
        
        if not nodes:
            nodes.append(TimelineNode(
                startDate=date_str,
                endDate=date_str,
                locationName=loc_name,
                lat=lat,
                lng=lng,
                photoCount=1,
                coverId=photo_obj.id
            ))
            continue
            
        last_node = nodes[-1]
        
        if last_node.locationName == loc_name:
            last_node.endDate = date_str
            # 更新平均经纬度
            total_lat = (last_node.lat * last_node.photoCount) + lat
            total_lng = (last_node.lng * last_node.photoCount) + lng
            last_node.photoCount += 1
            last_node.lat = total_lat / last_node.photoCount
            last_node.lng = total_lng / last_node.photoCount
        else:
            nodes.append(TimelineNode(
                startDate=date_str,
                endDate=date_str,
                locationName=loc_name,
                lat=lat,
                lng=lng,
                photoCount=1,
                coverId=photo_obj.id
            ))

    total_nodes = len(nodes)
    paginated_nodes = nodes[skip : skip + limit]

    return TimelineResponse(nodes=paginated_nodes, total=total_nodes)

def get_location_distribution(db: Session, owner_id: UUID, level: str = 'city', year: int = None):
    is_scene = False
    if level == 'city':
        group_col = PhotoMetadata.city
    elif level == 'province':
        group_col = PhotoMetadata.province
    elif level == 'district':
        group_col = PhotoMetadata.district
    elif level == 'scene':
        group_col = Scene.name
        is_scene = True
    else:
        return []

    # Group by location and count, no limit
    query = db.query(
        group_col.label('name'),
        func.count(Photo.id).label('count')
    ).filter(Photo.owner_id == owner_id).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    )

    if is_scene:
        query = query.join(Scene, PhotoMetadata.scene_id == Scene.id)

    if year:
        query = query.filter(extract('year', Photo.photo_time) == year)

    results = query.filter(
        group_col.is_not(None),
        group_col != ''
    ).group_by(
        group_col
    ).all()
    
    return [{"name": r[0], "count": r[1], "level": level} for r in results]

def get_location_statistics(db: Session, owner_id: UUID):
    # Filter photos by owner_id first
    subq = db.query(Photo.id).filter(Photo.owner_id == owner_id).subquery()
    
    # Query stats using the subquery
    result = db.query(
        func.count(func.distinct(case((PhotoMetadata.province != '', PhotoMetadata.province), else_=None))),
        func.count(func.distinct(case((PhotoMetadata.city != '', PhotoMetadata.city), else_=None))),
        func.count(func.distinct(case((PhotoMetadata.district != '', PhotoMetadata.district), else_=None))),
        func.count(func.distinct(case((PhotoMetadata.country != '', PhotoMetadata.country), else_=None)))
    ).join(
        subq, PhotoMetadata.photo_id == subq.c.id
    ).first()
    
    return {
        "province_count": result[0] or 0,
        "city_count": result[1] or 0,
        "district_count": result[2] or 0,
        "country_count": result[3] or 0
    }

def search_locations(db: Session, owner_id: UUID, query: str, limit: int = 20):
    search = f"%{query}%"
    suggestions = []
    seen = set()

    # 1. Search Provinces
    provinces = db.query(PhotoMetadata.province)\
        .join(Photo, Photo.id == PhotoMetadata.photo_id)\
        .filter(Photo.owner_id == owner_id)\
        .filter(PhotoMetadata.province.ilike(search))\
        .filter(PhotoMetadata.province.isnot(None), PhotoMetadata.province != '')\
        .distinct()\
        .limit(10).all()
        
    for p in provinces:
        label = p[0]
        if label and label not in seen:
            seen.add(label)
            suggestions.append({
                "label": label,
                "value": {
                    "province": label,
                    "city": "",
                    "district": ""
                }
            })
            
    # 2. Search Cities (Distinct Province + City)
    # Match on Province OR City
    cities = db.query(PhotoMetadata.province, PhotoMetadata.city)\
        .join(Photo, Photo.id == PhotoMetadata.photo_id)\
        .filter(Photo.owner_id == owner_id)\
        .filter((PhotoMetadata.province.ilike(search)) | (PhotoMetadata.city.ilike(search)))\
        .filter(PhotoMetadata.city.isnot(None), PhotoMetadata.city != '')\
        .distinct()\
        .limit(20).all()

    for p, c in cities:
        parts = [x for x in [p, c] if x]
        label = "".join(parts)
        
        # Only add if it matches the query string somewhat (e.g. contains query)
        # Or simply add because it was returned by the query
        if label and label not in seen:
            seen.add(label)
            suggestions.append({
                "label": label,
                "value": {
                    "province": p or "",
                    "city": c,
                    "district": ""
                }
            })

    # 3. Search Districts (Distinct Province + City + District)
    # Match on Province OR City OR District
    districts = db.query(PhotoMetadata.province, PhotoMetadata.city, PhotoMetadata.district)\
        .join(Photo, Photo.id == PhotoMetadata.photo_id)\
        .filter(Photo.owner_id == owner_id)\
        .filter(
            (PhotoMetadata.province.ilike(search)) |
            (PhotoMetadata.city.ilike(search)) |
            (PhotoMetadata.district.ilike(search))
        )\
        .filter(PhotoMetadata.district.isnot(None), PhotoMetadata.district != '')\
        .distinct()\
        .limit(20).all()
        
    for p, c, d in districts:
        parts = [x for x in [p, c, d] if x]
        label = "".join(parts)
        
        if label and label not in seen:
            seen.add(label)
            suggestions.append({
                "label": label,
                "value": {
                    "province": p or "",
                    "city": c or "",
                    "district": d
                }
            })
            
    # Sort by label length (shorter = broader scope usually comes first)
    suggestions.sort(key=lambda x: len(x["label"]))
    
    return suggestions[:limit]
