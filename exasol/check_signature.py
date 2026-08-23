import pyexasol

conn = pyexasol.connect(
    dsn="localhost:8563",
    user="sys",
    password="exasol",
    schema="HYDRAID",
    websocket_sslopt={"cert_reqs": 0}
)

stmt = conn.execute("SELECT * FROM FACT_SIGNATURE LIMIT 0")

print("FACT_SIGNATURE columns:")
for column in stmt.columns():
    print(column)

conn.close()