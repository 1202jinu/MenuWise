from database_and_crawler import MenuWiseDB, ReviewCrawler


def build_core_info():
    return [
        {
            "menu_id": "M001",
            "content": "얼큰하고 자극적인 맛이 강함",
            "info_type": "PROS",
            "level": 1,
            "upvotes": 3,
            "downvotes": 0
        },
        {
            "menu_id": "M001",
            "content": "조금 짠 편이라는 의견이 있음",
            "info_type": "CONS",
            "level": 2,
            "upvotes": 1,
            "downvotes": 2
        },
        {
            "menu_id": "M002",
            "content": "구수하고 가격이 괜찮음",
            "info_type": "PROS",
            "level": 1,
            "upvotes": 4,
            "downvotes": 0
        }
    ]


def main():
    db = MenuWiseDB()
    crawler = ReviewCrawler()

    restaurant_list = crawler.crawl_restaurant_info("강원대")

    for res_data in restaurant_list:
        reviews = crawler.crawl_reviews_with_retry(res_data["restaurant"]["res_id"])
        res_data["reviews"] = reviews
        res_data["core_info"] = build_core_info()

        db.save_restaurant_data(res_data)

    print("테스트 데이터 삽입 완료")
    print("반경 3km 내 식당:", db.get_nearby_restaurants(37.5665, 126.9780, 3))
    print("리뷰 개수:", db.get_review_count("R001"))
    print("김치찌개 리뷰 개수:", db.get_menu_review_count("M001"))
    print("된장찌개 리뷰 개수:", db.get_menu_review_count("M002"))
    print("리뷰 전처리 기능 적용 완료")
    print("한식 식당 조회:", db.get_restaurants_by_category("한식"))
    print("추천 수 기준 인기 식당:", db.get_top_restaurants_by_upvotes())
    print("키워드 기반 메뉴 검색:", db.search_menus("한식", 37.5665, 126.9780, 3))
    details = db.get_menu_details("M001")
    print("메뉴 상세 조회:", details["menu_name"], "/", details["restaurant"]["res_name"])
    print("핵심 요약 개수:", len(details["core_info"]))

    db.close()


if __name__ == "__main__":
    main()