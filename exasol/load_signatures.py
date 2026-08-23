"""
Loads simulation/generate_signatures.py's output (../signatures.csv) into
FACT_SIGNATURE.

Fix vs. the original script: the row-count sanity check was hardcoded to
2940 (leftover from an early smaller test run). The real scenario cube
described in README.md has 35,868 rows. Left as-is, the old check would
raise on every real run and block the whole load.
"""

import os
import pandas as pd

from exasol_conn import connect

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "..", "signatures.csv")

EXPECTED_ROWS = 35868  # baseline(588) + leak(14112) + demand(7056) + bias(7056) + stuck(7056)

REQUIRED_COLUMNS = ["scenario", "case_id", "sensor", "time", "pressure"]


def main():
    df = pd.read_csv(CSV_PATH)
    print(f"CSV rows: {len(df)}")
    print(f"CSV columns: {df.columns.tolist()}")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    if len(df) != EXPECTED_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_ROWS} rows, found {len(df)}. "
            "Did simulation/generate_signatures.py change, or did it fail partway through?"
        )

    df = df.rename(columns={"time": "sim_time"})

    conn = connect()
    try:
        conn.execute("TRUNCATE TABLE FACT_SIGNATURE")

        conn.import_from_pandas(
            df[["scenario", "case_id", "sensor", "sim_time", "pressure"]],
            "FACT_SIGNATURE",
        )

        count = conn.execute("SELECT COUNT(*) FROM FACT_SIGNATURE").fetchone()[0]
        print(f"Loaded {count} rows into FACT_SIGNATURE")

        rows = conn.execute(
            """
            SELECT SCENARIO, COUNT(*)
            FROM FACT_SIGNATURE
            GROUP BY SCENARIO
            ORDER BY SCENARIO
            """
        ).fetchall()
        print("\nScenario counts:")
        for row in rows:
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
