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
    live_event_data = {'n105': 0.5029287003348485, 'n115': 0.2518172123992988, 'n143': 0.7956614047918208,
     'n229': 0.7214567641649133, 'n251': 0.4016085707016349, 'n26': 3.2498233079478474e-06,
     'n282': 0.2510653366759432, 'n655': 0.5064131125748843, 'n693': 0.17446153744746862,
     'n755': 0.3127075211661002, 'n759': 0.32233987903915695, 'n760': 0.32286809671789596}
    
    # Run the engine
    posterior, ambiguities, recommendations,decision = run_diagnostic_pipeline('signatures.csv', live_event_data)
    
    # Print Results for the UI/Judges
    print("\n1. Likelihood of Causes:")
    for cause, prob in posterior.items():
        print(f"   {cause}: {prob * 100:.2f}%")

    print(f"\nDecision status: {decision['status']}")  
      
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