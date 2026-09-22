CREATE OR REPLACE VIEW delay_weather_join AS
SELECT
    o.*,
    w.temperature_2m,
    w.precipitation,
    w.wind_speed_10m,
    w.wind_gusts_10m,
    w.snowfall
FROM observations AS o
LEFT JOIN weather_hourly AS w
    ON o.station_id = w.station_id
   AND o.observation_hour = w.observation_hour;

CREATE OR REPLACE TABLE delay_region_mode AS
SELECT
    region,
    transport_mode,
    COUNT(*) AS observations,
    AVG(delay_minutes) AS mean_delay_minutes,
    MEDIAN(delay_minutes) AS median_delay_minutes,
    AVG(is_delayed_5) AS delayed_5_share
FROM delay_weather_join
GROUP BY region, transport_mode;

