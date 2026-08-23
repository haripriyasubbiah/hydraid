"""
Populates the three dimension tables that schema.sql declares but that
nothing in the original repo actually loaded: DIM_NETWORK, DIM_SENSOR,
DIM_HYPOTHESIS.

Run this once, before or after load_signatures.py (order doesn't matter,
neither table depends on the other being populated first):

    cd exasol
    python load_dimensions.py

Sources:
  - DIM_NETWORK   <- data/l_town.inp (via wntr), tagged against the frozen
                     scope in data/scope_selection.py
  - DIM_SENSOR    <- data/scope_selection.py SENSORS list
  - DIM_HYPOTHESIS <- distinct (scenario, case_id) pairs in signatures.csv
"""

import os
import sys

import pandas as pd
import wntr

from exasol_conn import connect

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from data.scope_selection import SENSORS, LEAK_ZONES  # noqa: E402

NETWORK_FILE = os.path.join(PROJECT_ROOT, "data", "l_town.inp")
SIGNATURES_CSV = os.path.join(PROJECT_ROOT, "signatures.csv")
NETWORK_ID = "l_town"


def build_dim_network():
    wn = wntr.network.WaterNetworkModel(NETWORK_FILE)
    rows = []

    for pipe_name in wn.pipe_name_list:
        rows.append({
            "network_id": NETWORK_ID,
            "element_type": "pipe",
            "element_id": pipe_name,
            "zone_id": pipe_name if pipe_name in LEAK_ZONES else None,
        })

    for junction_name in wn.junction_name_list:
        rows.append({
            "network_id": NETWORK_ID,
            "element_type": "junction",
            "element_id": junction_name,
            "zone_id": junction_name if junction_name in SENSORS else None,
        })

    for reservoir_name in wn.reservoir_name_list:
        rows.append({
            "network_id": NETWORK_ID,
            "element_type": "reservoir",
            "element_id": reservoir_name,
            "zone_id": None,
        })

    df = pd.DataFrame(rows)
    print(f"DIM_NETWORK: {len(df)} elements "
          f"({len(wn.pipe_name_list)} pipes, {len(wn.junction_name_list)} junctions, "
          f"{len(wn.reservoir_name_list)} reservoirs)")
    return df


def build_dim_sensor():
    df = pd.DataFrame([
        {"sensor_id": s, "node_id": s, "sensor_type": "pressure"}
        for s in SENSORS
    ])
    print(f"DIM_SENSOR: {len(df)} sensors")
    return df


def build_dim_hypothesis():
    sig = pd.read_csv(SIGNATURES_CSV)
    cases = sig.drop_duplicates(subset=["scenario", "case_id"])[["scenario", "case_id"]]
    df = pd.DataFrame({
        "hypothesis_id": cases["case_id"],
        "scenario": cases["scenario"],
        "case_id": cases["case_id"],
    })
    print(f"DIM_HYPOTHESIS: {len(df)} hypotheses across {df['scenario'].nunique()} scenarios")
    return df


def main():
    dim_network = build_dim_network()
    dim_sensor = build_dim_sensor()
    dim_hypothesis = build_dim_hypothesis()

    conn = connect()
    try:
        for table, df in [
            ("DIM_NETWORK", dim_network),
            ("DIM_SENSOR", dim_sensor),
            ("DIM_HYPOTHESIS", dim_hypothesis),
        ]:
            conn.execute(f"TRUNCATE TABLE {table}")
            conn.import_from_pandas(df, table)
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"Loaded {count} rows into {table}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
