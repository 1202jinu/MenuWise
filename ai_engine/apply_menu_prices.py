"""처음 정제한 22개 식당 메뉴의 가격 정보를 DB(menus.price)에 반영한다.

메뉴명은 AI가 추출한 이름을 그대로 사용하므로 (식당명, 메뉴명)으로 매칭한다.
가격 정보가 없는 메뉴(예: 닭튀김)는 0으로 두어 프론트에서 '가격 정보 없음'으로 표시된다.
재실행해도 같은 값으로 덮어쓰므로 멱등하게 동작한다.

실행: (프로젝트 루트에서) python ai_engine/apply_menu_prices.py
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawler.database_and_crawler import MenuWiseDB

# 식당명 -> {메뉴명: 가격(원)}
PRICE_DATA = {
    "국수닭": {
        "초계막국수": 10000,
        "얼큰닭국수": 9000,
        "메밀치킨": 9500,
        "초계국수": 9000,
        "삼계탕": 14000,
        "치킨소짜": 4000,
        "닭한마리": 14000,
        "삼계탕메밀국수": 10000,
    },
    "굽네치킨": {
        "오븐치킨": 18900,
    },
    "금계찜닭": {
        "안동찜닭": 31000,
        "신불찜닭": 31000,
        "치즈찜닭": 36000,
        "고추장찜닭": 31000,
        "계란밥": 2000,
        "비빔냉면": 9000,
        "직화불고기": 32000,
        "삼겹찜닭": 32000,
    },
    "남가네 설악추어탕 춘천점": {
        "추어탕": 12000,
        "추어튀김": 15000,
        "된장찌개": 7000,
        "순대국": 10000,
        "얼큰추어탕": 13000,
    },
    "내린천": {
        "쌈밥": 14000,
        "양념삼겹살": 17000,
        "점심 쌈정식": 14000,
    },
    "돈치킨강대점": {
        "매운치킨": 19000,
    },
    "동경": {
        "알탕": 22000,
        "회": 45000,
        "연어구이": 39000,
        "물회": 20000,
        "초밥": 22000,
    },
    "또래오래 석사점": {
        "후라이드": 20000,
        "양념반": 22000,
        "치맥": 27000,
        "갈릭": 22000,
    },
    "롯데리아 강원대학점": {
        "새우버거": 5100,
        "밀리터리버거": 6400,
        "소프트아이스크림": 1400,
    },
    "림스치킨": {
        "후라이드 치킨": 22000,
        "양념 치킨": 23000,
        "닭똥집": 16000,
        "생맥주": 4000,
    },
    "맘스터치 석사점": {
        "싸이버거": 5200,
        "휠렛버거 세트": 7400,
        "생맥주": 5000,
        "감튀": 2000,
    },
    "멕시카나 석사점": {
        "치킨": 20000,
    },
    "명동놀부닭갈비": {
        "닭갈비": 16000,
    },
    "바다양푼이동태탕찜": {
        "동태탕": 8000,
        "동태섞어찌개": 8000,
    },
    "서울녹각삼계탕": {
        "삼계탕": 17000,
        "인삼주": 5000,
    },
    "소담족발": {
        "마늘족발": 32000,
        "막국수": 5000,
        "앞다리살": 30000,
        "곽두리 쪽갈비": 32000,
    },
    "투다리석사점": {
        "김치우동": 11000,
    },
    "페리카나 후평2동점": {
        "양념치킨": 22000,
        "후라이드": 21000,
        "양념통닭": 24000,
    },
    "피자스쿨 석사애막골점": {
        "치즈 크러스트": 3000,
        "콤비네이션 피자": 10900,
        "고구마 피자": 10900,
    },
    "피자스쿨후평점": {
        "고구마피자": 10900,
        "포테이토피자": 11900,
    },
    "황소돌곱창구이": {
        "곱창전골": 35000,
        "볶음밥": 3000,
        "곱창": 26000,
    },
    "흥부곱창": {
        "곱창": 25000,
        "천엽": 13000,
    },
}


def apply_prices():
    db_path = os.getenv("MENUWISE_DB_PATH", str(ROOT_DIR / "menu_wise.db"))
    db = MenuWiseDB(db_path)
    cursor = db.conn.cursor()

    updated = 0
    unmatched = []

    for res_name, menu_prices in PRICE_DATA.items():
        cursor.execute("SELECT res_id FROM restaurants WHERE res_name = ?", (res_name,))
        rows = cursor.fetchall()
        if not rows:
            unmatched.append(f"[식당 없음] {res_name}")
            continue

        res_ids = [row[0] for row in rows]

        for menu_name, price in menu_prices.items():
            cursor.execute(
                "UPDATE menus SET price = ? WHERE menu_name = ? AND res_id IN (%s)"
                % ",".join("?" * len(res_ids)),
                (price, menu_name, *res_ids),
            )
            if cursor.rowcount > 0:
                updated += cursor.rowcount
            else:
                unmatched.append(f"[메뉴 없음] {res_name} > {menu_name}")

    db.conn.commit()
    db.close()

    print(f"가격 반영 완료: {updated}개 메뉴 업데이트 (DB: {db_path})")
    if unmatched:
        print(f"매칭 실패 {len(unmatched)}건:")
        for item in unmatched:
            print(f"  - {item}")


if __name__ == "__main__":
    apply_prices()
