import os
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False


def _load_env_files() -> None:
    current_dir = Path(__file__).resolve().parent
    for candidate in (current_dir / ".env", current_dir.parent / ".env", current_dir.parent.parent / ".env"):
        if candidate.exists():
            load_dotenv(dotenv_path=candidate)
    load_dotenv()


def _add_import_paths() -> None:
    current_dir = Path(__file__).resolve().parent
    for candidate in (current_dir, current_dir.parent, current_dir.parent.parent):
        path = str(candidate)
        if path not in sys.path:
            sys.path.insert(0, path)


_add_import_paths()
_load_env_files()

app = FastAPI(
    title="MenuWise API",
    description="음식점 리뷰 기반 메뉴 추천 시스템 백엔드 API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USE_DUMMY = os.getenv("USE_DUMMY", "0").lower() in {"1", "true", "yes", "y"}

db = None
db_init_error = None
try:
    from crawler.database_and_crawler import MenuWiseDB

    db = MenuWiseDB(os.getenv("MENUWISE_DB_PATH", "menu_wise.db"))
except Exception as exc:  # 서버는 띄우되 /health에서 원인을 확인할 수 있게 둔다.
    db_init_error = str(exc)

processor = None
ai_init_error = None
try:
    from ai_engine.ai_analyzer import MenuAIProcessor

    processor = MenuAIProcessor(os.getenv("OPENAI_API_KEY", ""))
except Exception as exc:
    ai_init_error = str(exc)


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
        "lng": 127.7298,
        "category": "한식",
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
        "lng": 127.7310,
        "category": "분식",
    },
]

DUMMY_DETAILS = [
    {
        "info_id": 1,
        "menu_id": "menu_001",
        "content": "국물이 정말 진하고 맛있어요. 고기도 푸짐해서 가성비가 좋습니다.",
        "info_type": "PROS",
        "level": 2,
        "upvotes": 12,
        "downvotes": 1,
    },
    {
        "info_id": 2,
        "menu_id": "menu_001",
        "content": "간이 센 편이라 짜게 느낄 수 있습니다.",
        "info_type": "CONS",
        "level": 2,
        "upvotes": 5,
        "downvotes": 2,
    },
]

DUMMY_SUMMARY = {
    "menu_id": "menu_001",
    "menu_name": "순대국밥",
    "photo_url": "https://example.com/photo1.jpg",
    "level_1": {
        "pros": "진한 국물, 푸짐한 고기, 좋은 가성비",
        "cons": "간이 센 편",
    },
    "level_2": [
        {"content": "국물이 진하고 깊은 맛이 납니다.", "type": "PROS"},
        {"content": "고기 양이 많아 든든합니다.", "type": "PROS"},
        {"content": "짜게 느낄 수 있습니다.", "type": "CONS"},
    ],
}


class VoteRequest(BaseModel):
    info_id: int
    upvote: bool


def _require_db():
    if db is None:
        detail = "DB가 초기화되지 않았습니다."
        if db_init_error:
            detail = f"{detail} 원인: {db_init_error}"
        raise HTTPException(status_code=503, detail=detail)
    return db


def _require_ai():
    if processor is None:
        detail = "AI 프로세서가 초기화되지 않았습니다."
        if ai_init_error:
            detail = f"{detail} 원인: {ai_init_error}"
        raise HTTPException(status_code=503, detail=detail)
    return processor


def _split_keywords(keywords: Optional[str]) -> List[str]:
    if not keywords:
        return []
    return [keyword.strip() for keyword in keywords.split(",") if keyword.strip()]


def _fetch_review_texts(menu_id: str) -> List[str]:
    database = _require_db()
    cursor = database.conn.cursor()
    cursor.execute(
        """
        SELECT content
        FROM reviews
        WHERE menu_id = ?
        ORDER BY review_id ASC
        """,
        (menu_id,),
    )
    return [row[0] for row in cursor.fetchall() if row[0]]


def _fetch_photo_urls(menu_id: str) -> List[str]:
    database = _require_db()
    cursor = database.conn.cursor()
    cursor.execute(
        """
        SELECT photo_url
        FROM reviews
        WHERE menu_id = ?
          AND photo_url IS NOT NULL
          AND photo_url != ''
        """,
        (menu_id,),
    )
    return [row[0] for row in cursor.fetchall() if row[0]]


def _save_ai_summary(menu_id: str, summary: dict) -> None:
    database = _require_db()
    transformed = database.transform_ai_core_info(menu_id, summary)
    cursor = database.conn.cursor()

    for info in transformed:
        content = (info.get("content") or "").strip()
        info_type = (info.get("info_type") or "PROS").strip()
        level = int(info.get("level", 2))

        if not content:
            continue

        cursor.execute(
            """
            SELECT info_id
            FROM core_info
            WHERE menu_id = ?
              AND content = ?
              AND info_type = ?
              AND level = ?
            """,
            (menu_id, content, info_type, level),
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            """
            INSERT INTO core_info (menu_id, content, info_type, level, upvotes, downvotes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                menu_id,
                content,
                info_type,
                level,
                int(info.get("upvotes", 0)),
                int(info.get("downvotes", 0)),
            ),
        )

    database.conn.commit()


@app.get("/health", summary="서버 상태 확인")
async def health():
    return {
        "ok": True,
        "use_dummy": USE_DUMMY,
        "db_ready": db is not None,
        "ai_ready": processor is not None,
        "db_error": db_init_error,
        "ai_error": ai_init_error,
    }


@app.get("/api/health", summary="API 상태 확인")
async def api_health():
    return await health()


@app.get(
    "/api/search",
    summary="주변 메뉴 검색",
    description="위치, 반경, 검색어, 맛 키워드 기준으로 메뉴 검색 결과를 반환합니다.",
)
async def search_menus(
    lat: float,
    lng: float,
    radius: Optional[float] = Query(default=None),
    radius_km: Optional[float] = Query(default=None),
    query: Optional[str] = "",
    search_mode: Optional[str] = None,
    keywords: Optional[str] = None,
):
    if USE_DUMMY:
        return {"results": DUMMY_SEARCH_RESULTS}

    database = _require_db()
    resolved_radius = radius_km if radius_km is not None else radius
    if resolved_radius is None:
        resolved_radius = 3.0

    try:
        results = database.search_menus(
            keyword=query or "",
            lat=lat,
            lng=lng,
            radius_km=resolved_radius,
            keywords=_split_keywords(keywords),
        )
        results.sort(key=lambda item: item.get("distance_km", float("inf")))
        return {"results": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {exc}") from exc


@app.get(
    "/api/menu/{menu_id}/details",
    summary="메뉴 상세 조회",
    description="menu_id에 해당하는 코어 리뷰 목록을 반환합니다.",
)
async def get_details(menu_id: str):
    if USE_DUMMY:
        return {"details": DUMMY_DETAILS}

    database = _require_db()
    try:
        menu_data = database.get_menu_details(menu_id)
        if not menu_data:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 메뉴가 없습니다.")
        return {"details": menu_data.get("core_info", [])}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"상세 조회 중 오류 발생: {exc}") from exc


@app.get(
    "/api/menu/{menu_id}/summary",
    summary="AI 메뉴 요약 + 대표 사진 조회",
    description="리뷰 원문을 AI로 요약하고 대표 사진 URL을 반환합니다.",
)
async def get_menu_summary(menu_id: str):
    if USE_DUMMY:
        return DUMMY_SUMMARY

    database = _require_db()
    ai_processor = _require_ai()

    try:
        menu_data = database.get_menu_details(menu_id)
        if not menu_data:
            raise HTTPException(status_code=404, detail=f"menu_id '{menu_id}'에 해당하는 메뉴가 없습니다.")

        menu_name = menu_data["menu_name"]
        review_texts = _fetch_review_texts(menu_id)
        if not review_texts:
            review_texts = [item["content"] for item in menu_data.get("core_info", []) if item.get("content")]

        summary = await ai_processor.analyze_reviews(menu_name, review_texts)
        _save_ai_summary(menu_id, summary)

        image_urls = _fetch_photo_urls(menu_id)
        fallback_photo = menu_data.get("photo_url") or ""
        best_photo = fallback_photo

        if image_urls:
            matched_photo = await run_in_threadpool(ai_processor.match_photo, menu_name, image_urls)
            if matched_photo and matched_photo != "default_url":
                best_photo = matched_photo

        return {
            "menu_id": menu_id,
            "menu_name": menu_name,
            "photo_url": best_photo,
            "level_1": summary.get("level_1", {}),
            "level_2": summary.get("level_2", []),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI 요약 중 오류 발생: {exc}") from exc


@app.post(
    "/api/vote",
    summary="리뷰 추천/비추천",
    description="info_id에 해당하는 핵심 정보에 추천 또는 비추천을 반영합니다.",
)
async def vote(request: VoteRequest):
    if USE_DUMMY:
        return {
            "message": f"info_id {request.info_id} 투표 완료 (더미)",
            "info_id": request.info_id,
            "upvote": request.upvote,
            "upvotes": 0,
            "downvotes": 0,
        }

    database = _require_db()

    try:
        result = database.vote(request.info_id, request.upvote)
        if result is None:
            raise HTTPException(status_code=404, detail=f"info_id {request.info_id}를 찾을 수 없습니다.")

        return {
            "message": "투표가 반영되었습니다.",
            "info_id": result["info_id"],
            "upvote": request.upvote,
            "upvotes": result["upvotes"],
            "downvotes": result["downvotes"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"투표 처리 중 오류 발생: {exc}") from exc
