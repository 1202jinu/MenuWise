# backend_server.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from models.shared_logic import MenuSummaryDTO, CoreInfoDTO
from crawler.database_and_crawler import MenuWiseDB
from ai.ai_engine import MenuAIProcessor
from typing import List, Optional
import os

app = FastAPI(
    title="MenuWise API",
    description="음식점 리뷰 기반 메뉴 추천 시스템 백엔드 API",
    version="0.1.0"
)

# MenuWiseDB 초기화 시 db_path 인자 명시
db = MenuWiseDB("menu_wise.db")

# 서버 시작 시 AI 프로세서 초기화
api_key = os.getenv("ANTHROPIC_API_KEY", "")
processor = MenuAIProcessor(api_key)

# ------------------------------------------------------------------
# 더미 데이터 (DB/AI 미완성 시 프론트 연동 테스트용)
# DB/AI 파트 코드가 완성되면 아래 USE_DUMMY를 False로 바꾸면 됨
# ------------------------------------------------------------------
USE_DUMMY = True

DUMMY_SEARCH_RESULTS = [
    {
        "menu_id": "menu_001",
        "restaurant_name": "맛있는 국밥집",
        "menu_name": "순대국밥",
        "price": 9000,
        "photo_url": "https://example.com/photo1.jpg",
        "summary": "진한 국물이 일품, 고기가 많이 들어있음",
        "distance_km": 0.3
    },
    {
        "menu_id": "menu_002",
        "restaurant_name": "청춘 떡볶이",
        "menu_name": "매운 떡볶이",
        "price": 6000,
        "photo_url": "https://example.com/photo2.jpg",
        "summary": "엄청 매움 주의, 치즈 추가 추천",
        "distance_km": 0.7
    }
]

DUMMY_DETAILS = [
    {
        "info_id": 1,
        "menu_id": "menu_001",
        "review_text": "국물이 정말 진하고 맛있어요. 고기도 푸짐해서 가성비 최고!",
        "is_positive": True,
        "upvotes": 12,
        "downvotes": 1
    },
    {
        "info_id": 2,
        "menu_id": "menu_001",
        "review_text": "좀 짤 수 있어요. 물 자주 마셔야 함.",
        "is_positive": False,
        "upvotes": 5,
        "downvotes": 2
    }
]

DUMMY_SUMMARY = {
    "menu_id": "menu_001",
    "menu_name": "순대국밥",
    "photo_url": "https://example.com/photo1.jpg",
    "positive_summary": "진한 국물, 푸짐한 고기, 가성비 좋음",
    "negative_summary": "간이 센 편, 짤 수 있음"
}


# ------------------------------------------------------------------
# 3순위: vote 엔드포인트용 Request Body 모델
# ------------------------------------------------------------------
class VoteRequest(BaseModel):
    info_id: int
    upvote: bool


# ------------------------------------------------------------------
# 엔드포인트
# ------------------------------------------------------------------

@app.get(
    "/api/search",
    summary="주변 메뉴 검색",
    description="위치(lat/lng)와 반경(radius_km) 기준으로 주변 음식점 메뉴를 검색합니다. query로 키워드 필터링 가능."
)
async def search_menus(
    lat: float,
    lng: float,
    radius_km: float,
    query: Optional[str] = None
):
    # 더미 모드
    if USE_DUMMY:
        return {"results": DUMMY_SEARCH_RESULTS}

    # try/except로 DB 오류 방어
    try:
        results = db.get_nearby_restaurants(lat, lng, radius_km, query)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {str(e)}")


@app.get(
    "/api/menu/{menu_id}/details",
    summary="메뉴 상세 조회",
    description="menu_id에 해당하는 코어 리뷰(장단점) 목록을 반환합니다."
)
async def get_details(menu_id: str):
    if USE_DUMMY:
        return {"results": DUMMY_DETAILS}

    try:
        results = db.get_menu_details(menu_id)
        if not results:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 메뉴를 찾을 수 없습니다.")
        return {"results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상세 조회 중 오류 발생: {str(e)}")


@app.get(
    "/api/menu/{menu_id}/summary",
    summary="AI 메뉴 요약 조회",
    description="menu_id에 해당하는 AI 요약 결과(장단점 요약 + 대표 사진 URL)를 반환합니다."
)
async def get_menu_summary(menu_id: str):
    if USE_DUMMY:
        return DUMMY_SUMMARY

    try:
        reviews = db.get_menu_details(menu_id)
        if not reviews:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 리뷰를 찾을 수 없습니다.")
        summary = processor.generate_core_summary(reviews)
        return {"summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 요약 중 오류 발생: {str(e)}")


# 3순위: Query Parameter → Request Body 방식으로 변경
@app.post(
    "/api/vote",
    summary="리뷰 추천/비추천",
    description="info_id에 해당하는 코어 리뷰에 추천(upvote=true) 또는 비추천(upvote=false)을 반영합니다."
)
async def vote(request: VoteRequest):
    if USE_DUMMY:
        return {"message": f"info_id {request.info_id} 투표 완료 (더미)", "upvote": request.upvote}

    try:
        result = db.update_feedback(request.info_id, request.upvote)
        if not result:
            raise HTTPException(status_code=404, detail=f"info_id '{request.info_id}'에 해당하는 리뷰를 찾을 수 없습니다.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"투표 처리 중 오류 발생: {str(e)}")