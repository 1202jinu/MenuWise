"""Collect extra restaurants around Kangwon National University.

This script was added after the first ai_crawl_input.txt crawl because the
initial dataset did not contain enough usable restaurants/reviews. It keeps the
first crawl result as the baseline, removes duplicate Google place_ids, and
creates ai_crawl_input_extra.txt with additional restaurants.

Flow:
1. Find more Google Places restaurant candidates with several local queries.
2. Remove places already present in crawler/ai_crawl_input.txt.
3. Sort candidates by Google user_ratings_total, descending.
4. Use Apify to collect reviews/photos for selected place_ids.
5. Write an ai_crawl_input-compatible txt file for team sharing.

Run from project root:
    python crawler/collect_extra_ai_crawl_input.py

Useful options:
    python crawler/collect_extra_ai_crawl_input.py --target-count 30
    python crawler/collect_extra_ai_crawl_input.py --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from apify_client import ApifyClient
except ModuleNotFoundError:
    ApifyClient = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EXISTING_INPUT = Path(__file__).with_name("ai_crawl_input.txt")
DEFAULT_OUTPUT = Path(__file__).with_name("ai_crawl_input_extra.txt")

DEFAULT_LAT = 37.8683
DEFAULT_LNG = 127.7445
DEFAULT_RADIUS_M = 3000
DEFAULT_TARGET_COUNT = 28
DEFAULT_REVIEW_LIMIT = 40
DEFAULT_PHOTO_LIMIT = 30

SEARCH_QUERIES = [
    "춘천 강원대학교 음식점",
    "춘천 강원대 맛집",
    "강원대 후문 음식점",
    "강원대 정문 음식점",
    "춘천 효자동 음식점",
    "춘천 석사동 음식점",
    "춘천 애막골 맛집",
    "춘천 백령로 음식점",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect extra Google/Apify crawl results in ai_crawl_input txt format."
    )
    parser.add_argument("--existing-input", default=str(DEFAULT_EXISTING_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lng", type=float, default=DEFAULT_LNG)
    parser.add_argument("--radius-m", type=int, default=DEFAULT_RADIUS_M)
    parser.add_argument("--target-count", type=int, default=DEFAULT_TARGET_COUNT)
    parser.add_argument("--review-limit", type=int, default=DEFAULT_REVIEW_LIMIT)
    parser.add_argument("--photo-limit", type=int, default=DEFAULT_PHOTO_LIMIT)
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=4,
        help="Collect this many candidate slots before taking target-count.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only collect/rank Google candidates. Do not call Apify.",
    )
    parser.add_argument(
        "--dataset-id",
        default="",
        help="Read an existing Apify Dataset ID instead of running the Actor again.",
    )
    return parser.parse_args()


def load_env():
    for candidate in (
        ROOT_DIR / ".env",
        ROOT_DIR / ".env.example",
        Path(__file__).with_name(".env"),
    ):
        if candidate.exists():
            load_dotenv(dotenv_path=candidate)
    load_dotenv()


def read_existing_place_ids(path):
    path = Path(path)
    if not path.exists():
        return set(), set()

    text = path.read_text(encoding="utf-8", errors="replace")
    place_ids = set(re.findall(r"(?m)^- place_id:\s*(\S+)\s*$", text))
    res_ids = set(re.findall(r"(?m)^- res_id:\s*(\S+)\s*$", text))

    for res_id in list(res_ids):
        if res_id.startswith("GOOGLE_"):
            place_ids.add(res_id.replace("GOOGLE_", "", 1))

    return place_ids, res_ids


def google_text_search(api_key, query, lat, lng, radius_m, max_pages=3):
    endpoint = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "location": f"{lat},{lng}",
        "radius": radius_m,
        "type": "restaurant",
        "language": "ko",
        "key": api_key,
    }

    results = []
    page_token = None
    for page in range(max_pages):
        request_params = dict(params)
        if page_token:
            request_params = {"pagetoken": page_token, "key": api_key, "language": "ko"}
            time.sleep(2)

        data = request_json(endpoint, request_params)
        status = data.get("status")
        if status not in {"OK", "ZERO_RESULTS"}:
            print(f"[Google] {query} page {page + 1} status={status}: {data.get('error_message', '')}")
            break

        results.extend(data.get("results", []))
        page_token = data.get("next_page_token")
        if not page_token:
            break

    return results


def request_json(endpoint, params, timeout=20):
    url = f"{endpoint}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "MenuWiseCrawler/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_google_candidates(api_key, args, existing_place_ids):
    candidates = {}

    for query in SEARCH_QUERIES:
        print(f"[Google] search: {query}")
        for place in google_text_search(
            api_key,
            query,
            args.lat,
            args.lng,
            args.radius_m,
        ):
            place_id = place.get("place_id")
            if not place_id or place_id in existing_place_ids:
                continue

            geometry = place.get("geometry") or {}
            location = geometry.get("location") or {}
            lat = location.get("lat")
            lng = location.get("lng")
            if lat is None or lng is None:
                continue

            distance_m = haversine_m(args.lat, args.lng, lat, lng)
            if distance_m > args.radius_m:
                continue

            previous = candidates.get(place_id)
            item = {
                "place_id": place_id,
                "res_id": f"GOOGLE_{place_id}",
                "res_name": place.get("name", ""),
                "category": category_from_types(place.get("types") or []),
                "lat": lat,
                "lng": lng,
                "place_rating": place.get("rating"),
                "place_reviews_count": int(place.get("user_ratings_total") or 0),
                "distance_m": round(distance_m, 1),
                "source_query": query,
            }

            if not previous or item["place_reviews_count"] > previous["place_reviews_count"]:
                candidates[place_id] = item

    ranked = sorted(
        candidates.values(),
        key=lambda item: (item["place_reviews_count"], -item["distance_m"]),
        reverse=True,
    )
    max_candidates = max(args.target_count, args.target_count * args.candidate_multiplier)
    return ranked[:max_candidates]


def category_from_types(types):
    for type_name in types:
        if type_name in {"restaurant", "food", "point_of_interest", "establishment"}:
            continue
        return type_name
    return "restaurant"


def haversine_m(lat1, lng1, lat2, lng2):
    from math import atan2, cos, radians, sin, sqrt

    radius = 6371000
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    )
    return radius * 2 * atan2(sqrt(a), sqrt(1 - a))


def run_apify_reviews(candidates, args):
    if ApifyClient is None:
        raise RuntimeError("apify-client is not installed. Run: pip install apify-client")

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError("APIFY_API_TOKEN must be set in .env")

    if args.dataset_id:
        print(f"[Apify] reading existing dataset={args.dataset_id}")
        return read_apify_dataset(token, args.dataset_id)

    actor_id = os.getenv("APIFY_ACTOR_ID")
    if not actor_id:
        raise RuntimeError("APIFY_ACTOR_ID must be set in .env")

    place_ids = [item["place_id"] for item in candidates[: args.target_count]]
    actor_input = {
        "include_personal": False,
        "limit": args.review_limit,
        "order": "most_relevant",
        "place_ids": place_ids,
        "place_urls": [],
        "rating": "0.0",
        "search_limit": len(place_ids),
        "source": "all",
        "lang": "ko",
        "searchKeyword": "",
        "search_location": "",
        "search_coordination": "",
        "maxConcurrency": int(os.getenv("APIFY_MAX_CONCURRENCY", "2")),
    }

    print(f"[Apify] actor={actor_id}, places={len(place_ids)}, reviews/place={args.review_limit}")
    client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=actor_input)
    dataset_id = get_run_value(run, "defaultDatasetId", "default_dataset_id")
    if not dataset_id:
        return []

    items = []
    for item in client.dataset(dataset_id).iterate_items():
        items.append(item)

    print(f"[Apify] dataset items: {len(items)}")
    return items


def read_apify_dataset(token, dataset_id):
    if ApifyClient is None:
        raise RuntimeError("apify-client is not installed. Run: pip install apify-client")

    client = ApifyClient(token)
    items = []
    for item in client.dataset(dataset_id).iterate_items():
        items.append(item)

    print(f"[Apify] dataset items: {len(items)}")
    return items


def get_run_value(run, *names):
    for name in names:
        if isinstance(run, dict) and name in run:
            return run[name]

        value = getattr(run, name, None)
        if value:
            return value

        if hasattr(run, "model_dump"):
            data = run.model_dump(by_alias=True)
            if name in data:
                return data[name]
            snake_name = camel_to_snake(name)
            if snake_name in data:
                return data[snake_name]

    return None


def camel_to_snake(value):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def group_apify_items(items):
    grouped = {}
    for item in items:
        place_id = item.get("place_id")
        if place_id:
            grouped.setdefault(place_id, []).append(item)
    return grouped


def collect_photo_urls(apify_reviews, limit):
    urls = []
    seen = set()

    for review in apify_reviews:
        candidates = []
        if review.get("place_photo_url"):
            candidates.append(review["place_photo_url"])
        candidates.extend(review.get("review_photos_urls") or [])

        for url in candidates:
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= limit:
                return urls

    return urls


def collect_review_texts(apify_reviews, limit):
    texts = []
    seen = set()

    for review in apify_reviews:
        content = str(review.get("content") or "").strip()
        if not content or content in seen:
            continue
        seen.add(content)
        texts.append(content)
        if len(texts) >= limit:
            break

    return texts


def merge_candidates_with_apify(candidates, apify_items, args):
    grouped = group_apify_items(apify_items)
    merged = []

    for candidate in candidates[: args.target_count]:
        reviews = grouped.get(candidate["place_id"], [])
        first = reviews[0] if reviews else {}
        location = first.get("location") or {}

        merged.append({
            **candidate,
            "res_name": first.get("place_name") or candidate["res_name"],
            "category": first_category(first, candidate["category"]),
            "lat": location.get("lat", candidate["lat"]),
            "lng": location.get("lng", candidate["lng"]),
            "place_rating": first.get("place_rating", candidate["place_rating"]),
            "place_reviews_count": first.get(
                "place_reviews_count",
                candidate["place_reviews_count"],
            ),
            "photo_urls": collect_photo_urls(reviews, args.photo_limit),
            "review_texts": collect_review_texts(reviews, args.review_limit),
        })

    return merged


def first_category(apify_item, fallback):
    categories = apify_item.get("categories")
    if isinstance(categories, list) and categories:
        return categories[0]
    return apify_item.get("category") or fallback or "restaurant"


def write_ai_crawl_input(restaurants, output_path, args):
    lines = [
        "MenuWise AI Crawl Input Extra",
        f"center: Kangwon National University, Chuncheon",
        f"lat/lng: {args.lat}, {args.lng}",
        f"radius_m: {args.radius_m}",
        f"restaurant_count: {len(restaurants)}",
        "",
    ]

    for index, item in enumerate(restaurants, start=1):
        photo_urls = item.get("photo_urls") or []
        review_texts = item.get("review_texts") or []

        lines.extend([
            f"[{index}] {item.get('res_name', '')}",
            f"- res_id: {item.get('res_id', '')}",
            f"- category: {item.get('category', '')}",
            f"- lat/lng: {item.get('lat', '')}, {item.get('lng', '')}",
            f"- place_id: {item.get('place_id', '')}",
            f"- place_rating: {item.get('place_rating', '')}",
            f"- place_reviews_count: {item.get('place_reviews_count', '')}",
            f"- source_query: {item.get('source_query', '')}",
            "- photo_urls:",
        ])

        if photo_urls:
            lines.extend(f"  * {url}" for url in photo_urls[: args.photo_limit])
        else:
            lines.append("  * no photos")

        lines.append("- reviews:")
        if review_texts:
            lines.extend(f"  * {text}" for text in review_texts[: args.review_limit])
        else:
            lines.append("  * no reviews")

        lines.append("")

    output_path = Path(output_path)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Output] saved: {output_path}")


def write_candidate_preview(candidates, output_path):
    preview_path = Path(output_path).with_suffix(".candidates.txt")
    lines = ["MenuWise Extra Candidate Preview", f"candidate_count: {len(candidates)}", ""]
    for index, item in enumerate(candidates, start=1):
        lines.append(
            f"[{index}] {item['res_name']} / reviews={item['place_reviews_count']} "
            f"/ distance_m={item['distance_m']} / place_id={item['place_id']}"
        )
    preview_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Output] candidate preview: {preview_path}")


def main():
    args = parse_args()
    load_env()

    google_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not google_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY must be set in .env")

    existing_place_ids, _ = read_existing_place_ids(args.existing_input)
    print(f"[Existing] place_ids: {len(existing_place_ids)}")

    candidates = collect_google_candidates(google_key, args, existing_place_ids)
    print(f"[Google] unique new candidates: {len(candidates)}")
    write_candidate_preview(candidates, args.output)

    selected = candidates[: args.target_count]
    if args.dry_run:
        print("[Dry run] skipped Apify and txt export with reviews/photos.")
        return

    apify_items = run_apify_reviews(selected, args)
    restaurants = merge_candidates_with_apify(selected, apify_items, args)
    write_ai_crawl_input(restaurants, args.output, args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
