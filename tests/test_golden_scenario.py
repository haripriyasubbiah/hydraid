# tests/test_golden_scenarios.py
import sys
import os
import pandas as pd

# Add the root directory to the system path so Python can find the 'src' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.test_pipeline import run_diagnostic_pipeline


def residual_vector_for_known_case(signatures_path, scenario, case_id):
    """Create a live-event residual vector from one known signature case."""
    signatures = pd.read_csv(signatures_path)
    baseline = signatures[signatures['scenario'] == 'baseline'][
        ['sensor', 'time', 'pressure']
    ]
    known_case = signatures[
        (signatures['scenario'] == scenario) &
        (signatures['case_id'] == case_id)
    ]
    if known_case.empty:
        raise ValueError(f"No signature exists for {scenario}/{case_id}")

    merged = known_case.merge(
        baseline, on=['sensor', 'time'], suffixes=('_case', '_baseline')
    )
    merged['residual'] = (
        merged['pressure_case'] - merged['pressure_baseline']
    ).abs()
    window_features = merged.groupby('sensor')['residual'].agg(
        mean_res='mean', max_res='max', std_res='std'
    ).fillna(0.0)
    return {
        f"{sensor}__{statistic}": value
        for sensor, values in window_features.iterrows()
        for statistic, value in values.items()
    }


def test_sensor_fault_scenario():
    print("--- RUNNING GOLDEN SCENARIO: SENSOR BIAS ---")

    live_event_data = residual_vector_for_known_case(
        'signatures.csv', scenario='bias', case_id='bias_n105'
    )

    posterior, ambiguities, recommendations, decision = run_diagnostic_pipeline(
        'signatures.csv', live_event_data
    )
    
    # Print Results for the UI/Judges
    print("\n1. Likelihood of Causes:")
    for cause, prob in posterior.items():
        print(f"   {cause}: {prob * 100:.2f}%")

    print(f"\nDecision status: {decision['status']}")  
    assert max(posterior, key=posterior.get) == 'bias'
      
    print(f"\n2. Ambiguous Signatures Detected: {len(ambiguities)}")
    if decision['status'] == 'ABSTAIN':
        print("   SYSTEM ABSTAINING: Causes are too mathematically similar.")
        
    print("\n3. Recommended Next Action:")
    if recommendations:
        top_check = recommendations[0]
        print(f"   Send crew to check Sensor: {top_check['sensor']} "
              f"(EIG: {top_check['expected_info_gain']:.3f}, "
              f"cost: {top_check['inspection_cost']:.1f}, "
              f"score: {top_check['action_score']:.6f})")
    else:
        print("   No extra check needed; the diagnosis is already resolved.")

    print("\n4. Final Decision:")
    print(f"   Status: {decision['status']}")
    if decision['status'] == 'ABSTAIN':
        print(f"   {decision['reason']}")
        print(f"   Equivalent cases: {decision['equivalence_class']['equivalent_cases']}")

   
if __name__ == "__main__":
    test_sensor_fault_scenario()
