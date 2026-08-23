import os
import sys
import numpy as np
import pandas as pd
import wntr
import networkx as nx


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

sys.path.insert(0, PROJECT_ROOT)

from data.scope_selection import SENSORS, LEAK_ZONES


NETWORK_FILE = os.path.join(PROJECT_ROOT, "data", "l_town.inp")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "signatures.csv")

SEED = 42
rng = np.random.default_rng(SEED)


# ---------------------------------------------------------
# The source .inp has ZERO demand patterns -- every junction's
# demand is constant, so pressure never naturally changes hour
# to hour. We add a standard diurnal curve so "time" actually
# means something (needed for stuck-sensor / demand-shift cases
# to be distinguishable at all).
# ---------------------------------------------------------

DIURNAL_PATTERN = [0.5, 0.4, 0.4, 0.4, 0.5, 0.7, 1.1, 1.4, 1.3, 1.1, 1.0, 1.0,
                    1.0, 1.0, 1.0, 1.0, 1.1, 1.3, 1.4, 1.2, 1.0, 0.8, 0.6, 0.5]

# A demand anomaly must affect a local consumption area, not merely the
# junction where a pressure sensor is installed.  Each case below expands
# outward from one sensor until it includes this fraction of total network
# base demand, then increases the whole area's demand.
DEMAND_ZONE_FRACTION = 0.05
# This is a 200% increase over normal use in the affected zone.  It was
# calibrated to produce a >= 0.10 m pressure response at the monitored
# sensors; a 20% increase was below the resolution of this network model.
DEMAND_SHIFT_MULTIPLIER = 3.00

# Pressure is measured in metres.  Cases below this impact are smaller than
# a practical pressure-sensor noise floor and must not enter training data.
MIN_DEMAND_PRESSURE_DELTA_M = 0.10


def load_network():
    """Always load a FRESH network with the diurnal pattern applied."""
    network = wntr.network.WaterNetworkModel(NETWORK_FILE)
    network.add_pattern("diurnal", DIURNAL_PATTERN)
    for junction_name in network.junction_name_list:
        junction = network.get_node(junction_name)
        for demand in junction.demand_timeseries_list:
            demand.pattern_name = "diurnal"
    network.options.time.pattern_timestep = 3600
    return network


def run_simulation(network):
    sim = wntr.sim.EpanetSimulator(network)
    results = sim.run_sim()
    return results.node["pressure"]


def _junction_base_demand(network, junction_name):
    """Return a junction's total base demand in WNTR's internal m^3/s."""
    junction = network.get_node(junction_name)
    return sum(demand.base_value for demand in junction.demand_timeseries_list)


def build_local_demand_zone(network, anchor_sensor, demand_fraction):
    """Build a hydraulically local demand zone around ``anchor_sensor``.

    Junctions are selected in shortest-pipe-distance order until their base
    demand reaches ``demand_fraction`` of total network demand.  This gives a
    traceable, non-trivial demand event while retaining a local physical cause.
    """
    graph = nx.Graph()
    for link_name in network.link_name_list:
        link = network.get_link(link_name)
        graph.add_edge(
            link.start_node_name,
            link.end_node_name,
            weight=max(float(getattr(link, "length", 1.0)), 1.0),
        )

    distances = nx.single_source_dijkstra_path_length(
        graph, anchor_sensor, weight="weight"
    )
    junctions = [
        name for name in network.junction_name_list if name in distances
    ]
    demands = {
        name: _junction_base_demand(network, name)
        for name in junctions
    }
    total_demand = sum(
        _junction_base_demand(network, name)
        for name in network.junction_name_list
    )
    target_demand = total_demand * demand_fraction

    zone, zone_demand = [], 0.0
    for junction_name in sorted(junctions, key=distances.__getitem__):
        zone.append(junction_name)
        zone_demand += demands[junction_name]
        if zone_demand >= target_demand:
            break

    if zone_demand < target_demand:
        raise RuntimeError(
            f"Could not form a demand zone around {anchor_sensor}: "
            f"found {zone_demand / total_demand:.2%} of network demand, "
            f"need {demand_fraction:.2%}."
        )
    return zone, zone_demand, total_demand


# ---------------------------------------------------------
# Baseline
# ---------------------------------------------------------

print("Running baseline simulation...")
wn = load_network()
baseline_pressure = run_simulation(wn)
print("Baseline simulation completed.")

TIME_INDEX = baseline_pressure.index   # ALL 49 timesteps -- used everywhere below

rows = []


# ---------------------------------------------------------
# BASELINE -- loop over every timestep, not just the last
# ---------------------------------------------------------

print("Generating baseline cases...")

for t in TIME_INDEX:
    for sensor in SENSORS:
        rows.append({
            "scenario": "baseline",
            "case_id": "baseline",
            "sensor": sensor,
            "time": int(t),
            "pressure": float(baseline_pressure.loc[t, sensor]),
        })


# ---------------------------------------------------------
# LEAK CASES
# ---------------------------------------------------------

print("Generating leak cases...")

for leak_pipe in LEAK_ZONES:
    print(f"  Leak: {leak_pipe}")

    leak_wn = load_network()
    pipe = leak_wn.get_link(leak_pipe)
    start_node = leak_wn.get_node(pipe.start_node_name)
    end_node = leak_wn.get_node(pipe.end_node_name)

    if isinstance(start_node, wntr.network.Junction):
        leak_node = start_node
    elif isinstance(end_node, wntr.network.Junction):
        leak_node = end_node
    else:
        raise ValueError(f"Pipe {leak_pipe} has no junction endpoint to attach a leak.")

    leak_node.add_leak(leak_wn, area=0.001, start_time=0, end_time=1e9)
    # IMPORTANT: EpanetSimulator silently ignores add_leak() -- it's a
    # WNTR-only feature. Leaks require WNTRSimulator specifically, or
    # the leak physically doesn't exist in the simulation.
    sim = wntr.sim.WNTRSimulator(leak_wn)
    pressure = sim.run_sim().node["pressure"]

    for t in TIME_INDEX:
        for sensor in SENSORS:
            rows.append({
                "scenario": "leak",
                "case_id": leak_pipe,
                "sensor": sensor,
                "time": int(t),
                "pressure": float(pressure.loc[t, sensor]),
            })


# ---------------------------------------------------------
# DEMAND SHIFT CASES
# ---------------------------------------------------------

print("Generating demand-shift cases...")

for sensor in SENSORS:
    demand_wn = load_network()
    zone, zone_demand, total_demand = build_local_demand_zone(
        demand_wn, sensor, DEMAND_ZONE_FRACTION
    )

    for node_name in zone:
        node = demand_wn.get_node(node_name)
        for demand in node.demand_timeseries_list:
            demand.base_value *= DEMAND_SHIFT_MULTIPLIER

    pressure = run_simulation(demand_wn)
    max_pressure_delta = float(
        (pressure.loc[TIME_INDEX, SENSORS] - baseline_pressure.loc[TIME_INDEX, SENSORS])
        .abs()
        .to_numpy()
        .max()
    )
    case_id = f"demand_{sensor}"
    print(
        f"  Demand zone {sensor}: {len(zone)} junctions, "
        f"{zone_demand / total_demand:.1%} of total demand, "
        f"max pressure change {max_pressure_delta:.3f} m"
    )
    if max_pressure_delta < MIN_DEMAND_PRESSURE_DELTA_M:
        raise ValueError(
            f"Demand case {case_id} is not detectable: maximum pressure "
            f"change is {max_pressure_delta:.4f} m; minimum is "
            f"{MIN_DEMAND_PRESSURE_DELTA_M:.2f} m. Increase the zone size "
            f"or demand multiplier before training."
        )

    for t in TIME_INDEX:
        for sensor in SENSORS:
            rows.append({
                "scenario": "demand",
                "case_id": case_id,
                "sensor": sensor,
                "time": int(t),
                "pressure": float(pressure.loc[t, sensor]),
            })


# ---------------------------------------------------------
# SENSOR BIAS CASES -- bias applies at every timestep, to just
# the one faulty sensor; every other sensor stays at baseline.
# ---------------------------------------------------------

print("Generating sensor-bias cases...")

for i in range(12):
    sensor = SENSORS[i]
    for t in TIME_INDEX:
        for s in SENSORS:
            value = float(baseline_pressure.loc[t, s])
            if s == sensor:
                value -= 5.0
            rows.append({
                "scenario": "bias",
                "case_id": f"bias_{sensor}",
                "sensor": s,
                "time": int(t),
                "pressure": value,
            })


# ---------------------------------------------------------
# STUCK SENSOR CASES -- faulty sensor freezes at its reading
# from the FIRST timestep; every other sensor moves normally.
# ---------------------------------------------------------

print("Generating stuck-sensor cases...")

first_t = TIME_INDEX[0]

for i in range(12):
    sensor = SENSORS[i]
    for t in TIME_INDEX:
        for s in SENSORS:
            if s == sensor:
                value = float(baseline_pressure.loc[first_t, s])  # frozen
            else:
                value = float(baseline_pressure.loc[t, s])
            rows.append({
                "scenario": "stuck",
                "case_id": f"stuck_{sensor}",
                "sensor": s,
                "time": int(t),
                "pressure": value,
            })


# ---------------------------------------------------------
# Final dataset -- NO artificial padding/duplication needed:
# real timesteps naturally give the right row counts.
# ---------------------------------------------------------

df = pd.DataFrame(rows)
df.to_csv(OUTPUT_FILE, index=False)

print()
print("=" * 50)
print("SIGNATURE GENERATION COMPLETE")
print("=" * 50)
print(f"Wrote {len(df)} rows to signatures.csv")
print()
print("Rows per scenario:")
print(df["scenario"].value_counts())
print()
print(f"Output file: {OUTPUT_FILE}")
