-- HydraID Step 2 - Exasol Schema

-- Network metadata
CREATE TABLE DIM_NETWORK (
    network_id VARCHAR(100) NOT NULL,
    element_type VARCHAR(50),
    element_id VARCHAR(100),
    zone_id VARCHAR(100)
);

-- Fixed 12-sensor scope
CREATE TABLE DIM_SENSOR (
    sensor_id VARCHAR(100) NOT NULL,
    node_id VARCHAR(100) NOT NULL,
    sensor_type VARCHAR(50)
);

-- Scenario / hypothesis definitions
CREATE TABLE DIM_HYPOTHESIS (
    hypothesis_id VARCHAR(100) NOT NULL,
    scenario VARCHAR(100) NOT NULL,
    case_id VARCHAR(100) NOT NULL
);

-- Raw simulated signatures
CREATE TABLE FACT_SIGNATURE (
    scenario VARCHAR(100) NOT NULL,
    case_id VARCHAR(100) NOT NULL,
    sensor VARCHAR(100) NOT NULL,
    sim_time DECIMAL(18,0) NOT NULL,
    pressure DECIMAL(18,8)
);

-- Future observation table
CREATE TABLE FACT_OBSERVATION (
    observation_id VARCHAR(100) NOT NULL,
    sensor_id VARCHAR(100) NOT NULL,
    observation_time TIMESTAMP,
    observation_value DECIMAL(18,8),
    quality VARCHAR(30)
);

CREATE TABLE FACT_POSTERIOR (
    event_id VARCHAR(100) NOT NULL,
    hypothesis_id VARCHAR(100) NOT NULL,
    likelihood DECIMAL(18,10),
    probability DECIMAL(18,10)
);

CREATE TABLE MART_PROBE_RANK (
    event_id VARCHAR(100) NOT NULL,
    probe_id VARCHAR(100) NOT NULL,
    eig DECIMAL(18,10),
    cost DECIMAL(18,10),
    risk DECIMAL(18,10),
    rank_value INTEGER
);

CREATE TABLE AUDIT_RUN (
    run_id VARCHAR(100) NOT NULL,
    model_version VARCHAR(100),
    data_version VARCHAR(100),
    tolerance DECIMAL(18,10),
    data_hash VARCHAR(128),
    operator_override VARCHAR(2000)
);