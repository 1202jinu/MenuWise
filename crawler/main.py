import json
import os
from pathlib import Path
from urllib.parse import quote_plus

from database_and_crawler import (
    MenuWiseDB,
    ReviewCrawler,
    convert_apify_groups_to_restaurant_data,
    group_apify_reviews_by_place,
    load_apify_reviews_from_file,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
APIFY_REVIEWS_FILE = Path(__file__).with_name("apify_reviews.json")
AI_CRAWL_INPUT_FILE = Path(__file__).with_name("ai_crawl_input.txt")
GOOGLE_PLACE_CANDIDATES_FILE = Path(__file__).with_name("google_place_candidates.txt")

KANGWON_UNIV_LAT = 37.8683
KANGWON_UNIV_LNG = 127.7445
RADIUS_M = 2000
RESTAURANT_LIMIT = 50
APIFY_REVIEW_LIMIT = 40
APIFY_PHOTO_LIMIT = 30
APIFY_MAX_CONCURRENCY = int(os.getenv("APIFY_MAX_CONCURRENCY", "2"))


def export_google_place_candidates():
    crawler = ReviewCrawler(
        center_lat=KANGWON_UNIV_LAT,
        center_lng=KANGWON_UNIV_LNG,
        radius_m=RADIUS_M,
    )
    restaurants = crawler.crawl_restaurant_info(
        "강원대",
        lat=KANGWON_UNIV_LAT,
        lng=KANGWON_UNIV_LNG,
        radius_m=RADIUS_M,
        limit=RESTAURANT_LIMIT,
    )

    lines = [
        "MenuWise Google Place Candidates",
        f"center: {KANGWON_UNIV_LAT}, {KANGWON_UNIV_LNG}",
        f"radius_m: {RADIUS_M}",
        f"count: {len(restaurants)}",
        "",
        "Use these place_ids as Apify Google Maps Reviews Scraper input.",
        "",
    ]

    for index, item in enumerate(restaurants, start=1):
        restaurant = item.get("restaurant", {})
        source = item.get("source", {})
        res_id = restaurant.get("res_id", "")
        place_id = res_id.replace("GOOGLE_", "", 1)

        lines.extend([
            f"[{index}] {restaurant.get('res_name', '')}",
            f"- place_id: {place_id}",
            f"- res_id: {res_id}",
            f"- lat/lng: {restaurant.get('lat', '')}, {restaurant.get('lng', '')}",
            f"- user_ratings_total: {source.get('user_ratings_total', '')}",
            f"- place_url: {source.get('place_url', '')}",
            "",
        ])

    GOOGLE_PLACE_CANDIDATES_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved Google place candidates to {GOOGLE_PLACE_CANDIDATES_FILE}")
    return restaurants


def run_apify_reviews_scraper(restaurants):
    from apify_client import ApifyClient

    token = os.getenv("APIFY_API_TOKEN")
    actor_id = os.getenv("APIFY_ACTOR_ID")

    if not token or not actor_id:
        print("APIFY_API_TOKEN or APIFY_ACTOR_ID is not set. Skipping Apify run.")
        return []

    place_ids = extract_place_ids(restaurants)
    if not place_ids:
        print("No Google place_id values found. Skipping Apify run.")
        return []

    client = ApifyClient(token)
    items = call_apify_actor(client, actor_id, place_ids=place_ids)
    missing_place_ids = find_missing_place_ids(place_ids, items)

    if missing_place_ids:
        print(f"Retrying missing place_ids: {len(missing_place_ids)}")
        retry_items = call_apify_actor(client, actor_id, place_ids=missing_place_ids)
        items = merge_apify_items(items, retry_items)
        missing_place_ids = find_missing_place_ids(place_ids, items)

    if missing_place_ids:
        print(f"Retrying missing places with place_urls: {len(missing_place_ids)}")
        retry_urls = build_google_maps_place_urls(restaurants, missing_place_ids)
        retry_items = call_apify_actor(client, actor_id, place_urls=retry_urls)
        items = merge_apify_items(items, retry_items)
        missing_place_ids = find_missing_place_ids(place_ids, items)

    if missing_place_ids:
        print("Still missing place_ids after retries:")
        for place_id in missing_place_ids:
            print(f"- {place_id}")

    APIFY_REVIEWS_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved Apify reviews JSON to {APIFY_REVIEWS_FILE}")
    return items


def call_apify_actor(client, actor_id, place_ids=None, place_urls=None):
    place_ids = place_ids or []
    place_urls = place_urls or []
    target_count = len(place_ids) + len(place_urls)

    if target_count == 0:
        return []

    run_input = {
        "include_personal": False,
        "limit": APIFY_REVIEW_LIMIT,
        "order": "most_relevant",
        "place_ids": place_ids,
        "place_urls": place_urls,
        "rating": "0.0",
        "search_limit": target_count,
        "source": "all",
        "lang": "ko",
        "searchKeyword": "",
        "search_location": "",
        "search_coordination": "",
        "maxConcurrency": APIFY_MAX_CONCURRENCY,
    }

    run = client.actor(actor_id).call(run_input=run_input)
    dataset_id = get_apify_run_value(run, "defaultDatasetId", "default_dataset_id")

    if not dataset_id:
        print("Apify run completed, but defaultDatasetId was not returned.")
        return []

    return client.dataset(dataset_id).list_items().items


def get_apify_run_value(run, dict_key, attr_name):
    if isinstance(run, dict):
        return run.get(dict_key) or run.get(attr_name)

    return getattr(run, attr_name, None) or getattr(run, dict_key, None)


def extract_place_ids(restaurants):
    place_ids = []

    for item in restaurants:
        res_id = item.get("restaurant", {}).get("res_id", "")
        place_id = res_id.replace("GOOGLE_", "", 1)
        if place_id:
            place_ids.append(place_id)

    return place_ids


def find_missing_place_ids(expected_place_ids, items):
    scraped_place_ids = {
        item.get("place_id")
        for item in items
        if item.get("place_id")
    }

    return [
        place_id
        for place_id in expected_place_ids
        if place_id not in scraped_place_ids
    ]


def merge_apify_items(base_items, extra_items):
    merged = []
    seen = set()

    for item in list(base_items or []) + list(extra_items or []):
        key = item.get("review_id") or (
            item.get("place_id"),
            item.get("review_position"),
            item.get("content"),
        )

        if key in seen:
            continue

        seen.add(key)
        merged.append(item)

    return merged


def build_google_maps_place_urls(restaurants, target_place_ids):
    target_place_ids = set(target_place_ids)
    urls = []

    for item in restaurants:
        restaurant = item.get("restaurant", {})
        res_id = restaurant.get("res_id", "")
        place_id = res_id.replace("GOOGLE_", "", 1)

        if place_id not in target_place_ids:
            continue

        name = restaurant.get("res_name", "")
        query = quote_plus(name)
        urls.append(
            "https://www.google.com/maps/search/"
            f"?api=1&query={query}&query_place_id={place_id}"
        )

    return urls


def import_apify_reviews_to_db(items=None):
    if items is None:
        if not APIFY_REVIEWS_FILE.exists():
            print(f"{APIFY_REVIEWS_FILE} not found.")
            print("Run Apify automatically or save the Dataset JSON as crawler/apify_reviews.json.")
            return []

        items = load_apify_reviews_from_file(APIFY_REVIEWS_FILE)

    db = MenuWiseDB()
    grouped = group_apify_reviews_by_place(items)
    restaurants = convert_apify_groups_to_restaurant_data(
        grouped,
        review_limit=APIFY_REVIEW_LIMIT,
        photo_limit=APIFY_PHOTO_LIMIT,
    )

    for res_data in restaurants:
        db.save_restaurant_data(res_data)

    db.close()

    review_count = sum(len(item.get("reviews", [])) for item in restaurants)
    photo_count = sum(len(item.get("source", {}).get("photo_urls", [])) for item in restaurants)

    print(f"Imported restaurants: {len(restaurants)}")
    print(f"Imported reviews: {review_count}")
    print(f"Collected photo urls: {photo_count}")
    return restaurants


def export_ai_crawl_input(restaurants, google_restaurants=None):
    restaurants = fill_missing_google_candidates(restaurants, google_restaurants or [])

    lines = [
        "MenuWise AI Crawl Input",
        f"restaurant_count: {len(restaurants)}",
        "",
    ]

    for index, item in enumerate(restaurants, start=1):
        restaurant = item.get("restaurant", {})
        reviews = item.get("reviews", [])
        source = item.get("source", {})
        photo_urls = source.get("photo_urls", [])

        lines.extend([
            f"[{index}] {restaurant.get('res_name', '')}",
            f"- res_id: {restaurant.get('res_id', '')}",
            f"- category: {restaurant.get('category', '')}",
            f"- lat/lng: {restaurant.get('lat', '')}, {restaurant.get('lng', '')}",
            f"- place_id: {source.get('place_id', '')}",
            f"- place_rating: {source.get('place_rating', '')}",
            f"- place_reviews_count: {source.get('place_reviews_count', '')}",
            "- photo_urls:",
        ])

        if photo_urls:
            for url in photo_urls[:APIFY_PHOTO_LIMIT]:
                lines.append(f"  * {url}")
        else:
            lines.append("  * no photos")

        lines.append("- reviews:")
        if reviews:
            for review in reviews[:APIFY_REVIEW_LIMIT]:
                content = review.get("content", "").replace("\n", " ")
                lines.append(f"  * {content}")
        else:
            lines.append("  * no reviews")

        lines.append("")

    AI_CRAWL_INPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved AI crawl input to {AI_CRAWL_INPUT_FILE}")


def fill_missing_google_candidates(restaurants, google_restaurants):
    if not google_restaurants:
        google_restaurants = load_google_place_candidates_from_file()

    existing_res_ids = {
        item.get("restaurant", {}).get("res_id")
        for item in restaurants
    }
    filled = list(restaurants)

    for item in google_restaurants:
        restaurant = item.get("restaurant", {})
        res_id = restaurant.get("res_id")

        if not res_id or res_id in existing_res_ids:
            continue

        source = item.get("source", {})
        place_id = res_id.replace("GOOGLE_", "", 1)
        filled.append({
            "restaurant": restaurant,
            "menus": item.get("menus", []),
            "reviews": [],
            "source": {
                "provider": "google_places_candidate",
                "place_id": place_id,
                "place_rating": source.get("rating", ""),
                "place_reviews_count": source.get("user_ratings_total", ""),
                "photo_urls": source.get("photo_urls", []),
                "full_address": source.get("address", ""),
            },
        })
        existing_res_ids.add(res_id)

    return filled[:RESTAURANT_LIMIT]


def load_google_place_candidates_from_file():
    if not GOOGLE_PLACE_CANDIDATES_FILE.exists():
        return []

    text = GOOGLE_PLACE_CANDIDATES_FILE.read_text(encoding="utf-8", errors="replace")
    sections = []
    current = None

    for line in text.splitlines():
        if line.startswith("["):
            if current:
                sections.append(current)
            current = {"name": line.split("] ", 1)[-1].strip()}
            continue

        if current is None:
            continue

        if line.startswith("- place_id: "):
            current["place_id"] = line.removeprefix("- place_id: ").strip()
        elif line.startswith("- res_id: "):
            current["res_id"] = line.removeprefix("- res_id: ").strip()
        elif line.startswith("- lat/lng: "):
            lat_lng = line.removeprefix("- lat/lng: ").split(",", 1)
            if len(lat_lng) == 2:
                current["lat"] = _safe_float_text(lat_lng[0])
                current["lng"] = _safe_float_text(lat_lng[1])
        elif line.startswith("- user_ratings_total: "):
            current["user_ratings_total"] = line.removeprefix("- user_ratings_total: ").strip()
        elif line.startswith("- place_url: "):
            current["place_url"] = line.removeprefix("- place_url: ").strip()

    if current:
        sections.append(current)

    restaurants = []
    for item in sections:
        res_id = item.get("res_id") or f"GOOGLE_{item.get('place_id', '')}"
        if not res_id or res_id == "GOOGLE_":
            continue

        restaurants.append({
            "restaurant": {
                "res_id": res_id,
                "res_name": item.get("name", ""),
                "lat": item.get("lat"),
                "lng": item.get("lng"),
                "category": "",
            },
            "menus": [
                {
                    "menu_id": f"{res_id}_MENU",
                    "menu_name": f"{item.get('name', '')} 대표 메뉴",
                    "price": 0,
                    "photo_url": "",
                }
            ],
            "source": {
                "provider": "google_places_candidate",
                "place_id": item.get("place_id", ""),
                "place_url": item.get("place_url", ""),
                "user_ratings_total": item.get("user_ratings_total", ""),
                "photo_urls": [],
            },
        })

    return restaurants


def _safe_float_text(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def main():
    google_restaurants = export_google_place_candidates()
    apify_items = run_apify_reviews_scraper(google_restaurants)
    restaurants = import_apify_reviews_to_db(apify_items or None)

    if restaurants:
        export_ai_crawl_input(restaurants, google_restaurants)


if __name__ == "__main__":
    main()
