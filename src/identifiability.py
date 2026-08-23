import pandas as pd 
import numpy as np 
from scipy.spatial.distance import pdist, squareform

def find_ambiguous_hypotheses(
    df_signatures, observed_sensors=None, noise_tolerance=0.10
):
    """Find cases indistinguishable within a sensor-level noise tolerance.

    Each signature retains all sensor × time readings.  Pairwise distance is
    the Euclidean norm of per-sensor temporal RMS errors: temporal dynamics
    distinguish stuck sensors from persistent bias, while the final distance
    remains in pressure units and is comparable to ``noise_tolerance``.
    """
    # Only evidence already available to the operator determines whether a
    # diagnosis is identifiable. Unobserved sensors remain for Step 4 to rank.
    data = df_signatures[df_signatures['scenario'] != 'baseline'].copy()
    if observed_sensors is not None:
        observed_sensors = list(observed_sensors)
        if not observed_sensors:
            raise ValueError("At least one observed sensor is required.")
        data = data[data['sensor'].isin(observed_sensors)]
    sensors = sorted(data['sensor'].unique())
    times = sorted(data['time'].unique())
    if not sensors or not times:
        raise ValueError("No signature readings exist for the observed sensors.")
    signature_columns = pd.MultiIndex.from_product(
        [sensors, times], names=['sensor', 'time']
    )
    profile_df = data.pivot_table(
        index=['scenario', 'case_id'],
        columns=['sensor', 'time'],
        values='pressure'
    ).reindex(columns=signature_columns, fill_value=0.0).fillna(0.0)

    dist_matrix = squareform(pdist(profile_df.values, metric='euclidean'))
    # Normalize the raw sensor×time Euclidean distance by the number of time
    # steps. This is equivalent to computing RMS error over time at each
    # sensor, then combining sensor errors with an L2 norm.
    dist_matrix /= np.sqrt(len(times))
    cases = profile_df.index.tolist()

    ambiguous_groups = []
    for i in range(len(cases)):
        for j in range(i + 1, len(cases)):
            if dist_matrix[i, j] < noise_tolerance:
                scenario_1, case_1 = cases[i]
                scenario_2, case_2 = cases[j]
                ambiguous_groups.append({
                    'case_1': case_1,
                    'case_2': case_2,
                    'scenario_1': scenario_1,
                    'scenario_2': scenario_2,
                    'signature_distance': float(dist_matrix[i, j]),
                    'status': 'ABSTAIN_EQUIVALENT'
                })
    return pd.DataFrame(ambiguous_groups)


def check_case_ambiguity(case_id, ambiguous_df):
    """
    Given a specific case_id (the hypothesis nearest to the live event),
    check if it appears in any ambiguous pair. Returns the equivalence
    group (list of case_ids + scenarios) if so, else None.
    """
    if ambiguous_df.empty:
        return None

    hits = ambiguous_df[
        (ambiguous_df['case_1'] == case_id) | (ambiguous_df['case_2'] == case_id)
    ]
    if hits.empty:
        return None

    group = set()
    scenario_by_case = {}
    for _, row in hits.iterrows():
        group.add(row['case_1']); group.add(row['case_2'])
        scenario_by_case[row['case_1']] = row['scenario_1']
        scenario_by_case[row['case_2']] = row['scenario_2']

    return {
        'equivalent_cases': sorted(group),
        'scenarios_involved': sorted(set(scenario_by_case.values())),
        'scenario_by_case': scenario_by_case
    }
