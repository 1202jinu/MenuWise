"""사용자 요청 데이터 보정(일회성).

1) 대주객 '간짜장' 메뉴 삭제 (식당은 유지)
2) 국수닭 '닭튀김' 메뉴 삭제
3) 순이네 '닭도리탕' → '닭볶음탕' 리뷰 병합 후 닭볶음탕 장단점 재정제(AI)
4) 굽네치킨춘천효자점 '추추치킨스테이크'/'순살치킨' 가격 22,000원

실행: (프로젝트 루트에서)
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONUTF8=1 python ai_engine/apply_corrections.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawler.database_and_crawler import MenuWiseDB


def _res_id(cur, name):
    row = cur.execute("SELECT res_id FROM restaurants WHERE res_name = ?", (name,)).fetchone()
    return row[0] if row else None


def _menu_id(cur, res_id, name):
    row = cur.execute(
        "SELECT menu_id FROM menus WHERE res_id = ? AND menu_name = ?", (res_id, name)
    ).fetchone()
    return row[0] if row else None


def _delete_menu(cur, res_id, name):
    mid = _menu_id(cur, res_id, name)
    if not mid:
        return False
    cur.execute("DELETE FROM core_info WHERE menu_id = ?", (mid,))
    cur.execute("UPDATE reviews SET menu_id = NULL WHERE menu_id = ?", (mid,))
    cur.execute("DELETE FROM menus WHERE menu_id = ?", (mid,))
    return True


async def main():
    db_path = os.getenv("MENUWISE_DB_PATH", str(ROOT_DIR / "menu_wise.db"))
    db = MenuWiseDB(db_path)
    cur = db.conn.cursor()

    # 1) 대주객 간짜장 삭제
    rid = _res_id(cur, "대주객")
    print("① 대주객 간짜장 삭제:", "완료" if rid and _delete_menu(cur, rid, "간짜장") else "대상 없음")

    # 2) 국수닭 닭튀김 삭제
    rid = _res_id(cur, "국수닭")
    print("② 국수닭 닭튀김 삭제:", "완료" if rid and _delete_menu(cur, rid, "닭튀김") else "대상 없음")

    # 4) 굽네치킨춘천효자점 가격
    rid = _res_id(cur, "굽네치킨춘천효자점")
    if rid:
        for mn, price in (("추추치킨스테이크", 22000), ("순살치킨", 22000)):
            cur.execute(
                "UPDATE menus SET price = ? WHERE res_id = ? AND menu_name = ?",
                (price, rid, mn),
            )
            print(f"④ 가격 {mn} = {price}원: {'완료' if cur.rowcount else '대상 없음'}")
    db.conn.commit()

    # 3) 순이네 닭도리탕 → 닭볶음탕 병합 + 재정제
    rid = _res_id(cur, "순이네")
    main_mid = _menu_id(cur, rid, "닭볶음탕") if rid else None
    dup_mid = _menu_id(cur, rid, "닭도리탕") if rid else None

    if main_mid and dup_mid:
        # 닭도리탕 리뷰를 닭볶음탕으로 재배정
        cur.execute("UPDATE reviews SET menu_id = ? WHERE menu_id = ?", (main_mid, dup_mid))
        # 닭도리탕 메뉴/장단점 제거
        cur.execute("DELETE FROM core_info WHERE menu_id = ?", (dup_mid,))
        cur.execute("DELETE FROM menus WHERE menu_id = ?", (dup_mid,))
        # 닭볶음탕 기존 장단점 제거(병합 리뷰로 재생성)
        cur.execute("DELETE FROM core_info WHERE menu_id = ?", (main_mid,))
        db.conn.commit()

        texts = [
            row[0]
            for row in cur.execute(
                "SELECT content FROM reviews WHERE menu_id = ? ORDER BY review_id", (main_mid,)
            ).fetchall()
            if row[0]
        ]

        # AI 재정제 (LLM)
        from ai_engine.ai_analyzer import MenuAIProcessor

        processor = MenuAIProcessor()
        summary = await processor.analyze_reviews("닭볶음탕", texts)
        rows = db.transform_ai_core_info(main_mid, summary)
        for info in rows:
            cur.execute(
                """INSERT INTO core_info (menu_id, content, info_type, level, upvotes, downvotes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    info["menu_id"],
                    info["content"],
                    info["info_type"],
                    info["level"],
                    info.get("upvotes", 0),
                    info.get("downvotes", 0),
                ),
            )
        db.conn.commit()
        print(f"③ 순이네 닭도리탕→닭볶음탕 병합: 리뷰 {len(texts)}개 → 장단점 {len(rows)}개 재정제")
    elif main_mid and not dup_mid:
        print("③ 병합 스킵: 닭도리탕이 이미 없음(이미 병합됨)")
    else:
        print("③ 병합 스킵: 닭볶음탕 메뉴를 찾지 못함")

    db.close()
    print("\n완료.")


if __name__ == "__main__":
    asyncio.run(main())
