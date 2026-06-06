# backend_server.py
import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트(.env) 로드
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware   # 추가
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(
    title="MenuWise API",
    description="음식점 리뷰 기반 메뉴 추천 시스템 백엔드 API - /docs 에서 전체 명세 확인 가능",
    version="0.1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 개발/테스트용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        "lat": 37.8813,
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
        "lat": 37.8821,
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

# 피드백 4: AI 응답을 level_1/level_2 최상위 구조로 통일 (summary 키 제거)
DUMMY_SUMMARY = {
    "menu_id": "menu_001",
    "menu_name": "순대국밥",
    "photo_url": "https://example.com/photo1.jpg",
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

def _fetch_photo_urls(menu_id: str) -> List[str]:
    """
    리뷰에 첨부된 사진 URL 목록 조회
    AI match_photo 입력용 — reviews 테이블 기준
    [완성] db None 체크 추가
    """
    if db is None:
        return []
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT photo_url
        FROM reviews
        WHERE menu_id = ?
        AND photo_url IS NOT NULL
    """, (menu_id,))
    rows = cursor.fetchall()
    return [row[0] for row in rows if row[0]]


def _save_ai_summary(menu_id: str, summary: dict):
    """
    AI 요약 결과를 core_info 테이블에 저장
    [완성] transform_ai_core_info는 변환만 하므로 변환 후 INSERT까지 직접 수행
    """
    if db is None:
        return
    transformed = db.transform_ai_core_info(menu_id, summary)
    cursor = db.conn.cursor()
    for info in transformed:
        # 동일 내용이 이미 있으면 중복 저장 방지
        cursor.execute("""
            SELECT info_id FROM core_info
            WHERE menu_id = ? AND content = ? AND info_type = ? AND level = ?
        """, (info["menu_id"], info["content"], info["info_type"], info["level"]))
        if cursor.fetchone():
            continue
        cursor.execute("""
            INSERT INTO core_info (menu_id, content, info_type, level, upvotes, downvotes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            info["menu_id"],
            info["content"],
            info["info_type"],
            info["level"],
            info.get("upvotes", 0),
            info.get("downvotes", 0)
        ))
    db.conn.commit()


# TODO: db.search_menus가 menus/restaurants JOIN 완성형으로 업그레이드되면
# _build_search_results 삭제 후 db.search_menus 결과를 바로 리턴하도록 단순화
def _build_search_results(restaurants: list):
    """
    get_nearby_restaurants 결과에 core_pros/core_cons/lat/lng 필드를 붙여서 반환
    """
    if db is None:
        return []

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
                "lat": res.get("lat"),
                "lng": res.get("lng")
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

    if db is None:
        raise HTTPException(status_code=503, detail="DB가 초기화되지 않았습니다.")

    try:
        # [완성] query 있을 때 db.search_menus 연결 (DB 파트에 구현 완료된 메서드)
        if query:
            restaurants = db.search_menus(query, lat, lng, radius)
        else:
            restaurants = db.get_nearby_restaurants(lat, lng, radius)

        results = _build_search_results(restaurants)

        results.sort(
            key=lambda x: x.get("distance_km", float("inf"))
        )

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
        return {"details": DUMMY_DETAILS}

    if db is None:
        raise HTTPException(status_code=503, detail="DB가 초기화되지 않았습니다.")

    try:
        menu_data = db.get_menu_details(menu_id)
        if not menu_data:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 메뉴가 없습니다.")
        results = menu_data.get("core_info", [])
        return {"details": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상세 조회 중 오류 발생: {str(e)}")


@app.get(
    "/api/menu/{menu_id}/summary",
    summary="AI 메뉴 요약 + 대표 사진 조회",
    description="menu_id에 해당하는 AI 요약 결과(장단점 요약)와 대표 사진 URL을 반환합니다."
)
async def get_menu_summary(menu_id: str):
    if USE_DUMMY:
        return DUMMY_SUMMARY

    if db is None:
        raise HTTPException(status_code=503, detail="DB가 초기화되지 않았습니다.")
    if processor is None:
        raise HTTPException(status_code=503, detail="AI 프로세서가 초기화되지 않았습니다.")

    try:
        menu_data = db.get_menu_details(menu_id)
        if not menu_data:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 메뉴가 없습니다.")

        menu_name = menu_data["menu_name"]
        reviews = menu_data.get("core_info", [])
        review_texts = [r["content"] for r in reviews]

        # analyze_reviews는 async
        summary = await processor.analyze_reviews(menu_name, review_texts)

        # 피드백 1: match_photo는 동기 함수이므로 run_in_threadpool로 블로킹 방지
        image_urls = _fetch_photo_urls(menu_id)

        best_photo = ""

        if image_urls:
            best_photo = await run_in_threadpool(
                processor.match_photo,
                menu_name,
                image_urls
            )

        # [완성] AI 결과 변환 후 DB 저장까지 수행
        _save_ai_summary(menu_id, summary)

        # 피드백 4: level_1/level_2 최상위 구조로 통일
        return {
            "menu_id": menu_id,
            "menu_name": menu_name,
            "photo_url": best_photo,
            "level_1": summary.get("level_1", {}),
            "level_2": summary.get("level_2", [])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 요약 중 오류 발생: {str(e)}")


@app.post(
    "/api/vote",
    summary="리뷰 추천/비추천",
    description='info_id에 해당하는 리뷰에 추천(upvote=true) 또는 비추천(upvote=false)을 반영합니다.'
)
async def vote(request: VoteRequest):
    if USE_DUMMY:
        return {
            "message": f"info_id {request.info_id} 투표 완료 (더미)",
            "upvote": request.upvote
        }

    if db is None:
        raise HTTPException(
            status_code=503,
            detail="DB가 초기화되지 않았습니다."
        )

    try:
        affected = db.vote(
        request.info_id,
        request.upvote
        )

        if affected is None:
            raise HTTPException(
                status_code=404,
                detail=f"info_id {request.info_id}를 찾을 수 없습니다."
            )

        return {
            "message": "투표가 반영되었습니다.",
            "info_id": request.info_id,
            "upvote": request.upvote
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"투표 처리 중 오류 발생: {str(e)}"
        )