# backend_server.py (Role 3 유다연)
from fastapi import FastAPI, HTTPException
from models.shared_logic import MenuSummaryDTO, CoreInfoDTO
from crawler.database_and_crawler import MenuWiseDB
from typing import List

app = FastAPI()
db = MenuWiseDB()

@app.get("/api/search", response_model=List[MenuSummaryDTO])
async def search_menus(lat: float, lng: float, radius: float):
    # 1. 반경 내 식당 필터링
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM restaurants")
    rows = cursor.fetchall()
    
    nearby_res = [row['res_id'] for row in rows if db.calculate_distance(lat, lng, row['lat'], row['lng']) <= radius]
    if not nearby_res: return []

    # 2. 메뉴 및 Level 1 요약 정보 결합 조회
    placeholders = ','.join(['?'] * len(nearby_res))
    query = f"""
        SELECT m.menu_id, m.name as menu_name, m.price, m.photo_url,
               (SELECT content FROM core_info WHERE menu_id = m.menu_id AND level = 1 AND info_type = 'PROS') as core_pros,
               (SELECT content FROM core_info WHERE menu_id = m.menu_id AND level = 1 AND info_type = 'CONS') as core_cons
        FROM menus m WHERE m.res_id IN ({placeholders})
    """
    cursor.execute(query, nearby_res)
    return [dict(row) for row in cursor.fetchall()]

@app.get("/api/menu/{menu_id}/details", response_model=List[CoreInfoDTO])
async def get_details(menu_id: str):
    # Level 2 상세 정보 조회 (추천순 정렬)
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM core_info WHERE menu_id = ? AND level = 2 ORDER BY upvotes DESC", (menu_id,))
    return [dict(row) for row in cursor.fetchall()]

@app.post("/api/vote")
async def vote(info_id: int, upvote: bool):
    col = "upvotes" if upvote else "downvotes"
    cursor = db.conn.cursor()
    cursor.execute(f"UPDATE core_info SET {col} = {col} + 1 WHERE info_id = ?", (info_id,))
    db.conn.commit()
    return {"status": "success"}
