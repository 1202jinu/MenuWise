import sqlite3
import math
import re


class MenuWiseDB:
    def __init__(self, db_path="menu_wise.db"):
        """데이터베이스 초기화 및 테이블 생성을 위해 만든 생성자입니다."""
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.init_tables()

    def init_tables(self):
        """식당, 메뉴, 리뷰, 그리고 계층적 요약(CoreInfo) 테이블을 생성합니다."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS restaurants (
                res_id TEXT PRIMARY KEY,
                res_name TEXT NOT NULL,
                lat REAL,
                lng REAL,
                category TEXT
            )
        """)

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
    def clean_review_text(self, text):
        """리뷰 원문에서 불필요한 공백과 특수문자를 정리합니다."""
        if text is None:
            return ""

        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^가-힣a-zA-Z0-9\s.,!?]", "", text)

        return text
    
    def transform_ai_core_info(self, menu_id, ai_result):
        """AI 요약 JSON을 core_info 테이블 저장 형식으로 변환합니다."""
        transformed = []

        level_1 = ai_result.get("level_1", {})
        pros = level_1.get("pros")
        cons = level_1.get("cons")

        if pros:
            transformed.append({
                "menu_id": menu_id,
                "content": pros,
                "info_type": "PROS",
                "level": 1,
                "upvotes": 0,
                "downvotes": 0
            })

        if cons:
            transformed.append({
                "menu_id": menu_id,
                "content": cons,
                "info_type": "CONS",
                "level": 1,
                "upvotes": 0,
                "downvotes": 0
            })

        for item in ai_result.get("level_2", []):
            transformed.append({
                "menu_id": menu_id,
                "content": item.get("content", ""),
                "info_type": item.get("info_type", item.get("type", "PROS")),
                "level": 2,
                "upvotes": item.get("upvotes", 0),
                "downvotes": item.get("downvotes", 0)
            })

        return transformed

    def save_restaurant_data(self, res_data):
        """크롤링한 식당, 메뉴, 리뷰, 핵심 요약 정보를 저장합니다."""
        cursor = self.conn.cursor()

        restaurant = res_data["restaurant"]
        menus = res_data.get("menus", [])
        reviews = res_data.get("reviews", [])
        core_infos = res_data.get("core_info", [])
        if isinstance(core_infos, dict):
            converted_core_infos = []

            for menu_id, ai_result in core_infos.items():
                converted_core_infos.extend(
                    self.transform_ai_core_info(menu_id, ai_result)
                )

            core_infos = converted_core_infos
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
            cleaned_content = self.clean_review_text(review.get("content"))

            if len(cleaned_content) < 5:
                continue

            cursor.execute("""
                INSERT OR REPLACE INTO reviews (
                    review_id,
                    res_id,
                    menu_id,
                    content,
                    photo_url
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                review["review_id"],
                restaurant["res_id"],
                review.get("menu_id"),
                cleaned_content,
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
    
    def search_menus(self, keyword, lat, lng, radius_km):
        """백엔드 검색 API용 함수: 키워드와 위치 기준으로 식당을 검색합니다."""
        cursor = self.conn.cursor()

        search_keyword = f"%{keyword}%"

        cursor.execute("""
            SELECT res_id, res_name, lat, lng, category
            FROM restaurants
            WHERE res_name LIKE ? OR category LIKE ?
        """, (search_keyword, search_keyword))

        rows = cursor.fetchall()

        result = []
        for row in rows:
            res_id, res_name, res_lat, res_lng, category = row
            dist = self._calculate_distance(lat, lng, res_lat, res_lng)

            if dist <= radius_km:
                result.append({
                    "res_id": res_id,
                    "res_name": res_name,
                    "category": category,
                    "distance_km": round(dist, 2)
                })

        result.sort(key=lambda x: x["distance_km"])
        return result

    def vote(self, info_id, is_upvote):
        """백엔드 피드백 API용 함수명."""
        self.update_feedback(info_id, is_upvote)
        
    def get_menu_details(self, menu_id):
        """메뉴 상세 정보와 핵심 요약 정보를 조회합니다."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                menus.menu_id,
                menus.menu_name,
                menus.price,
                menus.photo_url,
                restaurants.res_id,
                restaurants.res_name,
                restaurants.category
            FROM menus
            JOIN restaurants ON menus.res_id = restaurants.res_id
            WHERE menus.menu_id = ?
        """, (menu_id,))

        menu_row = cursor.fetchone()

        if menu_row is None:
            return None

        cursor.execute("""
            SELECT info_id, content, info_type, level, upvotes, downvotes
            FROM core_info
            WHERE menu_id = ?
            ORDER BY level ASC, info_id ASC
        """, (menu_id,))

        core_rows = cursor.fetchall()

        core_info = []
        for row in core_rows:
            core_info.append({
                "info_id": row[0],
                "content": row[1],
                "info_type": row[2],
                "level": row[3],
                "upvotes": row[4],
                "downvotes": row[5]
            })

        return {
            "menu_id": menu_row[0],
            "menu_name": menu_row[1],
            "price": menu_row[2],
            "photo_url": menu_row[3],
            "restaurant": {
                "res_id": menu_row[4],
                "res_name": menu_row[5],
                "category": menu_row[6]
            },
            "core_info": core_info
        }
    
    def get_restaurants_by_category(self, category):
        """카테고리 기준으로 식당을 조회합니다."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT res_id, res_name, lat, lng, category
            FROM restaurants
            WHERE category = ?
        """, (category,))

        rows = cursor.fetchall()

        restaurants = []
        for row in rows:
            res_id, res_name, lat, lng, category = row
            restaurants.append({
                "res_id": res_id,
                "res_name": res_name,
                "lat": lat,
                "lng": lng,
                "category": category
            })

        return restaurants
    
    def get_top_restaurants_by_upvotes(self):
        """추천 수 기준 인기 식당 조회"""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                restaurants.res_id,
                restaurants.res_name,
                restaurants.category,
                SUM(core_info.upvotes) as total_upvotes
            FROM restaurants
            JOIN menus ON restaurants.res_id = menus.res_id
            JOIN core_info ON menus.menu_id = core_info.menu_id
            GROUP BY restaurants.res_id
            ORDER BY total_upvotes DESC
        """)

        rows = cursor.fetchall()

        result = []

        for row in rows:
            result.append({
                "res_id": row[0],
                "res_name": row[1],
                "category": row[2],
                "total_upvotes": row[3]
            })

        return result

    def get_review_count(self, res_id):
        """특정 식당의 리뷰 개수를 조회합니다."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reviews WHERE res_id = ?", (res_id,))
        return cursor.fetchone()[0]
    def get_menu_review_count(self, menu_id):
        """특정 메뉴의 리뷰 개수를 조회합니다."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reviews WHERE menu_id = ?", (menu_id,))
        return cursor.fetchone()[0]

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
