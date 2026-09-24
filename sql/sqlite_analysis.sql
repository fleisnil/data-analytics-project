-- name: delay_by_region_mode
SELECT
    s.region,
    o.transport_mode,
    COUNT(*) AS observations,
    ROUND(AVG(o.delay_minutes), 3) AS mean_delay_minutes,
    ROUND(AVG(o.is_delayed_5), 4) AS delayed_5_share
FROM observations AS o
INNER JOIN stations AS s
    ON o.station_id = s.station_id
GROUP BY s.region, o.transport_mode
ORDER BY mean_delay_minutes DESC;

-- name: delay_by_hour
SELECT
    o.scheduled_hour,
    COUNT(*) AS observations,
    ROUND(AVG(o.delay_minutes), 3) AS mean_delay_minutes,
    ROUND(AVG(o.is_delayed_5), 4) AS delayed_5_share
FROM observations AS o
GROUP BY o.scheduled_hour
ORDER BY o.scheduled_hour;

-- name: weather_delay_join
SELECT
    o.observation_id,
    s.station_name,
    s.region,
    o.transport_mode,
    o.delay_minutes,
    w.precipitation,
    w.wind_speed_10m,
    w.temperature_2m
FROM observations AS o
INNER JOIN stations AS s
    ON o.station_id = s.station_id
LEFT JOIN weather_hourly AS w
    ON o.station_id = w.station_id
    AND o.observation_hour = w.observation_hour
ORDER BY o.delay_minutes DESC
LIMIT 500;

