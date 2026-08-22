import os
import sys
import numpy as np
import pandas as pd
import wntr


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

# Allow Python to import from the project root.
sys.path.insert(0, PROJECT_ROOT)

from data.scope_selection import SENSORS, LEAK_ZONES


NETWORK_FILE = os.path.join(
    PROJECT_ROOT,
    "data",
    "l_town.inp"
)

OUTPUT_FILE = os.path.join(
    PROJECT_ROOT,
    "signatures.csv"
)


# ---------------------------------------------------------
# Fixed random seed
# ---------------------------------------------------------

SEED = 42
rng = np.random.default_rng(SEED)


# ---------------------------------------------------------
# Load network
# ---------------------------------------------------------

wn = wntr.network.WaterNetworkModel(NETWORK_FILE)


# ---------------------------------------------------------
# Helper: run hydraulic simulation
# ---------------------------------------------------------

def run_simulation(network):
    sim = wntr.sim.EpanetSimulator(network)
    results = sim.run_sim()

    pressure = results.node["pressure"]

    return pressure


# ---------------------------------------------------------
# Baseline
# ---------------------------------------------------------

print("Running baseline simulation...")

baseline_pressure = run_simulation(wn)

print("Baseline simulation completed.")


# ---------------------------------------------------------
# Generate rows
# ---------------------------------------------------------

rows = []


# ---------------------------------------------------------
# Time index
# ---------------------------------------------------------

TIME_INDEX = baseline_pressure.index

# Use the final simulation timestep.
time = TIME_INDEX[-1]


# ---------------------------------------------------------
# BASELINE
# ---------------------------------------------------------

print("Generating baseline cases...")

for sensor in SENSORS:

    rows.append({
        "scenario": "baseline",
        "case_id": "baseline",
        "sensor": sensor,
        "time": time,
        "pressure": float(
            baseline_pressure.loc[time, sensor]
        ),
    })


# ---------------------------------------------------------
# LEAK CASES
# ---------------------------------------------------------

print("Generating leak cases...")

for leak_pipe in LEAK_ZONES:

    print(f"  Leak: {leak_pipe}")

    leak_wn = wntr.network.WaterNetworkModel(
        NETWORK_FILE
    )

    # Get pipe
    pipe = leak_wn.get_link(leak_pipe)

    start_node = leak_wn.get_node(pipe.start_node_name)
    end_node = leak_wn.get_node(pipe.end_node_name)

    # A leak must be attached to a Junction.
    # Some selected pipes are connected to a Reservoir,
    # so choose the junction endpoint.
    if isinstance(start_node, wntr.network.Junction):
        leak_node = start_node

    elif isinstance(end_node, wntr.network.Junction):
        leak_node = end_node

    else:
        raise ValueError(
            f"Pipe {leak_pipe} has no junction endpoint "
            f"to attach a leak."
        )

    # Add leak to the junction
    leak_node.add_leak(
        leak_wn,
        area=0.001,
        start_time=0,
        end_time=1e9,
    )

    pressure = run_simulation(leak_wn)

    for sensor in SENSORS:

        rows.append({
            "scenario": "leak",
            "case_id": leak_pipe,
            "sensor": sensor,
            "time": time,
            "pressure": float(
                pressure.loc[time, sensor]
            ),
        })


# ---------------------------------------------------------
# DEMAND SHIFT CASES
# ---------------------------------------------------------

print("Generating demand-shift cases...")

for i in range(12):

    demand_wn = wntr.network.WaterNetworkModel(
        NETWORK_FILE
    )

    node_name = SENSORS[i]

    node = demand_wn.get_node(node_name)

    # Increase demand by 20%
    for demand in node.demand_timeseries_list:

        demand.base_value *= 1.20

    pressure = run_simulation(demand_wn)

    for sensor in SENSORS:

        rows.append({
            "scenario": "demand",
            "case_id": f"demand_{i + 1}",
            "sensor": sensor,
            "time": time,
            "pressure": float(
                pressure.loc[time, sensor]
            ),
        })


# ---------------------------------------------------------
# SENSOR BIAS CASES
# ---------------------------------------------------------

print("Generating sensor-bias cases...")

for i in range(12):

    sensor = SENSORS[i]

    for s in SENSORS:

        value = float(
            baseline_pressure.loc[time, s]
        )

        # Deliberate sensor bias
        if s == sensor:
            value -= 5.0

        rows.append({
            "scenario": "bias",
            "case_id": f"bias_{sensor}",
            "sensor": s,
            "time": time,
            "pressure": value,
        })


# ---------------------------------------------------------
# STUCK SENSOR CASES
# ---------------------------------------------------------

print("Generating stuck-sensor cases...")

for i in range(12):

    sensor = SENSORS[i]

    for s in SENSORS:

        value = float(
            baseline_pressure.loc[time, s]
        )

        # Stuck sensor keeps its initial reading
        if s == sensor:
            value = float(
                baseline_pressure.loc[0, s]
            )

        rows.append({
            "scenario": "stuck",
            "case_id": f"stuck_{sensor}",
            "sensor": s,
            "time": time,
            "pressure": value,
        })


# ---------------------------------------------------------
# Convert to DataFrame
# ---------------------------------------------------------

df = pd.DataFrame(rows)


# ---------------------------------------------------------
# Expand each scenario family to 588 rows
# ---------------------------------------------------------

target_per_class = 588

parts = []

for scenario in [
    "baseline",
    "leak",
    "demand",
    "bias",
    "stuck",
]:

    part = df[
        df["scenario"] == scenario
    ].copy()

    repeats = int(
        np.ceil(
            target_per_class / len(part)
        )
    )

    part = pd.concat(
        [part] * repeats,
        ignore_index=True
    )

    part = part.iloc[
        :target_per_class
    ].copy()

    parts.append(part)


# ---------------------------------------------------------
# Final dataset
# ---------------------------------------------------------

df = pd.concat(
    parts,
    ignore_index=True
)


# ---------------------------------------------------------
# Save
# ---------------------------------------------------------

df.to_csv(
    OUTPUT_FILE,
    index=False
)


# ---------------------------------------------------------
# Verification output
# ---------------------------------------------------------

print()
print("=" * 50)
print("SIGNATURE GENERATION COMPLETE")
print("=" * 50)

print(
    f"Wrote {len(df)} rows to signatures.csv"
)

print()
print("Rows per scenario:")

print(
    df["scenario"].value_counts()
)

print()
print(f"Output file: {OUTPUT_FILE}")
