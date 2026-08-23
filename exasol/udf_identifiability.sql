-- Wraps src/identifiability.py's find_ambiguous_hypotheses() as an
-- in-database UDF.
--
-- The Python version pivots FACT_SIGNATURE into a (case_id x sensor)
-- profile table (averaging over sim_time via pandas' pivot_table default),
-- then does pairwise Euclidean distance between every pair of cases and
-- flags pairs closer than `noise_tolerance` as observationally ambiguous.
--
-- Here the pivot/average is a plain SQL view (V_CASE_SENSOR_PROFILE), and
-- only the O(n^2) pairwise-distance part — the part that's awkward in SQL —
-- runs as a UDF. With 61 cases that's ~1,800 pairs, trivial for a UDF.

OPEN SCHEMA HYDRAID;

CREATE OR REPLACE VIEW V_CASE_SENSOR_PROFILE AS
SELECT
    scenario,
    case_id,
    sensor,
    AVG(pressure) AS avg_pressure
FROM FACT_SIGNATURE
GROUP BY scenario, case_id, sensor;

CREATE OR REPLACE PYTHON3 SET SCRIPT UDF_FIND_AMBIGUOUS_HYPOTHESES (
    scenario          VARCHAR(100),
    case_id           VARCHAR(100),
    sensor            VARCHAR(100),
    avg_pressure      DOUBLE,
    noise_tolerance   DOUBLE
)
EMITS (
    case_1               VARCHAR(100),
    case_2               VARCHAR(100),
    scenario_1           VARCHAR(100),
    scenario_2           VARCHAR(100),
    signature_distance   DOUBLE,
    status               VARCHAR(30)
) AS

def run(ctx):
    import math

    profiles = {}          # case_id -> {sensor: pressure}
    scenario_by_case = {}  # case_id -> scenario
    tolerance = 0.35        # matches identifiability.py's default

    while True:
        case_id = ctx.case_id
        sensor = ctx.sensor
        pressure = ctx.avg_pressure
        t = ctx.noise_tolerance

        if t is not None:
            tolerance = float(t)

        profiles.setdefault(case_id, {})[sensor] = float(pressure) if pressure is not None else 0.0
        scenario_by_case[case_id] = ctx.scenario

        if not ctx.next():
            break

    all_sensors = sorted({s for p in profiles.values() for s in p.keys()})
    case_ids = sorted(profiles.keys())

    for i in range(len(case_ids)):
        for j in range(i + 1, len(case_ids)):
            c1, c2 = case_ids[i], case_ids[j]
            v1, v2 = profiles[c1], profiles[c2]

            sq_sum = 0.0
            for s in all_sensors:
                d = v1.get(s, 0.0) - v2.get(s, 0.0)
                sq_sum += d * d
            dist = math.sqrt(sq_sum)

            if dist < tolerance:
                ctx.emit(c1, c2, scenario_by_case[c1], scenario_by_case[c2], dist, 'ABSTAIN_EQUIVALENT')
/

-- ---------------------------------------------------------------------
-- Example usage: full ambiguity table over the whole scenario cube.
-- The literal `1 AS grp` forces every row into a single UDF call so the
-- script sees the complete set of cases at once (needed for pairwise
-- comparison) instead of being split into per-case groups.
-- ---------------------------------------------------------------------
-- SELECT UDF_FIND_AMBIGUOUS_HYPOTHESES(scenario, case_id, sensor, avg_pressure, 0.35)
-- FROM (SELECT 1 AS grp, scenario, case_id, sensor, avg_pressure FROM V_CASE_SENSOR_PROFILE)
-- GROUP BY grp;
