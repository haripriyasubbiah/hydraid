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

st.set_page_config(
    page_title="HydraID | Water Operations",
    page_icon="H",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCENARIO_LABELS = {
    "leak": "Leak",
    "demand": "Demand shift",
    "bias": "Sensor bias",
    "stuck": "Stuck sensor",
}
SCENARIO_COLORS = {
    "leak": "#C9533C",
    "demand": "#287AAB",
    "bias": "#17826D",
    "stuck": "#875AA3",
}


def apply_theme() -> None:
    """Apply the dashboard's editorial operational-system styling."""
    st.markdown(
        """
        <style>
        :root {
            --ink: #18211e;
            --muted: #6c746f;
            --line: #d8ddd7;
            --paper: #f7f7f3;
            --panel: #ffffff;
            --accent: #17826d;
            --sidebar: #14201c;
        }
        .stApp { background: var(--paper); color: var(--ink); }
        .block-container { max-width: 1440px; padding: 2rem 3rem 3.5rem; }
        h1, h2, h3, [data-testid="stMetricValue"] {
            font-family: Georgia, 'Times New Roman', serif !important;
            color: var(--ink) !important;
            font-weight: 500 !important;
            letter-spacing: 0 !important;
        }
        h1 { font-size: 2.65rem !important; line-height: 1.04 !important; }
        h2 { font-size: 1.4rem !important; margin: 1.25rem 0 0.55rem !important; }
        h3 { font-size: 1.05rem !important; margin: 1.15rem 0 0.55rem !important; }
        p, label, [data-testid="stCaptionContainer"] {
            font-family: Inter, ui-sans-serif, system-ui, sans-serif !important;
            letter-spacing: 0 !important;
        }
        [data-testid="stSidebar"] { background: var(--sidebar); }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
            color: #eff4f0 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] > div {
            background: #f8faf8 !important; border-color: #f8faf8 !important;
            border-radius: 6px !important; min-height: 2.55rem;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-baseweb="input"] input {
            color: #1b2823 !important;
            font-weight: 500 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] svg { fill: #51615a !important; }
        [data-testid="stSidebar"] hr { border-color: #405049; }
        [data-testid="stSidebar"] .stButton > button {
            background: #1e3930; border-color: #2b4b40; color: #ffffff;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background: #295044; border-color: #527268; color: #ffffff;
        }
        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 1rem 1.1rem;
        }
        [data-testid="stMetricLabel"] { color: var(--muted) !important; }
        [data-testid="stMetricValue"] { font-size: 1.55rem !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--line) !important;
            border-radius: 6px !important;
            background: var(--panel);
        }
        .brand-kicker, .section-kicker {
            color: var(--accent);
            font: 600 0.72rem Inter, ui-sans-serif, system-ui, sans-serif;
            letter-spacing: 0.08rem;
            text-transform: uppercase;
        }
        .section-kicker {
            display: block;
            margin: 1.45rem 0 0.85rem;
        }
        .brand-mark {
            display: inline-flex; align-items: center; justify-content: center;
            width: 2rem; height: 2rem; margin-bottom: 0.9rem;
            border: 1px solid #6b8278; color: #d5ebe1;
            font: 600 0.9rem Georgia, serif;
        }
        .sidebar-brand { margin-bottom: 1.9rem; }
        .sidebar-brand h2 { color: #ffffff !important; margin: 0 0 0.35rem !important; }
        .sidebar-brand p { color: #aabbb3 !important; font-size: 0.84rem; line-height: 1.45; }
        .page-rule { border-top: 1px solid var(--line); margin: 2rem 0 1.15rem; }
        [data-testid="stAlert"] {
            border: 0; border-radius: 6px; padding: 0.8rem 0.95rem;
            margin: 0.25rem 0 0.9rem;
        }
        [data-testid="stAlert"] p { line-height: 1.45; margin: 0; }
        [data-testid="stAlert"] svg { margin-top: 0.1rem; }
        [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
            gap: 0.6rem;
        }
        .status-panel { padding: 0.25rem 0 0.5rem; }
        .status-label { color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06rem; }
        .status-value { font: 500 1.7rem Georgia, serif; color: var(--ink); margin: 0.25rem 0; }
        .status-note { color: var(--muted); font-size: 0.9rem; line-height: 1.5; }
        .decision-card, .action-card {
            border: 1px solid var(--line); border-radius: 6px; padding: 1.35rem;
            margin: 0.35rem 0 1.2rem;
        }
        .decision-card { background: #193128; border-color: #193128; }
        .decision-card.is-abstain { background: #fff9df; border-color: #eee2a9; }
        .decision-card .status-label { color: #acc6b9; }
        .decision-card.is-abstain .status-label { color: #8d6b16; }
        .decision-card .status-value { color: #ffffff; font-size: 1.85rem; }
        .decision-card.is-abstain .status-value { color: #473b17; }
        .decision-card .status-note { color: #d4e2db; }
        .decision-card.is-abstain .status-note { color: #6e5d2c; }
        .action-card { background: #ffffff; }
        .action-card .status-value { font-size: 1.35rem; }
        .action-card .status-note { margin-bottom: 1rem; }
        .probe-callout {
            border-left: 3px solid var(--accent); padding: 0.3rem 0 0.3rem 1rem;
            margin: 0.4rem 0 0.8rem;
        }
        .probe-callout strong { font: 500 1.1rem Georgia, serif; color: var(--ink); }
        .stButton > button {
            border-radius: 4px; border: 1px solid #1c3029; background: #1c3029;
            color: #ffffff; font-weight: 600; min-height: 2.55rem;
        }
        .stButton > button:hover { background: #2b493e; border-color: #2b493e; color: #ffffff; }
        [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
        @media (max-width: 700px) {
            .block-container { padding: 1.25rem 1rem 2.5rem; }
            h1 { font-size: 2.15rem !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_theme()


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
    fig.add_trace(go.Scatter(
        x=baseline["time"], y=baseline["pressure"], name="Expected",
        line=dict(color="#89918c", dash="dash", width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=live["time"], y=live["pressure"], name="Observed",
        line=dict(color=SCENARIO_COLORS.get(scenario, "#17826D"), width=2.5),
        fill="tonexty", fillcolor="rgba(23, 130, 109, 0.07)",
    ))
    fig.update_layout(
        title=dict(text=f"Pressure trace / {sensor}", x=0, font=dict(family="Georgia, serif", size=18)),
        xaxis_title="Simulation time (seconds)", yaxis_title="Pressure (m)",
        height=380, margin=dict(t=78, b=32, l=18, r=18),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, Arial, sans-serif", color="#4D5752"),
        legend=dict(orientation="h", y=1.18, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="#EDF0EC", zeroline=False),
    )
    return fig


def posterior_figure(posterior: dict) -> go.Figure:
    causes = list(posterior.keys())
    probs = [posterior[c] * 100 for c in causes]
    colors = [SCENARIO_COLORS.get(c, "#CCCCCC") for c in causes]
    fig = go.Figure(go.Bar(
        x=probs, y=[SCENARIO_LABELS.get(c, c) for c in causes], orientation="h",
        marker_color=colors, text=[f"{p:.1f}%" for p in probs], textposition="outside",
        cliponaxis=False, width=0.55,
    ))
    fig.update_layout(
        title=dict(text="Cause likelihood", x=0, font=dict(family="Georgia, serif", size=18)),
        xaxis=dict(range=[0, 108], ticksuffix="%", showgrid=True, gridcolor="#EDF0EC", zeroline=False),
        yaxis=dict(showgrid=False, categoryorder="total ascending"),
        height=380, margin=dict(t=78, b=32, l=18, r=48),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", showlegend=False,
        font=dict(family="Inter, Arial, sans-serif", color="#4D5752"),
    )
    return fig


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
st.sidebar.title("💧 HydraID")
st.sidebar.caption("Identifiability-aware diagnosis for water networks")
st.sidebar.markdown(
    """
    <div class="sidebar-brand">
      <div class="brand-mark">H</div>
      <div class="brand-kicker">Network intelligence</div>
      <h2>HydraID</h2>
      <p>Decision support for pressure anomalies in water distribution networks.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.caption("Scenario source")
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
st.sidebar.markdown("<div class='section-kicker'>Investigation setup</div>", unsafe_allow_html=True)
st.sidebar.subheader("Incoming alarm")
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

top_cause = max(posterior, key=posterior.get)
metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("Decision state", decision["status"])
metric_2.metric("Leading hypothesis", SCENARIO_LABELS.get(top_cause, top_cause))
metric_3.metric(
    "Evidence coverage",
    f"{len(st.session_state.observed_sensors)} / {len(all_sensors)} sensors",
)

st.markdown("<div class='page-rule'></div>", unsafe_allow_html=True)
col1, col2 = st.columns([1.2, 1], gap="medium")

with col1:
    st.markdown("<div class='section-kicker'>01 / Observed anomaly</div>", unsafe_allow_html=True)
    st.plotly_chart(pressure_trace_figure(signatures, true_scenario, true_case_id, alarm_sensor),
                     use_container_width=True)

    st.markdown("<div class='section-kicker'>02 / Competing explanations</div>", unsafe_allow_html=True)
    st.plotly_chart(posterior_figure(posterior), use_container_width=True)

with col2:
    st.markdown("<div class='section-kicker'>03 / Decision</div>", unsafe_allow_html=True)
    if decision["status"] == "RESOLVED":
        st.markdown(
            f"""
            <div class="decision-card">
              <div class="status-label">Resolution available</div>
              <div class="status-value">{SCENARIO_LABELS.get(decision['top_cause'], decision['top_cause'])}</div>
              <div class="status-note">{decision['confidence']:.1%} calibrated confidence. The evidence supports an operational resolution.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="decision-card is-abstain">
              <div class="status-label">Resolution withheld</div>
              <div class="status-value">More evidence required</div>
              <div class="status-note">{decision['reason']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if "equivalence_class" in decision:
            eq = decision["equivalence_class"]
            st.caption("Competing families: " + ", ".join(
                SCENARIO_LABELS.get(scenario, scenario)
                for scenario in eq["scenarios_involved"]
            ))

    st.markdown("<div class='section-kicker'>04 / Next field check</div>", unsafe_allow_html=True)
    with st.container():
        if recommendations:
            top_check = recommendations[0]
            st.markdown(
                f"""
                <div class="action-card">
                  <div class="status-label">Recommended sensor</div>
                  <div class="status-value">{top_check['sensor']}</div>
                  <div class="status-note">{top_check['expected_info_gain']:.2f} bits of information gain at a travel cost of {top_check['inspection_cost']:.0f}.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Record reading from {top_check['sensor']}", use_container_width=True):
                st.session_state.observed_sensors.append(top_check["sensor"])
                st.rerun()
        else:
            st.markdown(
                "<div class='status-note'>No additional field reading is required for this evidence state.</div>",
                unsafe_allow_html=True,
            )

st.markdown("---")
with st.expander("Ambiguous hypothesis pairs at current tolerance"):
    st.dataframe(ambiguities, use_container_width=True, hide_index=True)

with st.expander("Raw event residual vector sent to the model"):
    st.json(event_residuals)
