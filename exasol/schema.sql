-- HydraID — Exasol Schema (Phase 2)
-- Run once against a fresh HYDRAID schema, e.g.:
--   docker compose exec exasol exaplus -c localhost:8563 -u sys -p exasol --encryption ON --sslcertificate ignore < schema.sql
-- or paste into DBeaver / exaplus pointed at localhost:8563.
--
-- All table/column names match the data dictionary in README.md exactly —
-- do not rename anything here without updating README.md and the loaders.

CREATE SCHEMA IF NOT EXISTS HYDRAID;
OPEN SCHEMA HYDRAID;

-- ---------------------------------------------------------------------
-- Network metadata: every pipe and junction in the L-Town model, tagged
-- with whether it's one of the frozen leak zones / sensor nodes.
-- ---------------------------------------------------------------------
CREATE TABLE DIM_NETWORK (
    network_id      VARCHAR(100) NOT NULL,
    element_type    VARCHAR(50)  NOT NULL,   -- 'pipe' | 'junction' | 'reservoir'
    element_id      VARCHAR(100) NOT NULL,
    zone_id         VARCHAR(100),            -- non-null only if this element is a frozen leak zone / sensor
    CONSTRAINT PK_DIM_NETWORK PRIMARY KEY (network_id, element_type, element_id)
);

-- Fixed 12-sensor scope
CREATE TABLE DIM_SENSOR (
    sensor_id       VARCHAR(100) NOT NULL,
    node_id         VARCHAR(100) NOT NULL,
    sensor_type     VARCHAR(50),
    CONSTRAINT PK_DIM_SENSOR PRIMARY KEY (sensor_id)
);

-- Scenario / hypothesis definitions (one row per case_id in FACT_SIGNATURE)
CREATE TABLE DIM_HYPOTHESIS (
    hypothesis_id   VARCHAR(100) NOT NULL,
    scenario        VARCHAR(100) NOT NULL,
    case_id         VARCHAR(100) NOT NULL,
    CONSTRAINT PK_DIM_HYPOTHESIS PRIMARY KEY (hypothesis_id)
);

-- Raw simulated signatures (the scenario cube — 35,868 rows)
CREATE TABLE FACT_SIGNATURE (
    scenario        VARCHAR(100)  NOT NULL,
    case_id         VARCHAR(100)  NOT NULL,
    sensor          VARCHAR(100)  NOT NULL,
    sim_time        DECIMAL(18,0) NOT NULL,
    pressure        DECIMAL(18,8)
);

-- Live / operator-entered sensor readings for a diagnostic event
CREATE TABLE FACT_OBSERVATION (
    observation_id      VARCHAR(100) NOT NULL,
    event_id             VARCHAR(100) NOT NULL,   -- groups readings belonging to one diagnostic event
    sensor_id             VARCHAR(100) NOT NULL,
    observation_time      TIMESTAMP,
    sim_time               DECIMAL(18,0),          -- elapsed seconds since event start; matches FACT_SIGNATURE.sim_time so residuals can be joined directly
    observation_value      DECIMAL(18,8),
    quality                 VARCHAR(30),
    CONSTRAINT PK_FACT_OBSERVATION PRIMARY KEY (observation_id)
);

-- Computed probability per hypothesis, per diagnostic event
CREATE TABLE FACT_POSTERIOR (
    event_id        VARCHAR(100)  NOT NULL,
    hypothesis_id   VARCHAR(100)  NOT NULL,
    likelihood      DECIMAL(18,10),
    probability     DECIMAL(18,10),
    CONSTRAINT PK_FACT_POSTERIOR PRIMARY KEY (event_id, hypothesis_id)
);

-- Ranked next-check recommendations
CREATE TABLE MART_PROBE_RANK (
    event_id        VARCHAR(100) NOT NULL,
    probe_id        VARCHAR(100) NOT NULL,   -- sensor_id being recommended
    eig             DECIMAL(18,10),
    cost            DECIMAL(18,10),
    risk            DECIMAL(18,10),
    rank_value      INTEGER,
    CONSTRAINT PK_MART_PROBE_RANK PRIMARY KEY (event_id, probe_id)
);

-- Reproducibility log: one row per pipeline run
CREATE TABLE AUDIT_RUN (
    run_id              VARCHAR(100) NOT NULL,
    model_version       VARCHAR(100),
    data_version        VARCHAR(100),
    tolerance           DECIMAL(18,10),
    data_hash           VARCHAR(128),
    operator_override   VARCHAR(2000),
    CONSTRAINT PK_AUDIT_RUN PRIMARY KEY (run_id)
);
