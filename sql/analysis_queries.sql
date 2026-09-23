-- name: row_counts
SELECT 'transport_observations' AS table_name, COUNT(*) AS rows
FROM transport_observations
UNION ALL
SELECT 'weather_observations', COUNT(*)
FROM weather_observations
UNION ALL
SELECT 'stations', COUNT(*)
FROM stations
UNION ALL
SELECT 'transport_weather_joined', COUNT(*)
FROM transport_weather_joined;

-- name: delay_by_city_mode
SELECT
    city,
    transport_mode,
    COUNT(*) AS observations,
    ROUND(AVG(predicted_delay_minutes), 2) AS avg_predicted_delay_min,
    ROUND(
        100.0 * AVG(
            CASE
                WHEN is_predicted_delayed_5min = 1 THEN 1.0
                ELSE 0.0
            END
        ),
        1
    ) AS delayed_5min_share_pct
FROM transport_observations
GROUP BY city, transport_mode
ORDER BY city, transport_mode;

-- name: weather_join_quality
SELECT
    city,
    COUNT(*) AS transport_observations,
    SUM(
        CASE WHEN weather_id IS NOT NULL THEN 1 ELSE 0 END
    ) AS weather_matches,
    ROUND(
        100.0 * SUM(
            CASE WHEN weather_id IS NOT NULL THEN 1 ELSE 0 END
        ) / COUNT(*),
        1
    ) AS weather_match_rate_pct,
    ROUND(AVG(weather_time_gap_minutes), 2) AS avg_weather_gap_min,
    ROUND(MAX(weather_time_gap_minutes), 2) AS max_weather_gap_min
FROM transport_weather_joined
GROUP BY city
ORDER BY city;

-- name: delay_with_weather
SELECT
    city,
    transport_mode,
    COUNT(*) AS observations,
    ROUND(AVG(predicted_delay_minutes), 2) AS avg_predicted_delay_min,
    ROUND(AVG(temperature_c), 2) AS avg_temperature_c,
    ROUND(AVG(precipitation_mm_10min), 3)
        AS avg_precipitation_mm_10min,
    ROUND(AVG(relative_humidity_pct), 2)
        AS avg_relative_humidity_pct,
    ROUND(AVG(wind_speed_kmh_10min), 2)
        AS avg_wind_speed_kmh_10min
FROM transport_weather_joined
WHERE weather_id IS NOT NULL
GROUP BY city, transport_mode
ORDER BY city, transport_mode;

-- name: delay_by_hour
SELECT
    hour,
    transport_mode,
    COUNT(*) AS observations,
    ROUND(AVG(predicted_delay_minutes), 2) AS avg_predicted_delay_min,
    ROUND(
        100.0 * AVG(
            CASE
                WHEN is_predicted_delayed_5min = 1 THEN 1.0
                ELSE 0.0
            END
        ),
        1
    ) AS delayed_5min_share_pct
FROM transport_observations
GROUP BY hour, transport_mode
ORDER BY hour, transport_mode;
