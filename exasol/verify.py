"""
Sanity-checks the whole Exasol setup after running schema.sql,
load_dimensions.py, and load_signatures.py.

    python verify.py
"""

from exasol_conn import connect

EXPECTED = {
    "FACT_SIGNATURE": 35868,
    "DIM_SENSOR": 12,
    "DIM_HYPOTHESIS": 61,   # 1 baseline + 24 leak + 12 demand + 12 bias + 12 stuck
    "DIM_NETWORK": 1690,    # 905 pipes + 782 junctions + 3 reservoirs
}


def main():
    conn = connect()
    try:
        print("Tables in HYDRAID:")
        tables = conn.execute(
            "SELECT TABLE_NAME FROM EXA_ALL_TABLES WHERE TABLE_SCHEMA = 'HYDRAID' ORDER BY 1"
        ).fetchall()
        for (t,) in tables:
            print(f"  - {t}")

        print("\nRow counts:")
        all_ok = True
        for table, expected in EXPECTED.items():
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            status = "OK" if count == expected else "MISMATCH"
            if count != expected:
                all_ok = False
            print(f"  {table}: {count} (expected {expected}) [{status}]")

        print("\nFACT_SIGNATURE scenario breakdown:")
        rows = conn.execute(
            "SELECT SCENARIO, COUNT(*) FROM FACT_SIGNATURE GROUP BY SCENARIO ORDER BY 1"
        ).fetchall()
        for scenario, count in rows:
            print(f"  {scenario}: {count}")

        print("\nSample timeseries (baseline, sensor n143):")
        rows = conn.execute(
            "SELECT SIM_TIME, PRESSURE FROM FACT_SIGNATURE "
            "WHERE SCENARIO = 'baseline' AND SENSOR = 'n143' ORDER BY SIM_TIME"
        ).fetchall()
        print(f"  {len(rows)} timesteps, first 3: {rows[:3]}")

        print(f"\n{'All checks passed.' if all_ok else 'Some row counts do not match — see MISMATCH above.'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
