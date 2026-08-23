# 💧 HydraID

### Identifiability-Aware Diagnosis for Water Distribution Networks

**Built for the Exasol AI Build Challenge 2026**

[![Status](https://img.shields.io/badge/status-in%20progress-yellow)]()
[![Data%20Platform](https://img.shields.io/badge/data%20platform-Exasol%20Personal-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

---

## Table of Contents

- [The Problem](#the-problem)
- [The Idea](#the-idea)
- [Why This Matters](#why-this-matters)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Data](#data)
- [Exasol Schema & Data Dictionary](#exasol-schema--data-dictionary)
- [Project Status](#project-status)
- [Setup](#setup)
- [Troubleshooting](#troubleshooting)
- [Repository Structure](#repository-structure)
- [Submission Checklist](#submission-checklist)
- [Team](#team)
- [License](#license)

---

## The Problem

When a water utility gets an anomaly alert — a pressure drop, a strange reading — the honest answer to *"what caused this?"* is often **"we can't tell yet."** A leak, a sudden demand surge, and a miscalibrated sensor can all look identical from a handful of pressure readings. Most anomaly-detection systems paper over this ambiguity and confidently output a single guess anyway, which means operators either chase false alarms or miss real leaks.

**HydraID doesn't guess when it shouldn't.**

## The Idea

Instead of forcing a single diagnosis, HydraID:

1. **Simulates** what every possible fault (leak, demand shift, sensor bias, stuck sensor) *should* look like across the sensor network — a "scenario cube" of known signatures.
2. **Compares** live sensor readings against that cube to see which causes are consistent with what's observed.
3. **Checks identifiability** — if two or more causes produce statistically indistinguishable signatures given current evidence, HydraID **abstains** and reports them as a tied group, instead of picking one arbitrarily.
4. **Recommends the cheapest, safest next check** (which sensor to read, or where to send a crew) that would actually resolve the ambiguity — ranked by expected information gain against cost and risk.
5. **Locks in** the correct diagnosis once that new reading comes in.

This mirrors how a good field engineer actually reasons: *"I can't tell if it's a leak or a bad sensor yet — let me check the meter two streets over before I decide."*

## Why This Matters

Sending a crew to inspect a "leak" that's actually a faulty sensor wastes time and money. Ignoring a real leak because it looked like sensor noise wastes water and risks infrastructure damage. An honest **"I don't know yet, but here's how to find out"** is more valuable — and more trustworthy — than a confident wrong answer.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│   L-Town Water   │────▶│   WNTR/EPANET    │────▶│   Exasol Personal  │
│     Network      │     │   Simulation     │     │   (Scenario Cube)  │
│ (782 nodes, 905  │     │  Baseline + 4    │     │   FACT_SIGNATURE   │
│      pipes)      │     │  fault families  │     │                    │
└─────────────────┘     └──────────────────┘     └─────────┬──────────┘
                                                             │
                         ┌───────────────────────────────────┘
                         ▼
              ┌─────────────────────┐      ┌──────────────────────┐
              │   Residual Engine    │─────▶│  Identifiability      │
              │  (live vs. signature)│      │  Check / Abstain      │
              └─────────────────────┘      └──────────┬───────────┘
                                                        │ ambiguous?
                                                        ▼
                                          ┌──────────────────────────┐
                                          │   Probe Planner           │
                                          │  EIG − cost − risk rank   │
                                          └──────────┬───────────────┘
                                                      ▼
                                          ┌──────────────────────────┐
                                          │   Streamlit Dashboard     │
                                          │  Anomaly → Ambiguity →    │
                                          │  Probe → Resolved cause   │
                                          └──────────────────────────┘
```

## Tech Stack

| Layer | Tools |
|---|---|
| Hydraulic simulation | Python, WNTR, EPANET |
| Data backbone | **Exasol Personal** (star schema) |
| Inference | NumPy, SciPy, pandas, scikit-learn |
| Active-check planning | NetworkX / OR-Tools |
| Dashboard | Streamlit, Plotly |

## Data

We use the **BattLeDIM L-Town** network — a synthetic-but-realistic water distribution benchmark (782 junctions, 905 pipes, 3 reservoirs) designed for leak-detection research.

**Frozen scope** (fixed for the entire project — do not regenerate with a different seed):

- **12 sensors:** `n26, n105, n115, n143, n229, n251, n282, n655, n693, n755, n759, n760`
- **24 leak zones:** `p204, p224, p226, p239, p28, p285, p31, p33, p430, p433, p460, p518, p559, p575, p604, p605, p617, p666, p719, p734, p829, p891, p90, p96`

The public source `.inp` file has **no built-in demand variation** — every junction has constant demand, so pressure never naturally changes hour to hour. We layered in a synthetic diurnal demand pattern (`simulation/generate_signatures.py`) so that time-based faults, like a stuck sensor, are actually detectable rather than trivially flat.

## Exasol Schema & Data Dictionary

Exasol Personal (run locally via Docker) is the system's data backbone. Schema: `HYDRAID`.

| Table | Purpose |
|---|---|
| `DIM_NETWORK` | Physical network topology |
| `DIM_SENSOR` | Sensor metadata and health state |
| `DIM_HYPOTHESIS` | Candidate fault causes |
| `FACT_SIGNATURE` | Simulated "what should this look like" scenario cube |
| `FACT_OBSERVATION` | Live/operator-entered sensor readings |
| `FACT_POSTERIOR` | Computed probability per hypothesis, per event |
| `MART_PROBE_RANK` | Ranked next-check recommendations |
| `AUDIT_RUN` | Reproducibility log (data hash, tolerance, code version) per run |

### `FACT_SIGNATURE` — the core table (35,868 rows)

| Column | Type | Description |
|---|---|---|
| `SCENARIO` | VARCHAR | Fault family: `baseline`, `leak`, `demand`, `bias`, `stuck` |
| `CASE_ID` | VARCHAR | Specific case within a scenario — e.g. leak pipe `p204`, or `bias_n143` |
| `SENSOR` | VARCHAR | Sensor node ID (one of the 12 frozen sensors) |
| `SIM_TIME` | DECIMAL | Simulated time in seconds, 30-minute steps: `0, 1800, 3600 ... 86400` (49 steps/day) |
| `PRESSURE` | DECIMAL | Simulated pressure reading (meters) at that sensor, case, and time |

**Row breakdown:**

| Scenario | Distinct cases | Rows |
|---|---|---|
| `baseline` | 1 | 588 |
| `leak` | 24 (one per leak zone) | 14,112 |
| `demand` | 12 (one per sensor node) | 7,056 |
| `bias` | 12 (one per sensor node) | 7,056 |
| `stuck` | 12 (one per sensor node) | 7,056 |
| **Total** | | **35,868** |

Each case carries the **full 49-step time series across all 12 sensors** — not a single snapshot — which is what makes temporal fault types (demand shift, stuck sensor) genuinely distinguishable rather than trivial.

**Design notes for whoever queries this:**
- A sensor-bias or stuck-sensor fault only corrupts the reading *at the faulty sensor itself*; every other sensor in that case reports true baseline. This is intentional — it's what makes a "probe" (checking a different sensor) actually informative.
- To reproduce the project's core "ambiguity → probe → resolution" story, compare a live observation against signatures using only a **subset** of sensors first (e.g. just the alarm sensor). Using all 12 sensors from the start makes every case trivially distinguishable and removes the need for probing entirely.

---

## Project Status

- [x] **Step 1 — Golden Scenario:** Network frozen, scope locked, all 4 fault families simulated with real physics
- [x] **Step 2 — Exasol Database:** Star schema live, scenario cube loaded and verified (35,868 rows, real time-series confirmed)
- [x] **Step 3 — Inference & Identifiability:** Residual engine, calibrated XGBoost cause classifier, and signature-equivalence abstention logic (`src/test_pipeline.py`)
- [x] **Step 4 — Active Check:** Observed-sensor-aware probe planner (expected information gain vs. NetworkX pipe-distance cost), with an abstain → probe validation
- [x] **Step 5 — Dashboard:** Streamlit operator view (`app/dashboard.py`) — Anomaly → Ambiguous causes → Recommended check → Resolved cause

## Setup

**Prerequisites:** Docker Desktop, Python 3.10+

```bash
git clone https://github.com/haripriyasubbiah/hydraid.git
cd hydraid

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install wntr pandas numpy scipy scikit-learn pyexasol
```

**Spin up Exasol:**
```bash
cd exasol
docker compose up -d
docker compose logs -f     # wait for the database to report ready (first boot takes a few minutes)
```

**Create the schema:**
```bash
# Apply schema.sql via any SQL client pointed at localhost:8563 (DBeaver, exaplus, etc.)
```

**Generate the scenario cube and load it:**
```bash
cd simulation
python generate_signatures.py      # produces signatures.csv

cd ../exasol
python load_signatures.py          # loads signatures.csv into FACT_SIGNATURE
```

**Verify the load:**
```python
import pyexasol
c = pyexasol.connect(dsn='localhost:8563', user='sys', password='exasol',
                      schema='HYDRAID', websocket_sslopt={'cert_reqs': 0})
print(c.execute("SELECT COUNT(*) FROM FACT_SIGNATURE").fetchone())   # expect (35868,)
c.close()
```

**Run the dashboard:**
```bash
pip install -r requirement.txt
streamlit run app/dashboard.py
```
Then open the URL Streamlit prints (usually `http://localhost:8501`). Use the sidebar to switch between
`CSV (local)` (works with no Docker/Exasol running — good for quick demos) and `Exasol (live)` (queries
`FACT_SIGNATURE` over the Docker Exasol instance — the required data platform for judging).

## Troubleshooting

Issues we actually hit while building this, in case you hit them too:

| Symptom | Cause | Fix |
|---|---|---|
| `AttributeError: 'Reservoir' object has no attribute 'add_leak'` | Tried to inject a leak on a pipe whose endpoint is a reservoir/tank, not a junction | Pick whichever pipe endpoint is a `Junction` before calling `add_leak()` |
| All rows for a case show the exact same `PRESSURE` value | Simulation only exported the final timestep and duplicated it to pad row counts | Loop over every timestep in `results.node['pressure'].index`, don't just grab the last one |
| Pressure never changes across timesteps even with a full time loop | Source `.inp` file has zero demand patterns — constant demand by default | Add a synthetic diurnal demand pattern to every junction before simulating |
| `git clone` of the official BattLeDIM repo gives a Git-LFS pointer file instead of real data | GitHub LFS storage isn't pulled by a plain clone in some environments | Use a plain-text mirror of `l_town.inp`, or run `git lfs pull` if LFS is set up locally |
| PowerShell mangles Python one-liners with nested quotes | PowerShell's quote-escaping differs from bash | Write a small `.py` script file instead of inlining complex `python -c "..."` commands |

## Repository Structure

```
hydraid/
├── data/                 # L-Town network file, frozen scope definitions
├── simulation/           # WNTR/EPANET fault-injection & signature generation
├── exasol/               # Docker Compose, schema, data loader
├── src/                  # Residual engine, cause inference, identifiability,
│                         # active-check planner, exasol reader, pipeline (Steps 3–4)
├── app/                  # Streamlit operator dashboard (Step 5)
│   └── dashboard.py
└── tests/                # Golden-scenario, active-check, and holdout evaluations
```


## Team

Built by a team of 5 for the Exasol AI Build Challenge 2026.

## License

MIT — see [LICENSE](./LICENSE).
