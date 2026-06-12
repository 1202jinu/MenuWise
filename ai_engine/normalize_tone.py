"""기존 core_info(장단점)의 어투를 정중한 존댓말로 일관되게 정규화한다.

메뉴/구조는 그대로 두고 content 문장만 LLM으로 다시 쓴다(의미 유지).
실행: (프로젝트 루트에서) python ai_engine/normalize_tone.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai_engine.ai_analyzer import MenuAIProcessor
from crawler.database_and_crawler import MenuWiseDB

CHUNK_SIZE = 25


def _build_prompt(chunk):
    payload = json.dumps(chunk, ensure_ascii=False)
    return f"""다음은 음식 메뉴의 장단점 문장 목록입니다.
각 content를 의미는 그대로 유지하되, 정중한 존댓말(~습니다/~합니다 체)로 어투만 통일해 다시 써 주세요.
- 사실/의미를 바꾸지 말 것, 새로운 내용 추가 금지
- 한 문장으로 간결하게
- id는 그대로 유지
- 반드시 아래 JSON 형식만 출력(설명/마크다운 금지)

입력: {payload}

출력 형식:
{{ "items": [ {{ "id": 1, "content": "정중한 존댓말 문장입니다." }} ] }}
"""


async def normalize():
    db_path = os.getenv("MENUWISE_DB_PATH", str(ROOT_DIR / "menu_wise.db"))
    db = MenuWiseDB(db_path)
    cursor = db.conn.cursor()
    rows = cursor.execute("SELECT info_id, content FROM core_info").fetchall()
    items = [{"id": row[0], "content": row[1]} for row in rows if row[1]]
    print(f"대상 core_info: {len(items)}개 (DB: {db_path})")

    processor = MenuAIProcessor()
    updated = 0

    for start in range(0, len(items), CHUNK_SIZE):
        chunk = items[start:start + CHUNK_SIZE]
        prompt = _build_prompt(chunk)
        try:
            raw = await processor._generate_summary_with_llm(prompt)
            raw = processor._extract_json(raw)
            result = json.loads(raw)
        except Exception as exc:
            print(f"  청크 실패({start}): {exc}")
            continue

        rewritten = result.get("items", []) if isinstance(result, dict) else result
        for item in rewritten:
            if not isinstance(item, dict):
                continue
            info_id = item.get("id")
            content = str(item.get("content", "")).strip()
            if info_id is not None and content:
                cursor.execute(
                    "UPDATE core_info SET content = ? WHERE info_id = ?",
                    (content, info_id),
                )
                updated += 1

        db.conn.commit()
        print(f"  {min(start + CHUNK_SIZE, len(items))}/{len(items)} 처리")

    db.close()
    print(f"완료: {updated}개 문장 존댓말로 정규화")


if __name__ == "__main__":
    asyncio.run(normalize())
