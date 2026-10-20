CREATE OR REPLACE VIEW transport_weather_duckdb AS
SELECT
    t.*,
    w.weather_id,
    w.weather_station_abbr,
    w.weather_station_name,
    w.reference_timestamp,
    w.temperature_c,
    w.precipitation_mm_10min,
    w.relative_humidity_pct,
    w.wind_speed_kmh_10min,
    w.wind_gust_kmh,
    w.station_pressure_hpa,
    date_diff('minute', w.reference_timestamp, t.collection_timestamp)
      AS weather_time_gap_minutes
FROM transport_observations AS t
LEFT JOIN LATERAL (
    SELECT *
    FROM weather_observations AS candidate
    WHERE candidate.city = t.city
      AND candidate.reference_timestamp <= t.collection_timestamp
      AND candidate.reference_timestamp >= t.collection_timestamp - INTERVAL '30 minutes'
    ORDER BY candidate.reference_timestamp DESC
    LIMIT 1
) AS w ON TRUE;
