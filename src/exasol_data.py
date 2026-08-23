"""Read HydraID scenario signatures from Exasol."""

import os

import pandas as pd
import pyexasol


def load_signatures_from_exasol():
    """Return ``FACT_SIGNATURE`` in the pipeline's canonical column format.

    Connection settings can be overridden with ``HYDRAID_EXASOL_*`` environment
    variables; the defaults match the local Docker Compose deployment.
    """
    connection = pyexasol.connect(
        dsn=os.getenv("HYDRAID_EXASOL_DSN", "localhost:8563"),
        user=os.getenv("HYDRAID_EXASOL_USER", "sys"),
        password=os.getenv("HYDRAID_EXASOL_PASSWORD", "exasol"),
        schema=os.getenv("HYDRAID_EXASOL_SCHEMA", "HYDRAID"),
        websocket_sslopt={"cert_reqs": 0},
    )
    try:
        signatures = connection.export_to_pandas("""
            SELECT
                SCENARIO AS "scenario",
                CASE_ID AS "case_id",
                SENSOR AS "sensor",
                SIM_TIME AS "time",
                PRESSURE AS "pressure"
            FROM FACT_SIGNATURE
            ORDER BY SCENARIO, CASE_ID, SENSOR, SIM_TIME
        """)
    finally:
        connection.close()

    required_columns = {"scenario", "case_id", "sensor", "time", "pressure"}
    missing_columns = required_columns.difference(signatures.columns)
    if missing_columns:
        raise ValueError(f"FACT_SIGNATURE is missing columns: {sorted(missing_columns)}")
    if signatures.empty:
        raise ValueError("FACT_SIGNATURE is empty; load the scenario cube first.")

    signatures["time"] = pd.to_numeric(signatures["time"])
    signatures["pressure"] = pd.to_numeric(signatures["pressure"])
    return signatures
