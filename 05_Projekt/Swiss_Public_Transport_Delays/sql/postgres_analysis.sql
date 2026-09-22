DROP MATERIALIZED VIEW IF EXISTS delay_region_mode;

CREATE MATERIALIZED VIEW delay_region_mode AS
SELECT
    region,
    transport_mode,
    COUNT(*) AS observations,
    AVG(delay_minutes) AS mean_delay_minutes,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_minutes) AS median_delay_minutes,
    AVG(is_delayed_5) AS delayed_5_share
FROM model_data
GROUP BY region, transport_mode;

CREATE INDEX IF NOT EXISTS idx_delay_region_mode
ON delay_region_mode(region, transport_mode);

