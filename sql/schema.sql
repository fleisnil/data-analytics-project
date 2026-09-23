-- SQLite schema additions for the Swiss Public Transport Delays project.
--
-- Python/pandas writes the three base tables first. This script then adds
-- indexes and the SQL integration view used for analysis.

DROP VIEW IF EXISTS transport_weather_joined;

CREATE UNIQUE INDEX IF NOT EXISTS idx_transport_id
    ON transport_observations(transport_id);

CREATE INDEX IF NOT EXISTS idx_transport_city_time
    ON transport_observations(city, collection_timestamp);

CREATE INDEX IF NOT EXISTS idx_transport_mode
    ON transport_observations(transport_mode);

CREATE UNIQUE INDEX IF NOT EXISTS idx_weather_id
    ON weather_observations(weather_id);

CREATE INDEX IF NOT EXISTS idx_weather_city_time
    ON weather_observations(city, reference_timestamp);

CREATE UNIQUE INDEX IF NOT EXISTS idx_station_key
    ON stations(station_key);

CREATE INDEX IF NOT EXISTS idx_stations_city_source
    ON stations(city, source);

-- Real SQL join between the two independently collected data sources.
-- For every OJP observation, select the newest MeteoSwiss observation in the
-- same city that is not from the future and is no more than 30 minutes old.
CREATE VIEW transport_weather_joined AS
SELECT
    t.*,
    w.weather_id,
    w.weather_station_abbr,
    w.weather_station_name,
    w.reference_timestamp AS weather_reference_timestamp,
    w.temperature_c,
    w.precipitation_mm_10min,
    w.relative_humidity_pct,
    w.wind_speed_kmh_10min,
    w.wind_gust_kmh,
    w.station_pressure_hpa,
    ROUND(
        (
            julianday(t.collection_timestamp)
            - julianday(w.reference_timestamp)
        ) * 24.0 * 60.0,
        2
    ) AS weather_time_gap_minutes
FROM transport_observations AS t
LEFT JOIN weather_observations AS w
    ON w.weather_id = (
        SELECT w2.weather_id
        FROM weather_observations AS w2
        WHERE w2.city = t.city
          AND w2.reference_timestamp <= t.collection_timestamp
          AND (
              julianday(t.collection_timestamp)
              - julianday(w2.reference_timestamp)
          ) * 24.0 * 60.0 <= 30.0
        ORDER BY w2.reference_timestamp DESC
        LIMIT 1
    );
