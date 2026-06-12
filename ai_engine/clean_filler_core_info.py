"""기존 core_info에서 '리뷰에 언급이 없다 / 정보가 부족하다'는 식의 내용 없는 문장을 삭제한다.

이런 문장은 실제 리뷰에서 뽑은 장단점이 아니라 AI가 만들어 낸 빈 설명이라,
삭제하면 프론트가 해당 탭에 '장점/단점에 대한 리뷰가 없습니다.' 안내만 표시한다.
연결된 댓글도 함께 정리한다. 재실행해도 안전하다(멱등).

실행: (프로젝트 루트에서) python ai_engine/clean_filler_core_info.py
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawler.database_and_crawler import MenuWiseDB, is_filler_core_info


def clean():
    db_path = os.getenv("MENUWISE_DB_PATH", str(ROOT_DIR / "menu_wise.db"))
    db = MenuWiseDB(db_path)
    cursor = db.conn.cursor()

    rows = cursor.execute("SELECT info_id, content FROM core_info").fetchall()
    filler_ids = [info_id for info_id, content in rows if is_filler_core_info(content)]

    comments_removed = 0
    for info_id in filler_ids:
        cursor.execute("DELETE FROM comments WHERE info_id = ?", (info_id,))
        comments_removed += cursor.rowcount
        cursor.execute("DELETE FROM core_info WHERE info_id = ?", (info_id,))

    db.conn.commit()
    remaining = cursor.execute("SELECT COUNT(*) FROM core_info").fetchone()[0]
    db.close()

    print(f"내용 없는 장단점 {len(filler_ids)}개 삭제 (댓글 {comments_removed}개 함께 정리)")
    print(f"남은 core_info: {remaining}개 (DB: {db_path})")


if __name__ == "__main__":
    clean()
