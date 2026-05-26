# backend_server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os

app = FastAPI(
    title="MenuWise API",
    description="음식점 리뷰 기반 메뉴 추천 시스템 백엔드 API - /docs 에서 전체 명세 확인 가능",
    version="0.1.0"
)

# DB / AI 초기화 (타 파트 미완성 시 서버 실행 가능하도록 try/except 처리)
try:
    from crawler.database_and_crawler import MenuWiseDB
    db = MenuWiseDB("menu_wise.db")
except ModuleNotFoundError:
    db = None

try:
    from ai_engine.ai_analyzer import MenuAIProcessor
    api_key = os.getenv("OPENAI_API_KEY", "")
    processor = MenuAIProcessor(api_key)
except ModuleNotFoundError:
    processor = None

# ------------------------------------------------------------------
# 더미 데이터 (DB/AI 미완성 시 프론트 연동 테스트용)
# DB/AI 파트 코드가 완성되면 USE_DUMMY = False 로만 바꾸면 됨
# ------------------------------------------------------------------
USE_DUMMY = True

# [7-8주차] 프론트가 Flutter로 바뀌면서 지도 마커용 lat/lng 좌표 필드 추가
DUMMY_SEARCH_RESULTS = [
    {
        "menu_id": "menu_001",
        "restaurant_name": "맛있는 국밥집",
        "menu_name": "순대국밥",
        "price": 9000,
        "photo_url": "https://example.com/photo1.jpg",
        "core_pros": "진한 국물, 고기 푸짐",
        "core_cons": "간이 센 편",
        "distance_km": 0.3,
        "lat": 37.8813,        # [7-8주차 추가] 지도 마커용 좌표
        "lng": 127.7298
    },
    {
        "menu_id": "menu_002",
        "restaurant_name": "청춘 떡볶이",
        "menu_name": "매운 떡볶이",
        "price": 6000,
        "photo_url": "https://example.com/photo2.jpg",
        "core_pros": "중독성 있는 매운맛",
        "core_cons": "매우 매움 주의",
        "distance_km": 0.7,
        "lat": 37.8821,        # [7-8주차 추가] 지도 마커용 좌표
        "lng": 127.7310
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

# [7-8주차] match_photo 연동으로 photo_url 필드가 AI가 선택한 대표 사진으로 채워짐
DUMMY_SUMMARY = {
    "menu_id": "menu_001",
    "menu_name": "순대국밥",
    "photo_url": "https://example.com/photo1.jpg",  # match_photo 결과가 여기 들어감
    "level_1": {
        "pros": "진한 국물, 푸짐한 고기, 가성비 좋음",
        "cons": "간이 센 편, 짤 수 있음"
    },
    "level_2": [
        {"content": "국물이 진하고 깊은 맛이 나요", "type": "PROS"},
        {"content": "고기 양이 많아서 배부르게 먹을 수 있어요", "type": "PROS"},
        {"content": "간이 좀 센 편이에요", "type": "CONS"}
    ]
}


# ------------------------------------------------------------------
# Request Body 모델
# ------------------------------------------------------------------
class VoteRequest(BaseModel):
    info_id: int
    upvote: bool  # True = 추천, False = 비추천


# ------------------------------------------------------------------
# 헬퍼 함수
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


def _fetch_photo_urls(menu_id: str) -> List[str]:
    """메뉴에 연결된 사진 URL 목록 조회 (match_photo 입력용)"""
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT photo_url FROM menus WHERE menu_id = ? AND photo_url IS NOT NULL",
        (menu_id,)
    )
    rows = cursor.fetchall()
    return [row[0] for row in rows if row[0]]


def _build_search_results(restaurants: list):
    """
    get_nearby_restaurants 결과에
    core_pros / core_cons / lat / lng 필드를 붙여서 반환
    [7-8주차] lat/lng 추가 - 프론트 지도 마커 표시용
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
                "distance_km": res["distance_km"],
                "lat": res.get("lat"),   # [7-8주차 추가] 지도 마커용
                "lng": res.get("lng")    # [7-8주차 추가] 지도 마커용
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
    radius: float,
    query: Optional[str] = None
):
    if USE_DUMMY:
        return {"results": DUMMY_SEARCH_RESULTS}

    try:
        restaurants = db.get_nearby_restaurants(lat, lng, radius)

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
    summary="AI 메뉴 요약 + 대표 사진 조회",
    description="menu_id에 해당하는 AI 요약 결과(장단점 요약)와 match_photo로 선택된 대표 사진 URL을 반환합니다."
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

        # [7-8주차] analyze_reviews가 async로 변경됐으므로 await 추가
        summary = await processor.analyze_reviews(menu_name, review_texts)

        # [7-8주차 추가] match_photo로 대표 사진 선택
        image_urls = _fetch_photo_urls(menu_id)
        best_photo = processor.match_photo(menu_name, image_urls)

        return {
            "menu_id": menu_id,
            "menu_name": menu_name,
            "photo_url": best_photo,   # match_photo 결과
            "summary": summary
        }
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
        db.update_vote(request.info_id, request.upvote)
        return {"message": "투표가 반영되었습니다.", "info_id": request.info_id, "upvote": request.upvote}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"투표 처리 중 오류 발생: {str(e)}")