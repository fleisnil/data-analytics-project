-- name: row_counts
SELECT 'transport_observations' AS table_name, COUNT(*) AS row_count FROM transport_observations
UNION ALL SELECT 'weather_observations', COUNT(*) FROM weather_observations
UNION ALL SELECT 'stations', COUNT(*) FROM stations
UNION ALL SELECT 'transport_weather_duckdb', COUNT(*) FROM transport_weather_duckdb
ORDER BY table_name;

-- name: delay_by_city_mode
SELECT city, transport_mode, COUNT(*) AS observations,
       ROUND(AVG(predicted_delay_minutes),3) AS avg_delay_min,
       ROUND(100.0 * AVG(CASE WHEN predicted_delay_minutes >= 5 THEN 1 ELSE 0 END),2) AS delayed_5min_share_pct
FROM transport_observations
GROUP BY city, transport_mode
ORDER BY city, transport_mode;

-- name: weather_join_quality
SELECT city, COUNT(*) AS transport_rows, COUNT(weather_id) AS weather_matched_rows,
       ROUND(100.0 * COUNT(weather_id)/COUNT(*),2) AS weather_match_rate_pct,
       ROUND(AVG(weather_time_gap_minutes),2) AS avg_weather_gap_minutes,
       MAX(weather_time_gap_minutes) AS max_weather_gap_minutes
FROM transport_weather_duckdb
GROUP BY city ORDER BY city;

-- name: weather_delay_summary
SELECT transport_mode, COUNT(*) AS observations,
       ROUND(AVG(predicted_delay_minutes),3) AS avg_delay_min,
       ROUND(AVG(temperature_c),2) AS avg_temperature_c,
       ROUND(AVG(precipitation_mm_10min),3) AS avg_precipitation_mm_10min,
       ROUND(AVG(wind_speed_kmh_10min),2) AS avg_wind_speed_kmh
FROM transport_weather_duckdb
WHERE weather_id IS NOT NULL
GROUP BY transport_mode ORDER BY transport_mode;
