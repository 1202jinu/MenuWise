import sqlite3
import math


class MenuWiseDB:
    def __init__(self, db_path="menu_wise.db"):
        """데이터베이스 초기화 및 테이블 생성을 위해 만든 생성자입니다."""
        self.conn = sqlite3.connect(db_path)
        self.init_tables()

    def init_tables(self):
        """식당, 메뉴, 리뷰, 그리고 계층적 요약(CoreInfo) 테이블을 생성합니다."""
        cursor = self.conn.cursor()

        # 식당 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS restaurants (
                res_id TEXT PRIMARY KEY,
                res_name TEXT NOT NULL,
                lat REAL,
                lng REAL,
                category TEXT
            )
        """)

        # 메뉴 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS menus (
                menu_id TEXT PRIMARY KEY,
                res_id TEXT NOT NULL,
                menu_name TEXT NOT NULL,
                price INTEGER,
                photo_url TEXT,
                FOREIGN KEY (res_id) REFERENCES restaurants(res_id)
            )
        """)

        # 리뷰 원문 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY,
                res_id TEXT NOT NULL,
                menu_id TEXT,
                content TEXT NOT NULL,
                photo_url TEXT,
                FOREIGN KEY (res_id) REFERENCES restaurants(res_id),
                FOREIGN KEY (menu_id) REFERENCES menus(menu_id)
            )
        """)

        # 핵심 요약 정보 테이블
        # level: 1(대표 요약), 2(상세 정보)
        # info_type: PROS(장점), CONS(단점)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS core_info (
                info_id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_id TEXT NOT NULL,
                content TEXT NOT NULL,
                info_type TEXT NOT NULL,
                level INTEGER NOT NULL,
                upvotes INTEGER DEFAULT 0,
                downvotes INTEGER DEFAULT 0,
                FOREIGN KEY (menu_id) REFERENCES menus(menu_id)
            )
        """)

        self.conn.commit()

    def save_restaurant_data(self, res_data):
        """크롤링한 식당 기본 정보와 위치(위도/경도)를 저장합니다."""
        cursor = self.conn.cursor()

        restaurant = res_data["restaurant"]
        menus = res_data.get("menus", [])
        reviews = res_data.get("reviews", [])
        core_infos = res_data.get("core_info", [])

        cursor.execute("""
            INSERT OR REPLACE INTO restaurants (res_id, res_name, lat, lng, category)
            VALUES (?, ?, ?, ?, ?)
        """, (
            restaurant["res_id"],
            restaurant["res_name"],
            restaurant.get("lat"),
            restaurant.get("lng"),
            restaurant.get("category")
        ))

        for menu in menus:
            cursor.execute("""
                INSERT OR REPLACE INTO menus (menu_id, res_id, menu_name, price, photo_url)
                VALUES (?, ?, ?, ?, ?)
            """, (
                menu["menu_id"],
                restaurant["res_id"],
                menu["menu_name"],
                menu.get("price"),
                menu.get("photo_url")
            ))

        for review in reviews:
            cursor.execute("""
                INSERT OR REPLACE INTO reviews (review_id, res_id, menu_id, content, photo_url)
                VALUES (?, ?, ?, ?, ?)
            """, (
                review["review_id"],
                restaurant["res_id"],
                review.get("menu_id"),
                review["content"],
                review.get("photo_url")
            ))

        for info in core_infos:
            cursor.execute("""
                INSERT INTO core_info (menu_id, content, info_type, level, upvotes, downvotes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                info["menu_id"],
                info["content"],
                info["info_type"],
                info["level"],
                info.get("upvotes", 0),
                info.get("downvotes", 0)
            ))

        self.conn.commit()

    def get_nearby_restaurants(self, lat, lng, radius_km):
        """사용자의 위치와 설정된 반경을 바탕으로 식당을 검색합니다."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT res_id, res_name, lat, lng, category FROM restaurants")
        rows = cursor.fetchall()

        nearby = []
        for row in rows:
            res_id, res_name, res_lat, res_lng, category = row
            dist = self._calculate_distance(lat, lng, res_lat, res_lng)
            if dist <= radius_km:
                nearby.append({
                    "res_id": res_id,
                    "res_name": res_name,
                    "category": category,
                    "distance_km": round(dist, 2)
                })

        nearby.sort(key=lambda x: x["distance_km"])
        return nearby

    def update_feedback(self, info_id, is_upvote):
        """사용자가 누른 추천/비추천 수치를 DB 컬럼에 실시간 반영합니다."""
        cursor = self.conn.cursor()
        column = "upvotes" if is_upvote else "downvotes"
        cursor.execute(
            f"UPDATE core_info SET {column} = {column} + 1 WHERE info_id = ?",
            (info_id,)
        )
        self.conn.commit()

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Haversine 공식을 이용한 거리 계산"""
        if None in (lat1, lon1, lat2, lon2):
            return float("inf")

        r = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c

    def close(self):
        self.conn.close()


class ReviewCrawler:
    def crawl_restaurant_info(self, keyword):
        """지도 플랫폼에서 식당, 메뉴명, 가격, 사진 URL을 수집합니다.
        현재는 실제 크롤링 전 단계이므로 mock 데이터 반환
        """
        return [
            {
                "restaurant": {
                    "res_id": "R001",
                    "res_name": f"{keyword} 맛집 1호점",
                    "lat": 37.5665,
                    "lng": 126.9780,
                    "category": "한식"
                },
                "menus": [
                    {
                        "menu_id": "M001",
                        "menu_name": "김치찌개",
                        "price": 9000,
                        "photo_url": "https://example.com/kimchi.jpg"
                    },
                    {
                        "menu_id": "M002",
                        "menu_name": "된장찌개",
                        "price": 8500,
                        "photo_url": "https://example.com/doenjang.jpg"
                    }
                ]
            }
        ]

    def crawl_reviews(self, res_id):
        """특정 식당의 리뷰 원문 데이터 전체를 수집하여 저장합니다.
        현재는 실제 크롤링 전 단계이므로 mock 데이터 반환
        """
        if res_id == "R001":
            return [
                {
                    "review_id": "RV001",
                    "menu_id": "M001",
                    "content": "김치찌개가 얼큰하고 맛있었지만 조금 짰어요.",
                    "photo_url": "https://example.com/review1.jpg"
                },
                {
                    "review_id": "RV002",
                    "menu_id": "M002",
                    "content": "된장찌개가 구수하고 가격도 괜찮아요.",
                    "photo_url": "https://example.com/review2.jpg"
                },
                {
                    "review_id": "RV003",
                    "menu_id": "M001",
                    "content": "김치찌개가 얼큰해서 좋았는데 조금 짰어요.",
                    "photo_url": None
                },
                {
                    "review_id": "RV004",
                    "menu_id": "M002",
                    "content": "된장찌개 양이 많고 맛도 무난했어요.",
                    "photo_url": None
                }
            ]
        return []

def get_review_count(self, res_id):
    cursor = self.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE res_id = ?", (res_id,))
    return cursor.fetchone()[0]
