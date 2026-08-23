-- Wraps src/active_check.py's calculate_entropy() + compute_sensor_separating_power()
-- + rank_next_sensor_checks() as one in-database UDF.
--
-- Because this UDF needs three different "shapes" of input at once — the
-- candidate hypotheses' signature values, the current posterior
-- distribution, and (optionally) per-sensor inspection costs — the calling
-- query UNIONs three tagged blocks together (row_type = 'SIG' | 'POST' |
-- 'COST') and the script separates them back out. This is the standard
-- pattern for feeding a UDF several logically distinct tables at once.

OPEN SCHEMA HYDRAID;

CREATE OR REPLACE PYTHON3 SET SCRIPT UDF_RANK_NEXT_CHECKS (
    event_id          VARCHAR(100),
    row_type          VARCHAR(10),   -- 'SIG' | 'POST' | 'COST'
    sensor            VARCHAR(100),
    case_id           VARCHAR(100),
    pressure          DOUBLE,
    posterior_label   VARCHAR(100),
    posterior_prob    DOUBLE,
    cost              DOUBLE,
    noise_tolerance   DOUBLE
)
EMITS (
    event_id              VARCHAR(100),
    sensor                VARCHAR(100),
    separating_power      DOUBLE,
    expected_info_gain    DOUBLE,
    cost                  DOUBLE,
    action_score          DOUBLE
) AS

def run(ctx):
    import math

    event_id = None
    sig_pressure = {}   # case_id -> {sensor: pressure}
    posterior = {}       # label -> prob
    sensor_cost = {}      # sensor -> cost
    noise_tolerance = 0.5

    while True:
        event_id = ctx.event_id
        rtype = ctx.row_type

        if rtype == 'SIG':
            sig_pressure.setdefault(ctx.case_id, {})[ctx.sensor] = (
                float(ctx.pressure) if ctx.pressure is not None else 0.0
            )
        elif rtype == 'POST':
            if ctx.posterior_label is not None and ctx.posterior_prob is not None:
                posterior[ctx.posterior_label] = float(ctx.posterior_prob)
        elif rtype == 'COST':
            if ctx.sensor is not None and ctx.cost is not None:
                sensor_cost[ctx.sensor] = float(ctx.cost)

        if ctx.noise_tolerance is not None:
            noise_tolerance = float(ctx.noise_tolerance)

        if not ctx.next():
            break

    # --- prior entropy of the current posterior (calculate_entropy) ---
    if posterior:
        probs = [max(p, 1e-9) for p in posterior.values()]
        total = sum(probs)
        probs = [p / total for p in probs]
        prior_entropy = -sum(p * math.log2(p) for p in probs)
    else:
        prior_entropy = 0.0

    case_ids = list(sig_pressure.keys())
    all_sensors = sorted({s for c in sig_pressure.values() for s in c.keys()})

    # --- separating power per sensor (compute_sensor_separating_power) ---
    separating_power = {}
    if len(case_ids) > 1:
        for sensor in all_sensors:
            values = [sig_pressure[c].get(sensor, 0.0) for c in case_ids]
            spread = max(values) - min(values)
            separating_power[sensor] = min(spread / (noise_tolerance * 2), 1.0)
    else:
        for sensor in all_sensors:
            separating_power[sensor] = 0.0

    # --- rank (rank_next_sensor_checks) ---
    for sensor in all_sensors:
        power = separating_power.get(sensor, 0.0)
        eig = prior_entropy * power
        c = sensor_cost.get(sensor, 1.0)
        score = eig / c if c else 0.0
        ctx.emit(event_id, sensor, round(power, 3), eig, c, score)
/

-- ---------------------------------------------------------------------
-- Example usage for one event (posterior already computed and staged in
-- FACT_POSTERIOR by the offline cause_inference step -- see
-- run_cause_inference.py -- and candidate_case_ids being the ambiguity
-- group returned by UDF_FIND_AMBIGUOUS_HYPOTHESES for that event).
--
-- IMPORTANT: source signature rows from V_CASE_SENSOR_PROFILE (see
-- udf_identifiability.sql), not raw FACT_SIGNATURE — the original Python
-- (compute_sensor_separating_power's pivot_table) averages pressure across
-- all 49 sim_time steps per (case_id, sensor) before comparing spreads.
-- Passing raw per-timestep rows instead would change the answer.
-- ---------------------------------------------------------------------
-- SELECT UDF_RANK_NEXT_CHECKS(event_id, row_type, sensor, case_id, pressure,
--                              posterior_label, posterior_prob, cost, noise_tolerance)
-- FROM (
--     SELECT :event_id AS event_id, 'SIG' AS row_type, sensor, case_id, avg_pressure AS pressure,
--            CAST(NULL AS VARCHAR(100)) AS posterior_label, CAST(NULL AS DOUBLE) AS posterior_prob,
--            CAST(NULL AS DOUBLE) AS cost, 0.5 AS noise_tolerance
--     FROM V_CASE_SENSOR_PROFILE
--     WHERE case_id IN (:candidate_case_ids)
--
--     UNION ALL
--
--     SELECT :event_id, 'POST', NULL, NULL, NULL, hypothesis_id, probability, NULL, 0.5
--     FROM FACT_POSTERIOR
--     WHERE event_id = :event_id
--
--     UNION ALL
--
--     SELECT :event_id, 'COST', sensor_id, NULL, NULL, NULL, NULL, 1.0, 0.5
--     FROM DIM_SENSOR
-- )
-- GROUP BY event_id;
