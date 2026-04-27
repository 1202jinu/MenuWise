# backend_server.py
from fastapi import FastAPI
from models.shared_logic import MenuSummaryDTO, CoreInfoDTO
from crawler.database_and_crawler import MenuWiseDB
from typing import List, Optional

app = FastAPI()
db = MenuWiseDB()


@app.get("/api/search", response_model=List[MenuSummaryDTO])
async def search_menus(
    lat: float,
    lng: float,
    radius: float,
    keyword: Optional[str] = None   # 복구
):
    return db.search_menus(lat, lng, radius, keyword)


@app.get("/api/menu/{menu_id}/details", response_model=List[CoreInfoDTO])
async def get_details(menu_id: str):
    return db.get_menu_details(menu_id)


@app.post("/api/vote")
async def vote(info_id: int, upvote: bool):
    return db.vote(info_id, upvote)