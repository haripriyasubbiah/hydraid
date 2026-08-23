"""Active-check planning for unresolved HydraID diagnoses."""

from collections import defaultdict
from pathlib import Path

import networkx as nx
import numpy as np


def calculate_entropy(probabilities):
    """Return Shannon entropy in bits for a mapping or numeric sequence."""
    values = probabilities.values() if isinstance(probabilities, dict) else probabilities
    probs = np.asarray(list(values), dtype=float)
    probs = probs[probs > 0]
    if len(probs) == 0:
        return 0.0
    probs = probs / probs.sum()
    return float(-np.sum(probs * np.log2(probs)))


def _case_priors(candidate_cases, current_posterior):
    """Distribute scenario posterior mass uniformly across its candidate cases."""
    scenarios = defaultdict(list)
    for case_id, scenario in candidate_cases.items():
        scenarios[scenario].append(case_id)
    priors = {}
    for scenario, case_ids in scenarios.items():
        mass = float(current_posterior.get(scenario, 0.0))
        for case_id in case_ids:
            priors[case_id] = mass / len(case_ids)
    total = sum(priors.values())
    if total == 0:
        return {case_id: 1.0 / len(candidate_cases) for case_id in candidate_cases}
    return {case_id: value / total for case_id, value in priors.items()}


def _outcome_groups(sensor_profiles, noise_tolerance):
    """Cluster traces that a noisy reading cannot distinguish."""
    case_ids = list(sensor_profiles)
    graph = nx.Graph()
    graph.add_nodes_from(case_ids)
    for index, first_case in enumerate(case_ids):
        for second_case in case_ids[index + 1:]:
            rms = float(np.sqrt(np.mean(
                (sensor_profiles[first_case] - sensor_profiles[second_case]) ** 2
            )))
            if rms <= noise_tolerance:
                graph.add_edge(first_case, second_case)
    return [sorted(group) for group in nx.connected_components(graph)]


def _sensor_profiles(df_signatures, candidate_case_ids, sensor):
    data = df_signatures[
        (df_signatures["case_id"].isin(candidate_case_ids))
        & (df_signatures["sensor"] == sensor)
    ]
    profiles = data.pivot_table(index="case_id", columns="time", values="pressure")
    profiles = profiles.reindex(candidate_case_ids)
    if profiles.empty or profiles.isna().any().any():
        return None
    return {case_id: row.to_numpy(dtype=float) for case_id, row in profiles.iterrows()}


def build_network_graph(network_path):
    """Build a pipe-length-weighted NetworkX graph from an EPANET INP file."""
    try:
        import wntr
    except ImportError as exc:
        raise RuntimeError("WNTR is required to calculate network travel costs.") from exc
    network = wntr.network.WaterNetworkModel(str(network_path))
    graph = nx.Graph()
    for link_name in network.link_name_list:
        link = network.get_link(link_name)
        graph.add_edge(
            link.start_node_name,
            link.end_node_name,
            weight=max(float(getattr(link, "length", 1.0)), 1.0),
        )
    return graph


def network_inspection_costs(candidate_sensors, crew_location, network_path):
    """Return shortest-pipe-distance inspection costs from the crew."""
    graph = build_network_graph(network_path)
    distances = nx.single_source_dijkstra_path_length(
        graph, crew_location, weight="weight"
    )
    return {
        sensor: float(distances[sensor]) if sensor in distances else float("inf")
        for sensor in candidate_sensors
    }


def rank_next_sensor_checks(
    current_posterior,
    candidate_sensors,
    df_signatures,
    candidate_case_ids,
    sensor_costs=None,
    crew_location=None,
    network_path=None,
    noise_tolerance=0.10,
):
    """Rank unobserved sensors by expected information gain divided by cost.

    A sensor's possible outcomes are groups of candidate case traces that are
    within the pressure-noise tolerance.  EIG is the prior entropy minus the
    probability-weighted posterior entropy after observing that sensor.
    """
    candidate_case_ids = list(dict.fromkeys(candidate_case_ids or []))
    if len(candidate_case_ids) < 2:
        return []
    case_rows = df_signatures[df_signatures["case_id"].isin(candidate_case_ids)]
    candidate_cases = (
        case_rows[["case_id", "scenario"]].drop_duplicates()
        .set_index("case_id")["scenario"].to_dict()
    )
    if set(candidate_cases) != set(candidate_case_ids):
        raise ValueError("Every candidate case must be present in df_signatures.")
    priors = _case_priors(candidate_cases, current_posterior)
    prior_entropy = calculate_entropy(priors)

    if sensor_costs is None:
        sensor_costs = (
            network_inspection_costs(candidate_sensors, crew_location, Path(network_path))
            if crew_location and network_path
            else {sensor: 1.0 for sensor in candidate_sensors}
        )

    recommendations = []
    for sensor in candidate_sensors:
        profiles = _sensor_profiles(df_signatures, candidate_case_ids, sensor)
        if profiles is None:
            continue
        groups = _outcome_groups(profiles, noise_tolerance)
        expected_entropy = 0.0
        for group in groups:
            outcome_probability = sum(priors[case_id] for case_id in group)
            conditional = {
                case_id: priors[case_id] / outcome_probability for case_id in group
            }
            expected_entropy += outcome_probability * calculate_entropy(conditional)
        separating_pairs = []
        for index, first_case in enumerate(candidate_case_ids):
            for second_case in candidate_case_ids[index + 1:]:
                rms = float(np.sqrt(np.mean(
                    (profiles[first_case] - profiles[second_case]) ** 2
                )))
                if rms > noise_tolerance:
                    separating_pairs.append((first_case, second_case))
        eig = max(0.0, prior_entropy - expected_entropy)
        cost = float(sensor_costs.get(sensor, 1.0))
        score = eig / cost if np.isfinite(cost) and cost > 0 else 0.0
        recommendations.append({
            "sensor": sensor,
            "expected_info_gain": eig,
            "expected_remaining_entropy": expected_entropy,
            "inspection_cost": cost,
            "action_score": score,
            "outcome_groups": groups,
            "separates_cases": separating_pairs,
        })
    return sorted(recommendations, key=lambda item: item["action_score"], reverse=True)
