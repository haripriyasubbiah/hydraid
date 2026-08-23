**# hydraid
Identifiability-aware diagnosis of leaks, demand shifts and sensor faults in sparse water networks.**# 💧 HydraID
### Identifiability-Aware Diagnosis for Water Distribution Networks

**Built for the Exasol AI Build Challenge 2026**

---

## The Problem

When a water utility gets an anomaly alert — a pressure drop, a weird reading — the honest answer to *"what caused this?"* is often **"we can't tell yet."** A leak, a sudden demand surge, and a miscalibrated sensor can all look identical from a handful of pressure readings. Most anomaly-detection systems paper over this ambiguity and confidently output a single guess anyway — which means operators either chase false alarms or miss real leaks.

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

We use the **BattLeDIM L-Town** network — a synthetic-but-realistic water distribution benchmark (782 junctions, 905 pipes, 3 reservoirs) designed for leak-detection research. We froze scope to:

- **12 sensors:** `n26, n105, n115, n143, n229, n251, n282, n655, n693, n755, n759, n760`
- **24 leak zones:** `p204, p224, p226, p239, p28, p285, p31, p33, p430, p433, p460, p518, p559, p575, p604, p605, p617, p666, p719, p734, p829, p891, p90, p96`

The source network has no built-in demand variation, so we layered in a synthetic diurnal demand pattern — otherwise pressure never changes hour to hour, which would make time-based faults (like a stuck sensor) undetectable by construction.

## How Exasol Is Used

Exasol Personal (run locally via Docker) is the system's data backbone — a star schema holding:

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

`FACT_SIGNATURE` currently holds **35,868 rows**: a full 49-step (30-minute interval) time series across all 12 sensors, for baseline conditions plus all 24 leak cases, 12 demand-shift cases, 12 sensor-bias cases, and 12 stuck-sensor cases.

---

## Project Status

- [x] **Step 1 — Golden Scenario:** Network frozen, scope locked, all 4 fault families simulated with real physics
- [x] **Step 2 — Exasol Database:** Star schema live, scenario cube loaded and verified
- [ ] **Step 3 — Inference & Identifiability:** Residual engine + abstention logic *(in progress)*
- [ ] **Step 4 — Active Check:** Probe planner (EIG vs. cost/risk ranking)
- [ ] **Step 5 — Dashboard:** Streamlit operator view

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
docker compose logs -f     # wait for the database to report ready
```

**Create the schema and load data:**
```bash
# Apply schema.sql via your SQL client of choice (DBeaver, exaplus, etc.)
# pointed at localhost:8563

python load_signatures.py
```

**Regenerate the scenario cube from scratch** (if you want to reproduce Step 1/2 yourself):
```bash
cd simulation
python generate_signatures.py
```

## Repository Structure

```
hydraid/
├── data/               # L-Town network file, frozen scope definitions
├── simulation/          # WNTR/EPANET fault-injection & signature generation
├── exasol/              # Docker Compose, schema, data loader
├── inference/           # Residual engine, identifiability check (Step 3)
├── probe_planner/       # Active-check / EIG ranking logic (Step 4)
└── app/                 # Streamlit operator dashboard (Step 5)
```

## Team

Built by a team of 5 for the Exasol AI Build Challenge 2026.

## License

MIT — see [LICENSE](./LICENSE).
