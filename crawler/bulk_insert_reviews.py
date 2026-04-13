from database_and_crawler import MenuWiseDB, ReviewCrawler


def build_core_info():
    """AI 연동 전 단계이므로 테스트용 요약 데이터 생성"""
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
        },
        {
            "menu_id": "M002",
            "content": "맛이 무난해서 호불호가 적음",
            "info_type": "PROS",
            "level": 2,
            "upvotes": 2,
            "downvotes": 0
        }
    ]


def main():
    db = MenuWiseDB()
    crawler = ReviewCrawler()

    restaurant_list = crawler.crawl_restaurant_info("강원대")

    for res_data in restaurant_list:
        reviews = crawler.crawl_reviews(res_data["restaurant"]["res_id"])
        res_data["reviews"] = reviews
        res_data["core_info"] = build_core_info()

        db.save_restaurant_data(res_data)

    print("테스트 데이터 삽입 완료")
    print("반경 3km 내 식당:", db.get_nearby_restaurants(37.5665, 126.9780, 3))

    db.close()


if __name__ == "__main__":
    main()