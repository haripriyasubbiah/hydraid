import pyexasol

c = pyexasol.connect(
    dsn='localhost:8563',
    user='sys',
    password='exasol',
    schema='HYDRAID',
    websocket_sslopt={'cert_reqs': 0}
)

rows = c.execute(
    "SELECT SIM_TIME, PRESSURE FROM FACT_SIGNATURE "
    "WHERE SCENARIO='baseline' AND SENSOR='n143' ORDER BY SIM_TIME"
).fetchall()

for r in rows:
    print(r)

c.close()