# backend_server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from crawler.database_and_crawler import MenuWiseDB
from ai.ai_analyzer import MenuAIProcessor          # [수정 1] 실제 파일명으로 import 경로 수정
from typing import Optional
import os

app = FastAPI(
    title="MenuWise API",
    description="음식점 리뷰 기반 메뉴 추천 시스템 백엔드 API - /docs 에서 전체 명세 확인 가능",
    version="0.1.0"
)

# DB / AI 초기화
db = MenuWiseDB("menu_wise.db")
api_key = os.getenv("OPENAI_API_KEY", "")           # [수정 2] AI 파트가 OpenAI 사용하므로 키 이름 수정
processor = MenuAIProcessor(api_key)

# ------------------------------------------------------------------
# 더미 데이터 (DB/AI 미완성 시 프론트 연동 테스트용)
# DB/AI 파트 코드가 완성되면 USE_DUMMY = False 로만 바꾸면 됨
# ------------------------------------------------------------------
USE_DUMMY = True

# [수정 3] 프론트 main.py가 core_pros, core_cons 필드를 기대하므로 더미에도 포함
DUMMY_SEARCH_RESULTS = [
    {
        "menu_id": "menu_001",
        "restaurant_name": "맛있는 국밥집",
        "menu_name": "순대국밥",
        "price": 9000,
        "photo_url": "https://example.com/photo1.jpg",
        "core_pros": "진한 국물, 고기 푸짐",
        "core_cons": "간이 센 편",
        "distance_km": 0.3
    },
    {
        "menu_id": "menu_002",
        "restaurant_name": "청춘 떡볶이",
        "menu_name": "매운 떡볶이",
        "price": 6000,
        "photo_url": "https://example.com/photo2.jpg",
        "core_pros": "중독성 있는 매운맛",
        "core_cons": "매우 매움 주의",
        "distance_km": 0.7
    }
]

DUMMY_DETAILS = [
    {
        "info_id": 1,
        "menu_id": "menu_001",
        "content": "국물이 정말 진하고 맛있어요. 고기도 푸짐해서 가성비 최고!",
        "info_type": "PROS",
        "level": 2,
        "upvotes": 12,
        "downvotes": 1
    },
    {
        "info_id": 2,
        "menu_id": "menu_001",
        "content": "좀 짤 수 있어요. 물 자주 마셔야 함.",
        "info_type": "CONS",
        "level": 2,
        "upvotes": 5,
        "downvotes": 2
    }
]

DUMMY_SUMMARY = {
    "menu_id": "menu_001",
    "menu_name": "순대국밥",
    "photo_url": "https://example.com/photo1.jpg",
    "level_1": {
        "pros": "진한 국물, 푸짐한 고기, 가성비 좋음",
        "cons": "간이 센 편, 짤 수 있음"
    }
}


# ------------------------------------------------------------------
# Request Body 모델
# ------------------------------------------------------------------
class VoteRequest(BaseModel):
    info_id: int
    upvote: bool  # True = 추천, False = 비추천


# ------------------------------------------------------------------
# 헬퍼 함수: DB에 get_menu_details가 없으므로 백엔드에서 직접 쿼리  [수정 4]
# ------------------------------------------------------------------
def _fetch_core_info(menu_id: str):
    """core_info 테이블에서 menu_id에 해당하는 리뷰 목록 조회"""
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT info_id, menu_id, content, info_type, level, upvotes, downvotes
        FROM core_info
        WHERE menu_id = ?
        ORDER BY level ASC, upvotes DESC
    """, (menu_id,))
    rows = cursor.fetchall()
    return [
        {
            "info_id": row[0],
            "menu_id": row[1],
            "content": row[2],
            "info_type": row[3],
            "level": row[4],
            "upvotes": row[5],
            "downvotes": row[6]
        }
        for row in rows
    ]


def _fetch_menu_name(menu_id: str):
    """메뉴 이름 조회 (AI 요약 호출 시 필요)"""
    cursor = db.conn.cursor()
    cursor.execute("SELECT menu_name FROM menus WHERE menu_id = ?", (menu_id,))
    row = cursor.fetchone()
    return row[0] if row else "알 수 없는 메뉴"


def _build_search_results(restaurants: list):
    """
    get_nearby_restaurants 결과(식당 목록)에
    프론트가 필요한 core_pros / core_cons 필드를 붙여서 반환  [수정 5]
    """
    result = []
    cursor = db.conn.cursor()
    for res in restaurants:
        cursor.execute("""
            SELECT m.menu_id, m.menu_name, m.price, m.photo_url
            FROM menus m
            WHERE m.res_id = ?
        """, (res["res_id"],))
        menus = cursor.fetchall()

        for menu in menus:
            menu_id, menu_name, price, photo_url = menu

            # level=1 (대표) pros/cons 조회
            cursor.execute("""
                SELECT content, info_type FROM core_info
                WHERE menu_id = ? AND level = 1
            """, (menu_id,))
            core_rows = cursor.fetchall()

            core_pros = next((r[0] for r in core_rows if r[1] == "PROS"), "")
            core_cons = next((r[0] for r in core_rows if r[1] == "CONS"), "")

            result.append({
                "menu_id": menu_id,
                "restaurant_name": res["res_name"],
                "menu_name": menu_name,
                "price": price,
                "photo_url": photo_url or "",
                "core_pros": core_pros,
                "core_cons": core_cons,
                "distance_km": res["distance_km"]
            })
    return result


# ------------------------------------------------------------------
# 엔드포인트
# ------------------------------------------------------------------

@app.get(
    "/api/search",
    summary="주변 메뉴 검색",
    description="위치(lat/lng)와 반경(radius) 기준으로 주변 음식점 메뉴를 검색합니다. query로 키워드 필터링 가능."
)
async def search_menus(
    lat: float,
    lng: float,
    radius: float,                      # [수정 6] DB 메서드 인자명과 통일 (radius_km → radius)
    query: Optional[str] = None
):
    if USE_DUMMY:
        return {"results": DUMMY_SEARCH_RESULTS}

    try:
        # [수정 6] DB 메서드는 인자 3개 (lat, lng, radius)
        restaurants = db.get_nearby_restaurants(lat, lng, radius)

        # query 키워드 필터링
        if query:
            query_lower = query.lower()
            results = [
                r for r in _build_search_results(restaurants)
                if query_lower in r["menu_name"].lower()
                or query_lower in r["restaurant_name"].lower()
                or query_lower in r["core_pros"].lower()
                or query_lower in r["core_cons"].lower()
            ]
        else:
            results = _build_search_results(restaurants)

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
        # [수정 4] DB에 get_menu_details 없으므로 헬퍼 함수로 직접 쿼리
        results = _fetch_core_info(menu_id)
        if not results:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 리뷰가 없습니다.")
        return {"results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상세 조회 중 오류 발생: {str(e)}")


@app.get(
    "/api/menu/{menu_id}/summary",
    summary="AI 메뉴 요약 조회",
    description="menu_id에 해당하는 AI 요약 결과(장단점 요약)를 반환합니다."
)
async def get_menu_summary(menu_id: str):
    if USE_DUMMY:
        return DUMMY_SUMMARY

    try:
        reviews = _fetch_core_info(menu_id)
        if not reviews:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 리뷰가 없습니다.")

        menu_name = _fetch_menu_name(menu_id)
        review_texts = [r["content"] for r in reviews]

        # [수정 7] AI 실제 메서드명 analyze_reviews(menu_name, reviews) 로 수정
        summary = processor.analyze_reviews(menu_name, review_texts)
        return {"menu_id": menu_id, "menu_name": menu_name, "summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 요약 중 오류 발생: {str(e)}")


@app.post(
    "/api/vote",
    summary="리뷰 추천/비추천",
    description='info_id에 해당하는 리뷰에 추천(upvote=true) 또는 비추천(upvote=false)을 반영합니다. Body 예시: {"info_id": 1, "upvote": true}'
)
async def vote(request: VoteRequest):
    if USE_DUMMY:
        return {"message": f"info_id {request.info_id} 투표 완료 (더미)", "upvote": request.upvote}

    try:
        # [수정 8] DB 실제 메서드명 update_vote(info_id, is_upvote) 로 수정
        db.update_vote(request.info_id, request.upvote)
        return {"message": "투표가 반영되었습니다.", "info_id": request.info_id, "upvote": request.upvote}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"투표 처리 중 오류 발생: {str(e)}")