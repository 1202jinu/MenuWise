"""추가된 27개 식당 메뉴의 가격을 DB에 반영하고, 가격 없는 일부 메뉴를 삭제한다.

- 가격은 (식당명, 메뉴명)으로 매칭해 menus.price를 갱신한다.
- 삭제는 (식당명, 메뉴명) 정확 일치로만 해당 메뉴 1개를 지운다(식당은 유지).
  연결된 core_info는 삭제하고, 리뷰는 menu_id를 NULL로 풀어 raw 데이터는 보존한다.
- 같은 메뉴명이 여러 식당에 있어도 식당 단위로만 처리되어 안전하다.

실행: (프로젝트 루트에서) python ai_engine/apply_extra_prices.py
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawler.database_and_crawler import MenuWiseDB

# 식당명 -> {메뉴명: 가격(원)}  (가격을 적지 않은 메뉴는 아래 DELETE_MENUS로 삭제)
PRICE_DATA = {
    "감미옥 춘천": {
        "수육": 28000, "돌솥설렁탕": 13000, "옛날설렁탕": 11000,
        "갈비탕": 17000, "갈비찜": 54000, "꼬리곰탕": 19000,
    },
    "진미닭갈비": {
        "닭갈비": 16000, "닭내장": 16000, "볶음밥": 3000, "옥수수동동주": 6000,
    },
    "청송막국수": {
        "막국수": 9000, "떡만두국": 10000, "녹두전": 9000, "감자전": 9000, "만둣국": 9000,
    },
    "중화요리 죽향": {
        "짬뽕": 7500, "탕수육": 21000, "자장면": 6000, "쟁반짜장": 17000, "삼선짬뽕": 8000,
    },
    "중화루": {
        "짬뽕": 10000, "탕수육": 23000, "짜장면": 7000, "볶음밥": 10000,
        "유산슬": 32000, "칠리새우": 31000, "고추잡채": 28000, "철판짜장": 10000,
    },
    "차이나게이트": {
        "탕수육": 15000, "사천탕면": 10000, "짜장면": 8000, "마파두부밥": 11000,
        "누룽지탕": 36000, "짬뽕": 10000, "간짜장": 8500,
    },
    "진짬뽕진짜장": {
        "간짜장": 8000, "짬뽕": 8500, "탕수육": 23000, "쟁반짜장": 8000, "해물짬뽕": 8500,
        "고기짬뽕": 10000, "게살볶음밥": 10000, "부대전골짬뽕": 11000, "새우볶음밥": 10000,
    },
    "석사왕막걸리": {
        "비지찌개": 3000, "비빔국수": 9000, "갈매기살": 17000,
        "통갈매기살": 17000, "돼지뒷고기": 18000, "청국장": 3000,
    },
    "애막골회집": {
        "송어회": 34000, "향어회": 30000, "매운탕": 45000,
    },
    "브릭스피자 (Brick's Pizza Club)": {
        "페타바이트 피자": 24000, "스파게티": 6500, "감자튀김": 6000,
        "맥앤치즈": 7000, "페퍼로니 피자": 24000,
    },
    "러스틱컴포트": {
        "야채치킨": 23000, "코젤다크": 7000, "치킨": 21000, "웨지감자": 7000,
    },
    "산애그린": {
        "삼겹살": 16000, "냄비라면": 4000, "김치찌개": 7000,
        "곰탕": 8000, "육회": 16000, "돼지껍데기": 10000,
    },
    "멘시루": {
        "돈코츠라멘": 8500, "탄탄멘": 8500,
    },
    "우성닭갈비 석사동애막골점": {
        "닭갈비": 16000,
    },
    "돈까스타운(신촌돈까스)": {
        "돈까스": 5000,
    },
    "삼겹천하": {
        "김치삼겹살": 16000, "치즈볶음밥": 4000, "미나리 삼겹살": 19000,
    },
    "곱돌생삼겹살": {
        "삼겹살": 11000,
    },
    "윤일닭갈비": {
        "닭갈비": 15000, "냉이 닭갈비": 15000, "볶음밥": 3000,
    },
    "순이네": {
        "닭볶음탕": 33000, "육회": 35000, "찜닭": 37000, "순살닭볶음탕": 35000,
    },
    "너와집": {
        "감자전": 13000, "막걸리": 5000, "해물파전": 21000, "벌렁주": 9000,
    },
    "신남큰집궁중삼계탕": {
        "삼계탕": 18000, "누룽지삼계탕": 19000,
    },
    "가마솥순대국": {
        "순대국밥": 10000, "순대": 15000, "곱창전골": 35000, "술국": 20000,
    },
    "대주객": {
        "짬뽕": 9000, "백짬뽕탕": 18000, "차돌짬뽕": 13000,
        "짜장면": 7000, "깐풍기": 20000, "탕수육": 17000,
    },
    "만석식당": {
        "냉면": 8000, "불고기쌈밥": 10000,
    },
    "엄마의손길": {
        "김치볶음밥": 9000, "제육덮밥": 9500, "참치김밥": 4500,
    },
    "특미원": {
        "마라탕": 13000, "꿔바로우": 11000,
    },
    "임가네": {
        "안심": 43000, "소고기말이": 29000, "등심": 43000, "볶음밥": 7000,
    },
}

# 식당명 -> [삭제할 메뉴명]  (가격 미기재 메뉴; 식당이 아니라 메뉴만 삭제)
DELETE_MENUS = {
    "진미닭갈비": ["동치미"],
    "청송막국수": ["손만두"],
    "애막골회집": ["송어튀김", "콩가루 야채"],
    "러스틱컴포트": ["피자", "코젤생맥주"],
    "산애그린": ["숭늉", "주먹밥", "야채소시지볶음", "순대"],
    "멘시루": ["라멘", "매운등갈비찜", "교자"],
    "곱돌생삼겹살": ["제육", "갈비탕", "양념계장"],
    "대주객": ["유린기"],
    "만석식당": ["쌈밥", "불고기"],
    "임가네": ["고기", "치즈"],
}


def _res_ids(cursor, res_name):
    cursor.execute("SELECT res_id FROM restaurants WHERE res_name = ?", (res_name,))
    return [row[0] for row in cursor.fetchall()]


def apply_prices(cursor):
    updated = 0
    unmatched = []
    for res_name, menu_prices in PRICE_DATA.items():
        res_ids = _res_ids(cursor, res_name)
        if not res_ids:
            unmatched.append(f"[식당 없음] {res_name}")
            continue
        placeholders = ",".join("?" * len(res_ids))
        for menu_name, price in menu_prices.items():
            cursor.execute(
                f"UPDATE menus SET price = ? WHERE menu_name = ? AND res_id IN ({placeholders})",
                (price, menu_name, *res_ids),
            )
            if cursor.rowcount > 0:
                updated += cursor.rowcount
            else:
                unmatched.append(f"[메뉴 없음] {res_name} > {menu_name}")
    return updated, unmatched


def delete_menus(cursor):
    deleted = 0
    missing = []
    for res_name, menu_names in DELETE_MENUS.items():
        res_ids = _res_ids(cursor, res_name)
        if not res_ids:
            missing.append(f"[식당 없음] {res_name}")
            continue
        placeholders = ",".join("?" * len(res_ids))
        for menu_name in menu_names:
            cursor.execute(
                f"SELECT menu_id FROM menus WHERE menu_name = ? AND res_id IN ({placeholders})",
                (menu_name, *res_ids),
            )
            menu_ids = [row[0] for row in cursor.fetchall()]
            if not menu_ids:
                missing.append(f"[메뉴 없음] {res_name} > {menu_name}")
                continue
            for menu_id in menu_ids:
                cursor.execute("DELETE FROM core_info WHERE menu_id = ?", (menu_id,))
                cursor.execute("UPDATE reviews SET menu_id = NULL WHERE menu_id = ?", (menu_id,))
                cursor.execute("DELETE FROM menus WHERE menu_id = ?", (menu_id,))
                deleted += 1
    return deleted, missing


def main():
    db_path = os.getenv("MENUWISE_DB_PATH", str(ROOT_DIR / "menu_wise.db"))
    db = MenuWiseDB(db_path)
    cursor = db.conn.cursor()

    updated, price_unmatched = apply_prices(cursor)
    deleted, delete_missing = delete_menus(cursor)
    db.conn.commit()
    db.close()

    print(f"가격 반영: {updated}개 메뉴 갱신 (DB: {db_path})")
    print(f"메뉴 삭제: {deleted}개 삭제")
    for item in price_unmatched:
        print(f"  가격 미매칭 - {item}")
    for item in delete_missing:
        print(f"  삭제 미매칭 - {item}")


if __name__ == "__main__":
    main()
