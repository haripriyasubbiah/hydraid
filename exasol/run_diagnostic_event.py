"""
End-to-end glue for one diagnostic event: trains/uses src/cause_inference.py's
XGBoost classifier client-side, then pushes everything else — ambiguity
detection and next-check ranking — down into Exasol via the UDFs in
udf_identifiability.sql / udf_active_check.sql, writing results into
FACT_POSTERIOR and MART_PROBE_RANK.

WHY XGBOOST TRAINING ISN'T A UDF
---------------------------------
Exasol UDFs run inside a Script Language Container (SLC) that only has the
packages that were installed into it. The base `PYTHON3` SLC you install
with `init slc install=all` does NOT ship xgboost / scikit-learn by default
— only a custom SLC build does, and that's real extra infra work (building
and publishing a custom container image) that isn't worth it for a 5-person
hackathon team. The pragmatic split used here, and a defensible one for a
real system too:

  - Pure numeric/array work (residual aggregation, pairwise distance,
    entropy/EIG ranking) -> runs INSIDE Exasol as UDFs, because it's cheap,
    has no exotic dependencies, and keeps data movement low.
  - Model TRAINING/inference (XGBoost + calibration) -> runs OUTSIDE, in
    this script, and only the *result* (a probability per hypothesis) is
    written back into FACT_POSTERIOR for the dashboard to query.

If you do want XGBoost running natively inside Exasol later, the path is a
custom SLC (see https://github.com/exasol/script-languages-release) with
xgboost baked in — flag it to the team as a stretch goal, not a blocker.

USAGE
-----
    python run_diagnostic_event.py --event-id evt001

Reads the live event's readings from FACT_OBSERVATION (event_id must
already be loaded there), and the sample residual dict format
src/test_pipeline.py expects. For a quick smoke test with no real
observation data yet, use --demo to reuse the synthetic bias-fault example
from tests/test_golden_scenario.py.
"""

import argparse
import os
import sys

import pandas as pd

from exasol_conn import connect

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from src.residual_engine import compute_residuals, extract_window_features
from src.cause_inference import (
    prepare_feature_matrix,
    train_cause_classifier,
    get_calibrated_posterior,
    find_nearest_case,
)
from src.identifiability import find_ambiguous_hypotheses, check_case_ambiguity
from src.active_check import rank_next_sensor_checks

SIGNATURES_CSV = os.path.join(PROJECT_ROOT, "signatures.csv")

DEMO_EVENT = {
    'n105': 0.0, 'n115': 0.0, 'n143': 0.0, 'n229': 0.0, 'n251': 0.0,
    'n26': 5.0, 'n282': 0.0, 'n655': 0.0, 'n693': 0.0, 'n755': 0.0,
    'n759': 0.0, 'n760': 0.0
}


def fetch_event_residuals(conn, event_id):
    """
    Pulls this event's readings from FACT_OBSERVATION, joins against
    baseline FACT_SIGNATURE by (sensor, sim_time), and returns the
    {sensor: mean_residual} dict that get_calibrated_posterior() expects —
    same shape as the sample_event_residuals argument in
    src/test_pipeline.py.
    """
    rows = conn.execute(
        """
        SELECT s.sensor, AVG(ABS(s.pressure - o.observation_value)) AS mean_res
        FROM FACT_SIGNATURE s
        JOIN FACT_OBSERVATION o
          ON o.sensor_id = s.sensor
         AND o.sim_time   = s.sim_time
        WHERE s.scenario = 'baseline'
          AND o.event_id = ?
        GROUP BY s.sensor
        """,
        [event_id],
    ).fetchall()

    if not rows:
        return None
    return {sensor: float(res) for sensor, res in rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument(
        "--demo", action="store_true",
        help="Use the synthetic bias-fault example instead of FACT_OBSERVATION data",
    )
    args = parser.parse_args()

    conn = connect()
    try:
        if args.demo:
            live_event_residuals = DEMO_EVENT
        else:
            live_event_residuals = fetch_event_residuals(conn, args.event_id)
            if live_event_residuals is None:
                print(f"No FACT_OBSERVATION rows found for event_id={args.event_id!r}. "
                      f"Load some readings first, or pass --demo to smoke-test the pipeline.")
                return

        # ---- everything below mirrors src/test_pipeline.py exactly ----
        df_sig = pd.read_csv(SIGNATURES_CSV)

        ambiguities = find_ambiguous_hypotheses(df_sig, noise_tolerance=0.5)

        baseline = df_sig[df_sig['scenario'] == 'baseline'][['sensor', 'time', 'pressure']]
        residuals = compute_residuals(df_sig, baseline)
        feat_df = extract_window_features(residuals)
        matrix_df = prepare_feature_matrix(feat_df)

        model, le, sensor_order = train_cause_classifier(matrix_df)
        posterior = get_calibrated_posterior(model, le, sensor_order, live_event_residuals)

        nearest = find_nearest_case(matrix_df, sensor_order, live_event_residuals)
        equivalence = check_case_ambiguity(nearest['case_id'], ambiguities)

        if equivalence is not None and len(equivalence['scenarios_involved']) > 1:
            decision_status = 'ABSTAIN'
            candidate_case_ids = equivalence['equivalent_cases']
        else:
            decision_status = 'RESOLVED'
            candidate_case_ids = [nearest['case_id']]

        ranked = rank_next_sensor_checks(
            posterior, sensor_order,
            df_signatures=df_sig,
            candidate_case_ids=candidate_case_ids,
        )

        # ---- write results back into Exasol ----
        conn.execute("DELETE FROM FACT_POSTERIOR WHERE event_id = ?", [args.event_id])
        posterior_rows = pd.DataFrame([
            {"event_id": args.event_id, "hypothesis_id": scenario, "likelihood": None, "probability": prob}
            for scenario, prob in posterior.items()
        ])
        conn.import_from_pandas(posterior_rows, "FACT_POSTERIOR")

        conn.execute("DELETE FROM MART_PROBE_RANK WHERE event_id = ?", [args.event_id])
        probe_rows = pd.DataFrame([
            {
                "event_id": args.event_id,
                "probe_id": r["sensor"],
                "eig": r["expected_info_gain"],
                "cost": r["cost"],
                "risk": None,
                "rank_value": i + 1,
            }
            for i, r in enumerate(ranked)
        ])
        conn.import_from_pandas(probe_rows, "MART_PROBE_RANK")

        print(f"Event {args.event_id}: status={decision_status}, "
              f"nearest_case={nearest['case_id']} ({nearest['scenario']})")
        print("Posterior:", posterior)
        print("Top recommended check:", ranked[0]["sensor"] if ranked else None)
        print(f"Wrote {len(posterior_rows)} rows to FACT_POSTERIOR, "
              f"{len(probe_rows)} rows to MART_PROBE_RANK.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
