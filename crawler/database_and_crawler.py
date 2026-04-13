import sqlite3
import math

class MenuWiseDB:
    def __init__(self, db_path="menu_wise.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        """테이블 생성: 변경 시 팀장 승인 필수"""
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
            CREATE TABLE IF NOT EXISTS core_info (
                info_id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_id TEXT,
                content TEXT,
                info_type TEXT, -- 'PROS' / 'CONS'
                level INTEGER,  -- 1: 대표, 2: 상세
                upvotes INTEGER DEFAULT 0,
                downvotes INTEGER DEFAULT 0,
                FOREIGN KEY (menu_id) REFERENCES menus(menu_id)
            )
        """)
        self.conn.commit()

    # --- TODO: 이성준 구현 영역 ---
    def insert_crawled_data(self, restaurant_data, menu_list):
        """크롤링 데이터를 DB 규칙에 맞게 입력"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO restaurants (res_id, res_name, lat, lng, category)
            VALUES (?, ?, ?, ?, ?)
        """, (
            restaurant_data["res_id"],
            restaurant_data["res_name"],
            restaurant_data.get("lat"),
            restaurant_data.get("lng"),
            restaurant_data.get("category")
        ))

        for menu in menu_list:
            cursor.execute("""
                INSERT OR REPLACE INTO menus (menu_id, res_id, menu_name, price, photo_url)
                VALUES (?, ?, ?, ?, ?)
            """, (
                menu["menu_id"],
                restaurant_data["res_id"],
                menu["menu_name"],
                menu.get("price"),
                menu.get("photo_url")
            ))

            for info in menu.get("core_info", []):
                cursor.execute("""
                    INSERT INTO core_info (menu_id, content, info_type, level, upvotes, downvotes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    menu["menu_id"],
                    info["content"],
                    info["info_type"],
                    info["level"],
                    info.get("upvotes", 0),
                    info.get("downvotes", 0)
                ))

        self.conn.commit()

    def get_nearby_restaurants(self, lat, lng, radius):
        """반경 내 식당 필터링 로직 구현"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT res_id, res_name, lat, lng, category
            FROM restaurants
            WHERE lat IS NOT NULL AND lng IS NOT NULL
        """)
        rows = cursor.fetchall()

        result = []
        for row in rows:
            res_id, res_name, res_lat, res_lng, category = row
            distance = self._calculate_distance(lat, lng, res_lat, res_lng)

            if distance <= radius:
                result.append({
                    "res_id": res_id,
                    "res_name": res_name,
                    "category": category,
                    "distance_km": round(distance, 2)
                })

        result.sort(key=lambda x: x["distance_km"])
        return result

    def update_vote(self, info_id, is_upvote):
        """추천/비추천 수치 1 증가 로직"""
        cursor = self.conn.cursor()

        if is_upvote:
            cursor.execute("""
                UPDATE core_info
                SET upvotes = upvotes + 1
                WHERE info_id = ?
            """, (info_id,))
        else:
            cursor.execute("""
                UPDATE core_info
                SET downvotes = downvotes + 1
                WHERE info_id = ?
            """, (info_id,))

        self.conn.commit()

    def _calculate_distance(self, lat1, lng1, lat2, lng2):
        r = 6371.0

        lat1_rad = math.radians(lat1)
        lng1_rad = math.radians(lng1)
        lat2_rad = math.radians(lat2)
        lng2_rad = math.radians(lng2)

        dlat = lat2_rad - lat1_rad
        dlng = lng2_rad - lng1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c

    def close(self):
        self.conn.close()
