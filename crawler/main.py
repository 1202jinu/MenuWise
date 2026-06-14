"""[1단계] raw 적재기.

crawler/ai_crawl_input.txt(크롤링 결과 텍스트)를 파싱해 식당/리뷰/사진 후보를
AI 가공 없이 DB(menu_wise.db)에 그대로 저장한다.
외부 API 호출이나 json/txt 파일 출력은 하지 않는다.

메뉴 추출/매칭/핵심정보 생성은 2단계(ai_engine/enrich_db.py)에서 수행한다.
"""

import argparse
import hashlib
import os
import re
from pathlib import Path

from database_and_crawler import MenuWiseDB


ROOT_DIR = Path(__file__).resolve().parents[1]
AI_CRAWL_INPUT_FILE = Path(__file__).with_name("ai_crawl_input.txt")
AI_CRAWL_INPUT_EXTRA_FILE = Path(__file__).with_name("ai_crawl_input_extra.txt")


def _db_path():
    """실행 위치와 무관하게 항상 프로젝트 루트의 DB를 사용한다."""
    return os.getenv("MENUWISE_DB_PATH", str(ROOT_DIR / "menu_wise.db"))


def _extract_single_line(section, prefix):
    for line in section.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()

    return ""


def _extract_bullet_block(section, header):
    """`- header:` 다음에 오는 `  * 값` 라인들을 모아 반환한다."""
    values = []
    in_block = False

    for line in section.splitlines():
        if line.strip() == header:
            in_block = True
            continue

        if not in_block:
            continue

        # 다음 항목(`- `) 또는 다음 식당(`[n] `)을 만나면 블록 종료.
        if line.startswith("- ") or re.match(r"^\[\d+\]\s", line):
            break

        stripped = line.strip()
        if stripped.startswith("* "):
            value = stripped[2:].strip()
            if value and not value.startswith("no "):
                values.append(value)

    return values


def _parse_lat_lng(text):
    if not text or "," not in text:
        return None, None

    lat_text, lng_text = text.split(",", 1)
    try:
        return float(lat_text.strip()), float(lng_text.strip())
    except ValueError:
        return None, None


def parse_ai_crawl_input(path=AI_CRAWL_INPUT_FILE):
    """ai_crawl_input.txt를 식당 단위 dict 리스트로 파싱한다."""
    path = Path(path)
    if not path.exists():
        print(f"{path} 파일을 찾을 수 없습니다.")
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    section_pattern = re.compile(r"(?m)^\[(\d+)\]\s(.+)$")
    matches = list(section_pattern.finditer(text))

    restaurants = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[start:end]

        res_id = _extract_single_line(section, "- res_id: ")
        if not res_id:
            continue

        lat, lng = _parse_lat_lng(_extract_single_line(section, "- lat/lng: "))

        restaurants.append({
            "res_id": res_id,
            "res_name": match.group(2).strip(),
            "category": _extract_single_line(section, "- category: ") or "음식점",
            "lat": lat,
            "lng": lng,
            "photo_urls": _extract_bullet_block(section, "- photo_urls:"),
            "review_texts": _extract_bullet_block(section, "- reviews:"),
        })

    return restaurants


def _build_reviews(res_id, review_texts):
    reviews = []
    seen = set()

    for content in review_texts:
        content = content.strip()
        if not content or content in seen:
            continue

        seen.add(content)
        review_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        reviews.append({
            "review_id": f"{res_id}_{review_hash}",
            "content": content,
            "photo_url": "",
        })

    return reviews


def load_ai_crawl_input_to_db(path=AI_CRAWL_INPUT_FILE):
    """파싱한 raw 데이터를 DB에 저장한다."""
    restaurants = parse_ai_crawl_input(path)
    if not restaurants:
        print("저장할 식당 데이터가 없습니다.")
        return []

    db = MenuWiseDB(_db_path())

    total_reviews = 0
    total_photos = 0

    for item in restaurants:
        restaurant = {
            "res_id": item["res_id"],
            "res_name": item["res_name"],
            "lat": item["lat"],
            "lng": item["lng"],
            "category": item["category"],
        }
        reviews = _build_reviews(item["res_id"], item["review_texts"])
        photo_urls = item["photo_urls"]

        db.save_restaurant_raw(restaurant, reviews, photo_urls)

        total_reviews += len(reviews)
        total_photos += len(photo_urls)

    db.close()

    print(f"저장한 식당: {len(restaurants)}개")
    print(f"저장한 리뷰: {total_reviews}개")
    print(f"저장한 사진 후보: {total_photos}개")
    print("다음 단계: python ai_engine/enrich_db.py 로 메뉴/핵심정보를 채우세요.")
    return restaurants


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load MenuWise ai_crawl_input txt files into menu_wise.db."
    )
    parser.add_argument(
        "--input",
        default=str(AI_CRAWL_INPUT_FILE),
        help="Path to one ai_crawl_input-compatible txt file.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Load both ai_crawl_input.txt and ai_crawl_input_extra.txt if they exist.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.all:
        for path in (AI_CRAWL_INPUT_FILE, AI_CRAWL_INPUT_EXTRA_FILE):
            if not path.exists():
                print(f"{path} 파일을 찾을 수 없습니다. 건너뜁니다.")
                continue

            print(f"\n=== Loading {path} ===")
            load_ai_crawl_input_to_db(path)
        return

    load_ai_crawl_input_to_db(args.input)


if __name__ == "__main__":
    main()
