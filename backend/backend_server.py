from fastapi import FastAPI, HTTPException
from shared_models import MenuSummaryDTO, CoreInfoDTO
from db_manager import MenuWiseDB

app = FastAPI()
db = MenuWiseDB()

@app.get("/api/search", response_model=List[MenuSummaryDTO])
async def search(lat: float, lng: float, radius: float, keyword: str = None):
    """
    1. DB에서 반경 내 식당 조회
    2. 키워드 필터링 적용
    3. Level 1 요약 정보 포함하여 반환
    """
    # TODO: db.get_nearby_restaurants 호출 및 필터링 로직 채우기
    return []

@app.get("/api/menu/{menu_id}/details", response_model=List[CoreInfoDTO])
async def get_details(menu_id: str):
    """특정 메뉴 터치 시 상세 리스트(Level 2) 반환"""
    # TODO: DB에서 level=2인 데이터를 추천순으로 정렬하여 반환
    pass

@app.post("/api/vote")
async def vote(info_id: int, upvote: bool):
    """피드백 처리"""
    db.update_vote(info_id, upvote)
    return {"status": "ok"}