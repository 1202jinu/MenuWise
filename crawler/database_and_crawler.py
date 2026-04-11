import sqlite3

class MenuWiseDB:
    def __init__(self, db_path="menu_wise.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        """테이블 생성: 변경 시 팀장 승인 필수"""
        cursor = self.conn.cursor()
        # 식당(공간검색용), 메뉴, 핵심요약(Level 1,2 통합)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS core_info (
                info_id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_id TEXT,
                content TEXT,
                info_type TEXT, -- 'PROS' / 'CONS'
                level INTEGER,  -- 1: 대표, 2: 상세
                upvotes INTEGER DEFAULT 0,
                downvotes INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    # --- TODO: 이성준 구현 영역 ---
    def insert_crawled_data(self, restaurant_data, menu_list):
        """크롤링 데이터를 DB 규칙에 맞게 입력"""
        pass

    def get_nearby_restaurants(self, lat, lng, radius):
        """반경 내 식당 필터링 로직 구현"""
        pass

    def update_vote(self, info_id, is_upvote):
        """추천/비추천 수치 1 증가 로직"""
        pass