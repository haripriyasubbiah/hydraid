# HydraID — Phase 2 (Infrastructure)

Everything in this folder replaces/extends the original `exasol/` folder.
Drop these files in over the existing ones (or just replace the folder) and
follow the steps below.

## What was already working

`schema.sql`'s table design and `load_signatures.py`'s overall approach were
solid — no need to redesign the data model, README.md's data dictionary is
kept accurate throughout.

## What was fixed

| File | Problem | Fix |
|---|---|---|
| `docker-compose.yml` | Pointed at `exasol/docker-db`, which needs a separate `init-sc --template` step before it can even start — a bare `docker compose up` just fails. | Switched to `exasol/nano`, Exasol's actual single-node dev image, with the correct `shm_size`/`pids_limit` settings from Exasol's own docs. |
| `load_signatures.py` | Hardcoded row-count check for `2940` (a leftover from an early smaller test run) — blocks every real load, since the real cube is 35,868 rows. | Fixed to `35868`, matching README.md and the actual `signatures.csv`. |
| `load_signatures.py` / `check_time.py` | Connected without `encryption=True`. Nano's SQL port is TLS-only, so this would hang/fail. | Centralized in `exasol_conn.py` with the correct TLS settings. |
| `DIM_NETWORK`, `DIM_SENSOR`, `DIM_HYPOTHESIS` | Declared in schema.sql, documented in README.md, but nothing loaded them — they'd sit empty forever. | New `load_dimensions.py` populates all three from `data/l_town.inp` + `data/scope_selection.py` + `signatures.csv`. |

## What was added

- **UDF wrappers** (the actual Phase 2 ask) for the parts of `src/` that are
  cheap, dependency-light numeric work:
  - `udf_residual_features.sql` → `src/residual_engine.py`
  - `udf_identifiability.sql` → `src/identifiability.py`
  - `udf_active_check.sql` → `src/active_check.py`

  Each was checked against the original Python implementation on the real
  `signatures.csv` and produces identical output (same 1,176 ambiguous
  pairs, same sensor rankings to 6 decimal places).

- **`run_diagnostic_event.py`** — orchestrates a full diagnostic run:
  trains/scores with XGBoost client-side (see below for why), then pushes
  the identifiability + active-check steps down into Exasol via the UDFs
  above, and writes the result into `FACT_POSTERIOR` / `MART_PROBE_RANK` so
  Teammate 3's dashboard has something to query.

- **`verify.py`** — one script that checks every table's row count against
  what it should be, not just `FACT_SIGNATURE`.

## What's *not* a UDF, on purpose

`src/cause_inference.py` (XGBoost training + calibration) stays client-side.
Exasol UDFs run inside a Script Language Container that only has whatever
packages were installed into it — the base container you get from
`init slc install=all` doesn't include xgboost/scikit-learn. Building a
custom SLC with those baked in is real infra work that isn't worth it for
this timeline; running training outside and writing only the resulting
probabilities into `FACT_POSTERIOR` is the standard, defensible pattern
here. Flagged in `run_diagnostic_event.py`'s docstring in case the team
wants to revisit it later.

## Setup, in order

```bash
cd exasol

# 1. Start Exasol (first time: also install the Python language container)
docker compose up -d
docker compose run --rm exasol init slc install=all   # one-time, persists in the volume
docker compose logs -f   # wait for "Database is now up and running!"

# 2. Apply the schema (any SQL client pointed at localhost:8563, TLS on,
#    cert check off for local dev — e.g. DBeaver, or exaplus:
#    exaplus -c localhost:8563 -u sys -p exasol --encryption ON --sslcertificate ignore)
#    Run schema.sql, then udf_residual_features.sql, udf_identifiability.sql,
#    udf_active_check.sql (these last three both declare tables/views and UDFs).

pip install pyexasol wntr pandas xgboost scikit-learn --break-system-packages

# 3. Load dimension tables and the scenario cube
python load_dimensions.py
python load_signatures.py

# 4. Confirm everything's in
python verify.py

# 5. Smoke-test the full pipeline end to end (writes into FACT_POSTERIOR / MART_PROBE_RANK)
python run_diagnostic_event.py --event-id demo1 --demo
```

## Notes for Teammate 3 (dashboard)

- `FACT_POSTERIOR` and `MART_PROBE_RANK` are what you query after
  `run_diagnostic_event.py` runs for an event — that's your "cause
  probabilities" and "recommended next check" data respectively.
- `DIM_SENSOR` / `DIM_NETWORK` are now populated, so map/plot views don't
  need to shell out to `wntr` again — everything's already in Exasol.
- Connection snippet for the Streamlit app is in `exasol_conn.py` — reuse
  `connect()` rather than rolling your own, so the TLS settings stay
  consistent everywhere.

## One thing I can't verify from here

I don't have a live Docker daemon or a way to pull the Exasol image in this
environment, so none of this has been run against a real Exasol instance —
only the *pure Python logic* inside each UDF was checked against the
original `src/` functions on the real 35,868-row dataset (exact match). The
SQL/UDF syntax follows Exasol's current documented syntax, but please run
`schema.sql` → the three `udf_*.sql` files → `verify.py` early and ping me
with whatever error comes back — SLC/UDF syntax is the most likely place
for something to need a small tweak on a real instance.
