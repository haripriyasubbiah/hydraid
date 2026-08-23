"""Case-level leave-one-out evaluation for the HydraID inference model.

Each event is created from one known scenario signature, then that complete
case is removed before fitting.  This prevents the evaluation from testing a
case that the model has already seen during training.
"""

import os
import sys
import argparse

import pandas as pd


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.residual_engine import compute_residuals, extract_window_features
from src.cause_inference import (
    find_nearest_case,
    get_calibrated_posterior,
    MIN_RESOLVED_CONFIDENCE,
    prepare_feature_matrix,
    train_cause_classifier,
)
from src.identifiability import check_case_ambiguity, find_ambiguous_hypotheses
from src.exasol_data import load_signatures_from_exasol


SIGNATURES_PATH = os.path.join(PROJECT_ROOT, "signatures.csv")
NOISE_TOLERANCE = 0.10


def evaluate_leave_one_case_out(signatures_path=SIGNATURES_PATH, signatures=None, verbose=True):
    """Return one evaluation result for every non-baseline scenario case."""
    signatures = (
        signatures.copy() if signatures is not None else pd.read_csv(signatures_path)
    )
    baseline = signatures[signatures["scenario"] == "baseline"][
        ["sensor", "time", "pressure"]
    ]

    # This uses the same residual construction as the diagnostic pipeline.
    residuals = compute_residuals(signatures, baseline)
    features = extract_window_features(residuals)
    matrix = prepare_feature_matrix(features)
    sensor_order = [
        column for column in matrix.columns if column not in ("scenario", "case_id")
    ]
    ambiguities = find_ambiguous_hypotheses(
        signatures, noise_tolerance=NOISE_TOLERANCE
    )
    cases = matrix[["scenario", "case_id"]].drop_duplicates()
    rows = []

    for position, (_, case) in enumerate(cases.iterrows(), start=1):
        actual_scenario = case["scenario"]
        actual_case_id = case["case_id"]
        held_out = matrix[
            (matrix["scenario"] == actual_scenario)
            & (matrix["case_id"] == actual_case_id)
        ]
        train_matrix = matrix.drop(held_out.index)

        # The held-out row is the event residual vector, aggregated across its
        # 49-step window exactly as a real incoming event would be.
        event_residuals = held_out.iloc[0][sensor_order].to_dict()
        model, label_encoder, trained_sensor_order = train_cause_classifier(
            train_matrix
        )
        posterior = get_calibrated_posterior(
            model, label_encoder, trained_sensor_order, event_residuals
        )
        nearest = find_nearest_case(
            train_matrix, trained_sensor_order, event_residuals
        )
        equivalence = check_case_ambiguity(nearest["case_id"], ambiguities)
        equivalent = (
            equivalence is not None
            and len(equivalence["scenarios_involved"]) > 1
        )
        predicted_scenario = max(posterior, key=posterior.get)
        confidence = posterior[predicted_scenario]
        abstained = equivalent or confidence < MIN_RESOLVED_CONFIDENCE

        rows.append(
            {
                "actual_scenario": actual_scenario,
                "actual_case_id": actual_case_id,
                "predicted_scenario": predicted_scenario,
                "confidence": confidence,
                "decision": "ABSTAIN" if abstained else "RESOLVED",
                "nearest_case": nearest["case_id"],
                "nearest_scenario": nearest["scenario"],
                "nearest_distance": nearest["distance"],
                "correct": predicted_scenario == actual_scenario,
                "abstained": abstained,
            }
        )
        if verbose:
            print(
                f"[{position}/{len(cases)}] {actual_case_id}: "
                f"{predicted_scenario} ({posterior[predicted_scenario]:.1%}), "
                f"{'ABSTAIN' if abstained else 'RESOLVED'}",
                flush=True,
            )

    return pd.DataFrame(rows)


def print_report(results):
    """Print scenario-level performance and the cause-family confusion matrix."""
    report = results.groupby("actual_scenario").agg(
        cases=("actual_case_id", "count"),
        accuracy=("correct", "mean"),
        mean_confidence=("confidence", "mean"),
        abstain_rate=("abstained", "mean"),
    )
    print("\nScenario-level leave-one-case-out results")
    print(report.to_string(float_format=lambda value: f"{value:.1%}"))
    resolved = results[~results["abstained"]]
    if not resolved.empty:
        print(
            "\nAccuracy among automatically resolved cases: "
            f"{resolved['correct'].mean():.1%} ({len(resolved)}/{len(results)} cases resolved)"
        )
    print("\nConfusion matrix (actual rows, predicted columns)")
    print(pd.crosstab(results["actual_scenario"], results["predicted_scenario"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run leave-one-case-out inference evaluation."
    )
    parser.add_argument(
        "--source", choices=("csv", "exasol"), default="csv",
        help="Scenario-signature source (default: csv).",
    )
    arguments = parser.parse_args()
    source_data = (
        load_signatures_from_exasol() if arguments.source == "exasol" else None
    )
    evaluation = evaluate_leave_one_case_out(signatures=source_data)
    print_report(evaluation)
