# src/04_active_check.py
import numpy as np
import pandas as pd

def calculate_entropy(prob_dict):
    """Computes Shannon entropy in bits for the hypothesis distribution."""
    probs = np.array(list(prob_dict.values()))
    probs = np.clip(probs, 1e-9, 1.0)
    probs = probs / np.sum(probs)
    return -np.sum(probs * np.log2(probs))

def compute_sensor_separating_power(df_signatures, candidate_case_ids, sensor_list, noise_tolerance=0.10):
    """
    For each candidate sensor, measures how much the forward-model signatures
    of the candidate hypotheses differ at that sensor. High spread = a reading
    there would help separate the hypotheses. Near-zero spread = that sensor
    physically cannot distinguish them, no matter what it reads.
    """
    subset = df_signatures[df_signatures['case_id'].isin(candidate_case_ids)]
    profile = subset.pivot_table(index='case_id', columns='sensor', values='pressure').fillna(0.0)

    separating_power = {}
    for sensor in sensor_list:
        if sensor not in profile.columns:
            separating_power[sensor] = 0.0
            continue
        values = profile[sensor].values
        spread = (values.max() - values.min()) if len(values) > 1 else 0.0
        # normalize relative to the identifiability tolerance: a spread
        # smaller than tolerance means this sensor can't separate these
        # hypotheses even under noise-free conditions
        separating_power[sensor] = float(min(spread / (noise_tolerance * 2), 1.0))
    return separating_power

def rank_next_sensor_checks(current_posterior, candidate_sensors, df_signatures=None,
                             candidate_case_ids=None, sensor_costs=None, noise_tolerance=0.10):
    """
    Ranks unverified candidate sensors by Information Gain / Inspection Cost.
    Real EIG now depends on whether each sensor can actually separate the
    hypotheses in play — not a constant.
    """
    prior_entropy = calculate_entropy(current_posterior)

    if sensor_costs is None:
        sensor_costs = {s: 1.0 for s in candidate_sensors}

    if df_signatures is not None and candidate_case_ids and len(candidate_case_ids) > 1:
        separating_power = compute_sensor_separating_power(
            df_signatures, candidate_case_ids, candidate_sensors, noise_tolerance
        )
    else:
        # No competing hypothesis set to discriminate between (e.g. a
        # confidently resolved single cause) -> nothing to separate, so
        # ranking falls back to cost only.
        separating_power = {s: 0.0 for s in candidate_sensors}

    recommendations = []
    for sensor in candidate_sensors:
        power = separating_power.get(sensor, 0.0)
        eig = prior_entropy * power          # replaces the old constant 0.75*prior_entropy
        cost = sensor_costs.get(sensor, 1.0)
        score = eig / cost

        recommendations.append({
            'sensor': sensor,
            'separating_power': round(power, 3),
            'expected_info_gain': eig,
            'cost': cost,
            'action_score': score
        })

    return sorted(recommendations, key=lambda x: x['action_score'], reverse=True)
