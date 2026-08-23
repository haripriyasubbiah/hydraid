import pandas as pd
import pyexasol

# -----------------------------
# 1. Load CSV
# -----------------------------
csv_path = "../signatures.csv"

df = pd.read_csv(csv_path)

print(f"CSV rows: {len(df)}")
print(f"CSV columns: {df.columns.tolist()}")

# -----------------------------
# 2. Validate input
# -----------------------------
required_columns = [
    "scenario",
    "case_id",
    "sensor",
    "time",
    "pressure",
]

missing = [c for c in required_columns if c not in df.columns]

if missing:
    raise ValueError(f"Missing columns: {missing}")

if len(df) != 35868:
    raise ValueError(f"Expected 35868 rows, found {len(df)}")

# -----------------------------
# 3. Rename time -> sim_time
# -----------------------------
df = df.rename(columns={
    "time": "sim_time"
})

# -----------------------------
# 4. Connect to Exasol
# -----------------------------
conn = pyexasol.connect(
    dsn="localhost:8563",
    user="sys",
    password="exasol",
    schema="HYDRAID",
    websocket_sslopt={"cert_reqs": 0}
)

# -----------------------------
# 5. Clear existing signatures
# -----------------------------
conn.execute("TRUNCATE TABLE FACT_SIGNATURE")

# -----------------------------
# 6. Load data
# -----------------------------
conn.import_from_pandas(
    df[
        [
            "scenario",
            "case_id",
            "sensor",
            "sim_time",
            "pressure",
        ]
    ],
    "FACT_SIGNATURE"
)

# -----------------------------
# 7. Verify
# -----------------------------
count = conn.execute(
    "SELECT COUNT(*) FROM FACT_SIGNATURE"
).fetchone()[0]

print(f"Loaded {count} rows into FACT_SIGNATURE")

# Scenario counts
rows = conn.execute("""
    SELECT SCENARIO, COUNT(*)
    FROM FACT_SIGNATURE
    GROUP BY SCENARIO
    ORDER BY SCENARIO
""").fetchall()

print("\nScenario counts:")
for row in rows:
    print(row)

conn.close()
