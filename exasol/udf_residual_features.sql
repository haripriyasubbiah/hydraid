-- Wraps src/residual_engine.py's compute_residuals() + extract_window_features()
-- as an in-database UDF.
--
-- Design note: compute_residuals() itself (an ABS-difference join on
-- sensor+time) is plain arithmetic on a join — that part is done in SQL
-- below (a join is what Exasol is for), and only the aggregation step
-- (mean/max/std per scenario/case_id/sensor, i.e. extract_window_features)
-- runs as the UDF. This gets you the same numbers as the original Python
-- with far less data movement, since Exasol pushes the join + grouping down
-- instead of pulling everything into a client process.
--
-- Prereq: `docker compose run --rm exasol init slc install=all` (see
-- docker-compose.yml comments) so the PYTHON3 language container exists.

OPEN SCHEMA HYDRAID;

CREATE OR REPLACE PYTHON3 SET SCRIPT UDF_RESIDUAL_FEATURES (
    event_id      VARCHAR(100),
    scenario      VARCHAR(100),
    case_id       VARCHAR(100),
    sensor        VARCHAR(100),
    residual      DOUBLE
)
EMITS (
    event_id      VARCHAR(100),
    scenario      VARCHAR(100),
    case_id       VARCHAR(100),
    sensor        VARCHAR(100),
    mean_res      DOUBLE,
    max_res       DOUBLE,
    std_res       DOUBLE
) AS

def run(ctx):
    import math

    event_id = None
    scenario = None
    case_id = None
    sensor = None
    values = []

    while True:
        event_id = ctx.event_id
        scenario = ctx.scenario
        case_id = ctx.case_id
        sensor = ctx.sensor
        r = ctx.residual
        if r is not None:
            values.append(float(r))

        if not ctx.next():
            break

    if values:
        n = len(values)
        mean_res = sum(values) / n
        max_res = max(values)
        # sample std, ddof=1, matching pandas' default .agg(std_res='std');
        # falls back to 0.0 for a single point, same as the original
        # features['std_res'] = features['std_res'].fillna(0.0)
        if n > 1:
            variance = sum((v - mean_res) ** 2 for v in values) / (n - 1)
            std_res = math.sqrt(variance)
        else:
            std_res = 0.0
    else:
        mean_res = max_res = std_res = 0.0

    ctx.emit(event_id, scenario, case_id, sensor, mean_res, max_res, std_res)
/

-- ---------------------------------------------------------------------
-- Example usage: residual features for one live diagnostic event.
--
-- Assumes FACT_OBSERVATION rows for this event carry sim_time values that
-- line up with FACT_SIGNATURE.sim_time (see schema.sql comment on
-- FACT_OBSERVATION.sim_time), so the join below is exact rather than a
-- nearest-neighbour match.
-- ---------------------------------------------------------------------
-- SELECT UDF_RESIDUAL_FEATURES(o.event_id, s.scenario, s.case_id, s.sensor,
--                               ABS(s.pressure - o.observation_value))
-- FROM FACT_SIGNATURE s
-- JOIN FACT_OBSERVATION o
--   ON o.sensor_id = s.sensor
--  AND o.sim_time   = s.sim_time
-- WHERE o.event_id = :event_id
-- GROUP BY o.event_id, s.scenario, s.case_id, s.sensor;
