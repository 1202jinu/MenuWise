import oracledb

reviews_data = [
    (2, 1, "된장찌개가 구수하고 가격도 괜찮아요."),
    (3, 1, "김치찌개가 얼큰해서 좋았는데 조금 짰어요."),
    (4, 1, "된장찌개 양이 많고 맛도 무난했어요."),
]

feedback_data = [
    (2, 2, 5, 1),
    (3, 3, 7, 2),
    (4, 4, 3, 0),
]

try:
    conn = oracledb.connect(
        user="c##hr",
        password="hr1234",
        dsn="localhost:1521/xe"
    )

    cursor = conn.cursor()

    # 리뷰 여러 개 저장
    for review in reviews_data:
        cursor.execute("""
            INSERT INTO reviews (id, restaurant_id, content)
            VALUES (:1, :2, :3)
        """, review)

    # 피드백 여러 개 저장
    for feedback in feedback_data:
        cursor.execute("""
            INSERT INTO review_feedback (id, review_id, likes, dislikes)
            VALUES (:1, :2, :3, :4)
        """, feedback)

    conn.commit()

    print("리뷰 및 피드백 여러 개 저장 완료")

    cursor.close()
    conn.close()

except Exception as e:
    print("오류 발생:", e)