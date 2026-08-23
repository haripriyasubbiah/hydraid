"""Executable proof for the Step 4 abstain -> probe workflow.

Run directly with ``venv\\Scripts\\python.exe tests\\test_active_check.py``;
pytest is deliberately not required by this repository.
"""

import os
import sys

import pandas as pd


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.active_check import rank_next_sensor_checks
from src.identifiability import find_ambiguous_hypotheses


def test_active_check_reduces_ambiguity():
    signatures = pd.read_csv(os.path.join(PROJECT_ROOT, "signatures.csv"))
    observed_sensors = ["n105"]
    ambiguities = find_ambiguous_hypotheses(signatures, observed_sensors)
    cross_cause = ambiguities[
        ambiguities["scenario_1"] != ambiguities["scenario_2"]
    ].iloc[0]
    candidate_case_ids = [cross_cause["case_1"], cross_cause["case_2"]]
    posterior = {
        cross_cause["scenario_1"]: 0.5,
        cross_cause["scenario_2"]: 0.5,
    }
    candidate_sensors = sorted(
        set(signatures["sensor"]) - set(observed_sensors)
    )

    recommendations = rank_next_sensor_checks(
        posterior,
        candidate_sensors,
        signatures,
        candidate_case_ids,
        crew_location="n105",
        network_path=os.path.join(PROJECT_ROOT, "data", "l_town.inp"),
    )

    assert recommendations, "An ambiguous diagnosis must produce a probe plan."
    top_check = recommendations[0]
    assert top_check["sensor"] not in observed_sensors
    assert top_check["expected_info_gain"] > 0
    assert top_check["inspection_cost"] > 0
    assert top_check["separates_cases"], "Top check must separate a candidate pair."

    before = len(ambiguities)
    after_ambiguities = find_ambiguous_hypotheses(
        signatures, observed_sensors + [top_check["sensor"]]
    )
    after = len(after_ambiguities)
    assert after < before, "The selected reading must reduce ambiguity."
    original_pair_remains = after_ambiguities[
        ((after_ambiguities["case_1"] == candidate_case_ids[0])
         & (after_ambiguities["case_2"] == candidate_case_ids[1]))
        | ((after_ambiguities["case_1"] == candidate_case_ids[1])
           & (after_ambiguities["case_2"] == candidate_case_ids[0]))
    ]
    assert original_pair_remains.empty, (
        "The selected reading must distinguish the original ambiguous pair."
    )
    print(
        "Step 4 passed: observed n105 -> ABSTAIN -> check "
        f"{top_check['sensor']} (EIG {top_check['expected_info_gain']:.3f}, "
        f"network cost {top_check['inspection_cost']:.1f}); "
        f"ambiguous pairs {before} -> {after}."
    )


if __name__ == "__main__":
    test_active_check_reduces_ambiguity()
