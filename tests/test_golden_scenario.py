# tests/test_golden_scenarios.py
import sys
import os

# Add the root directory to the system path so Python can find the 'src' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.test_pipeline import run_diagnostic_pipeline

def test_sensor_fault_scenario():
    print("--- RUNNING GOLDEN SCENARIO: SENSOR BIAS ---")
    
    # Mocking a live event where sensor 'n105' is reporting a massive weird drop (residual = 5.0)
    # but all other sensors look totally normal (residual = 0.1)
    live_event_data = {
    'n105': 0.0, 'n115': 0.0, 'n143': 0.0, 'n229': 0.0, 'n251': 0.0,
    'n26': 5.0, 'n282': 0.0, 'n655': 0.0, 'n693': 0.0, 'n755': 0.0,
    'n759': 0.0, 'n760': 0.0
    }
    
    # Run the engine
    posterior, ambiguities, recommendations,decision = run_diagnostic_pipeline('signatures.csv', live_event_data)
    
    # Print Results for the UI/Judges
    print("\n1. Likelihood of Causes:")
    for cause, prob in posterior.items():
        print(f"   {cause}: {prob * 100:.2f}%")
        
    print(f"\n2. Ambiguous Signatures Detected: {len(ambiguities)}")
    if not ambiguities.empty:
        print("   SYSTEM ABSTAINING: Causes are too mathematically similar.")
        
    print("\n3. Recommended Next Action:")
    top_check = recommendations[0]
    print(f"   Send crew to check Sensor: {top_check['sensor']} "
          f"(Score: {top_check['action_score']:.3f}, "
          f"Separating power: {top_check['separating_power']})")

    print("\n4. Final Decision:")
    print(f"   Status: {decision['status']}")
    if decision['status'] == 'ABSTAIN':
        print(f"   {decision['reason']}")
        print(f"   Equivalent cases: {decision['equivalence_class']['equivalent_cases']}")

   
if __name__ == "__main__":
    test_sensor_fault_scenario()