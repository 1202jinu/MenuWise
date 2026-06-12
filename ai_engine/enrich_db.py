"""[2단계] AI 보강기.

DB(menu_wise.db)에 적재된 raw 리뷰/사진을 읽어
  - 리뷰에서 메뉴명 추출 + 리뷰↔메뉴 매칭
  - 메뉴별 핵심 장점/단점(core_info) 생성
  - 메뉴↔식당 사진 매칭(같은 식당 사진 풀에서만, 다른 음식/비음식 제외)
을 수행하고 결과를 다시 DB에 저장한다.

재실행 시 식당별 AI 산출물을 먼저 정리하므로 멱등하게 동작한다.
raw 리뷰/사진은 1단계(crawler/main.py) 결과를 그대로 사용한다.

실행: (프로젝트 루트에서) python ai_engine/enrich_db.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai_engine.ai_analyzer import MenuAIProcessor
from crawler.database_and_crawler import MenuWiseDB


def _assign_primary_menu(menu_records):
    """한 리뷰가 여러 메뉴에 매칭된 경우, 가장 구체적인(메뉴명이 긴) 메뉴 하나에만
    리뷰를 귀속시킨다. menu_id -> [review_id] 매핑을 반환한다."""
    assignments = {menu_id: [] for menu_id, _ in menu_records}
    chosen = set()

    # 메뉴명이 긴(구체적인) 메뉴부터 우선 배정한다.
    for menu_id, menu in sorted(
        menu_records,
        key=lambda record: len(record[1]["menu_name"]),
        reverse=True,
    ):
        for review in menu.get("reviews", []):
            review_id = review.get("review_id")
            if not review_id or review_id in chosen:
                continue

            chosen.add(review_id)
            assignments[menu_id].append(review_id)

    return assignments


async def enrich_one(db, processor, restaurant, reviews, photo_urls):
    res_id = restaurant["res_id"]
    res_name = restaurant["res_name"]

    dataset = await processor.build_menu_dataset(res_name, reviews, photo_urls)
    ai_menus = dataset.get("menus", [])

    if not ai_menus:
        print(f"  - 추출된 메뉴 없음(매칭 리뷰 부족). 건너뜀.")
        return 0

    # 이전 AI 산출물을 정리해 재실행에도 깨끗하게 덮어쓴다.
    db.clear_ai_enrichment(res_id)

    menu_records = [
        (f"{res_id}_MENU_{index}", menu)
        for index, menu in enumerate(ai_menus, start=1)
    ]

    menus_out = [
        {
            "menu_id": menu_id,
            "menu_name": menu["menu_name"],
            "price": 0,
            "photo_url": menu.get("photo_url", ""),
        }
        for menu_id, menu in menu_records
    ]
    core_info_out = {menu_id: menu.get("core_info", {}) for menu_id, menu in menu_records}

    db.save_restaurant_data({
        "restaurant": restaurant,
        "menus": menus_out,
        "reviews": [],
        "core_info": core_info_out,
    })

    # raw 리뷰를 대표 매칭 메뉴에 연결(menu_id UPDATE).
    assignments = _assign_primary_menu(menu_records)
    for menu_id, review_ids in assignments.items():
        db.assign_reviews_to_menu(review_ids, menu_id)

    matched_photos = sum(1 for menu in menus_out if menu["photo_url"])
    print(
        f"  - 메뉴 {len(menus_out)}개 / 사진매칭 {matched_photos}개 / "
        f"메뉴미언급 제외 리뷰 {dataset.get('dropped_review_count', 0)}개"
    )
    return len(menus_out)


async def enrich_all():
    db_path = os.getenv("MENUWISE_DB_PATH", str(ROOT_DIR / "menu_wise.db"))
    db = MenuWiseDB(db_path)
    processor = MenuAIProcessor()

    restaurants = db.get_all_restaurants()
    print(f"보강 대상 식당: {len(restaurants)}개 (DB: {db_path})")

    total_menus = 0

    for index, restaurant in enumerate(restaurants, start=1):
        res_id = restaurant["res_id"]
        res_name = restaurant["res_name"]
        print(f"[{index}/{len(restaurants)}] {res_name}")

        reviews = db.get_reviews_by_restaurant(res_id)
        if not reviews:
            print("  - 리뷰 없음. 건너뜀.")
            continue

        photo_urls = db.get_restaurant_photos(res_id)

        try:
            total_menus += await enrich_one(db, processor, restaurant, reviews, photo_urls)
        except Exception as exc:
            print(f"  - 보강 실패: {exc}")

    db.close()
    print(f"\n완료: 총 메뉴 {total_menus}개 생성.")


if __name__ == "__main__":
    asyncio.run(enrich_all())
