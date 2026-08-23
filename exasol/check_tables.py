import pyexasol

conn = pyexasol.connect(
    dsn="localhost:8563",
    user="sys",
    password="exasol",
    schema="HYDRAID",
    websocket_sslopt={"cert_reqs": 0}
)

rows = conn.execute("""
    SELECT table_name
    FROM exa_all_tables
    WHERE table_schema = 'HYDRAID'
    ORDER BY table_name
""").fetchall()

if rows:
    for row in rows:
        print(row[0])
else:
    print("NO TABLES")

conn.close()