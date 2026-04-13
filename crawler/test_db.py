import oracledb

try:
    conn = oracledb.connect(
        user="c##hr",
        password="hr1234",
        dsn="localhost:1521/xe"
    )

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM menus")

    for row in cursor:
        print(row)

    cursor.close()
    conn.close()
    print("DB 연결 성공")

except Exception as e:
    print("오류 발생:", e)