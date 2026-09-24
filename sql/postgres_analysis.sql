DROP MATERIALIZED VIEW IF EXISTS delay_region_mode;

CREATE OR REPLACE VIEW delay_weather_join AS
SELECT o.*, s.station_name, s.region, s.canton, s.latitude, s.longitude,
       w.temperature_2m, w.precipitation, w.wind_speed_10m, w.wind_gusts_10m, w.snowfall
FROM observations AS o
INNER JOIN stations AS s ON o.station_id = s.station_id
LEFT JOIN weather_hourly AS w
    ON o.station_id = w.station_id AND o.observation_hour = w.observation_hour;

CREATE MATERIALIZED VIEW delay_region_mode AS
SELECT
    region,
    transport_mode,
    COUNT(*) AS observations,
    AVG(delay_minutes) AS mean_delay_minutes,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_minutes) AS median_delay_minutes,
    AVG(is_delayed_5) AS delayed_5_share
FROM delay_weather_join
GROUP BY region, transport_mode;

CREATE INDEX IF NOT EXISTS idx_delay_region_mode
ON delay_region_mode(region, transport_mode);

