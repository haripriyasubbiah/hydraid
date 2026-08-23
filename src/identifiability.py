import pandas as pd 
import numpy as np 
from scipy.spatial.distance import pdist, squareform

def find_ambiguous_hypotheses(df_signatures, noise_tolerance=0.35):
    profile_df = df_signatures.pivot_table(
        index='case_id', columns='sensor', values='pressure'
    ).fillna(0.0)

    # NEW: map case_id -> scenario, so we know which family each case belongs to
    case_scenario_map = df_signatures.drop_duplicates('case_id').set_index('case_id')['scenario'].to_dict()

    dist_matrix = squareform(pdist(profile_df.values, metric='euclidean'))
    cases = profile_df.index.tolist()

    ambiguous_groups = []
    for i in range(len(cases)):
        for j in range(i + 1, len(cases)):
            if dist_matrix[i, j] < noise_tolerance:
                ambiguous_groups.append({
                    'case_1': cases[i],
                    'case_2': cases[j],
                    'scenario_1': case_scenario_map.get(cases[i]),
                    'scenario_2': case_scenario_map.get(cases[j]),
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