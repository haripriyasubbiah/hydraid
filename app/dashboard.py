"""HydraID Operator Dashboard — Step 5.

Run from the project root:
    streamlit run app/dashboard.py

Workflow shown on screen (matches the project blueprint):
    Anomaly -> Ambiguous causes -> Recommended check -> Resolved cause
"""

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.test_pipeline import run_diagnostic_pipeline  # noqa: E402
from src.exasol_data import load_signatures_from_exasol  # noqa: E402

st.set_page_config(page_title="HydraID Operator Dashboard", layout="wide")

SCENARIO_LABELS = {
    "leak": "Leak",
    "demand": "Demand shift",
    "bias": "Sensor bias",
    "stuck": "Stuck sensor",
}
SCENARIO_COLORS = {
    "leak": "#EF553B",
    "demand": "#636EFA",
    "bias": "#00CC96",
    "stuck": "#AB63FA",
}


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Loading scenario cube...")
def load_signatures(source: str) -> pd.DataFrame:
    if source == "Exasol (live)":
        return load_signatures_from_exasol()
    csv_path = os.path.join(PROJECT_ROOT, "signatures.csv")
    return pd.read_csv(csv_path)


def residual_vector_for_case(signatures: pd.DataFrame, scenario: str, case_id: str,
                             observed_sensors: list) -> dict:
    baseline = signatures[signatures["scenario"] == "baseline"][["sensor", "time", "pressure"]]
    case = signatures[(signatures["scenario"] == scenario) & (signatures["case_id"] == case_id)]
    case = case[case["sensor"].isin(observed_sensors)]
    merged = case.merge(baseline, on=["sensor", "time"], suffixes=("_case", "_baseline"))
    merged["residual"] = (merged["pressure_case"] - merged["pressure_baseline"]).abs()
    
    # Calculate the mean residual per sensor
    window = merged.groupby("sensor")["residual"].mean().fillna(0.0)
    
    # Return flat dictionary: {'n105': 5.0, 'n115': 0.1, ...}
    return window.to_dict()


def pressure_trace_figure(signatures: pd.DataFrame, scenario: str, case_id: str, sensor: str) -> go.Figure:
    baseline = signatures[(signatures["scenario"] == "baseline") & (signatures["sensor"] == sensor)]
    live = signatures[
        (signatures["scenario"] == scenario) & (signatures["case_id"] == case_id) & (signatures["sensor"] == sensor)
    ]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=baseline["time"], y=baseline["pressure"], name="Expected (baseline)",
                              line=dict(color="#888888", dash="dash")))
    fig.add_trace(go.Scatter(x=live["time"], y=live["pressure"], name="Live reading",
                              line=dict(color="#EF553B")))
    fig.update_layout(title=f"Pressure at {sensor}", xaxis_title="Time (s)", yaxis_title="Pressure (m)",
                       height=320, margin=dict(t=40, b=10, l=10, r=10))
    return fig


def posterior_figure(posterior: dict) -> go.Figure:
    causes = list(posterior.keys())
    probs = [posterior[c] * 100 for c in causes]
    colors = [SCENARIO_COLORS.get(c, "#CCCCCC") for c in causes]
    fig = go.Figure(go.Bar(x=[SCENARIO_LABELS.get(c, c) for c in causes], y=probs, marker_color=colors,
                            text=[f"{p:.1f}%" for p in probs], textposition="outside"))
    fig.update_layout(title="Likelihood of each cause", yaxis_title="Probability (%)", yaxis_range=[0, 100],
                       height=350, margin=dict(t=40, b=10, l=10, r=10))
    return fig


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
st.sidebar.title("💧 HydraID")
st.sidebar.caption("Identifiability-aware diagnosis for water networks")
data_source = st.sidebar.radio("Data source", ["CSV (local)", "Exasol (live)"], index=0)

try:
    signatures = load_signatures(data_source)
except Exception as exc:  # noqa: BLE001
    st.sidebar.error(f"Could not load signatures: {exc}")
    st.stop()

all_sensors = sorted(signatures["sensor"].unique())
non_baseline = signatures[signatures["scenario"] != "baseline"][["scenario", "case_id"]].drop_duplicates()
case_options = sorted(
    non_baseline.apply(lambda r: f"{r['scenario']} / {r['case_id']}", axis=1).tolist()
)

st.sidebar.markdown("---")
st.sidebar.subheader("Simulate an incoming alarm")
chosen_case = st.sidebar.selectbox("Ground-truth event (hidden from operator view)", case_options)
true_scenario, true_case_id = [s.strip() for s in chosen_case.split("/")]

alarm_sensor = st.sidebar.selectbox("Sensor that raised the alarm", all_sensors)

if "observed_sensors" not in st.session_state or st.session_state.get("_case") != chosen_case:
    st.session_state.observed_sensors = [alarm_sensor]
    st.session_state._case = chosen_case
elif alarm_sensor not in st.session_state.observed_sensors:
    st.session_state.observed_sensors = [alarm_sensor]

if st.sidebar.button("🔄 Reset investigation", use_container_width=True):
    st.session_state.observed_sensors = [alarm_sensor]

st.sidebar.markdown(f"**Sensors checked so far:** {', '.join(st.session_state.observed_sensors)}")

# --------------------------------------------------------------------------- #
# Main panel
# --------------------------------------------------------------------------- #
st.title("HydraID — Operator Dashboard")
st.caption("Anomaly → Ambiguous causes → Recommended check → Resolved cause")

event_residuals = residual_vector_for_case(
    signatures, true_scenario, true_case_id, st.session_state.observed_sensors
)

with st.spinner("Running diagnostic pipeline..."):
    posterior, ambiguities, recommendations, decision = run_diagnostic_pipeline(
        signatures_path=None,
        sample_event_residuals=event_residuals,
        signatures_df=signatures,
        observed_sensors=st.session_state.observed_sensors,
        crew_location=alarm_sensor,
        network_path=os.path.join(PROJECT_ROOT, "data", "l_town.inp"),
    )

col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("1. Anomaly")
    st.plotly_chart(pressure_trace_figure(signatures, true_scenario, true_case_id, alarm_sensor),
                     use_container_width=True)

    st.subheader("2. Likelihood of causes")
    st.plotly_chart(posterior_figure(posterior), use_container_width=True)

with col2:
    st.subheader("3. Decision")
    if decision["status"] == "RESOLVED":
        st.success(f"**RESOLVED** — most likely cause: **{SCENARIO_LABELS.get(decision['top_cause'], decision['top_cause'])}** "
                   f"({decision['confidence']:.1%} confidence)")
    else:
        st.warning("**ABSTAINING** — the system will not guess.")
        st.write(decision["reason"])
        if "equivalence_class" in decision:
            eq = decision["equivalence_class"]
            st.write(f"Tied causes: {', '.join(SCENARIO_LABELS.get(s, s) for s in eq['scenarios_involved'])}")
            st.write(f"Equivalent hypotheses: `{', '.join(eq['equivalent_cases'])}`")

    st.subheader("4. Recommended next check")
    if recommendations:
        rec_df = pd.DataFrame(recommendations)[
            ["sensor", "expected_info_gain", "inspection_cost", "action_score"]
        ].rename(columns={
            "sensor": "Sensor", "expected_info_gain": "Info gain (bits)",
            "inspection_cost": "Travel cost", "action_score": "Score (gain/cost)",
        })
        st.dataframe(rec_df.head(5), use_container_width=True, hide_index=True)

        top_sensor = recommendations[0]["sensor"]
        if st.button(f"➕ Send crew to check {top_sensor}", use_container_width=True):
            st.session_state.observed_sensors.append(top_sensor)
            st.rerun()
    else:
        st.info("No further check needed — diagnosis is already resolved or fully ambiguous with all sensors read.")

st.markdown("---")
with st.expander("Ambiguous hypothesis pairs at current tolerance"):
    st.dataframe(ambiguities, use_container_width=True, hide_index=True)

with st.expander("Raw event residual vector sent to the model"):
    st.json(event_residuals)
