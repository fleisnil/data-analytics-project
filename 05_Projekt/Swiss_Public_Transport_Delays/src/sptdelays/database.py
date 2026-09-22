from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .settings import PATHS

WEATHER_COLUMNS = [
    "temperature_2m", "precipitation", "wind_speed_10m", "wind_gusts_10m", "snowfall"
]


def _parse_named_queries(path: Path) -> dict[str, str]:
    queries: dict[str, list[str]] = {}
    current = "query"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- name:"):
            current = line.split(":", 1)[1].strip()
            queries[current] = []
        elif current in queries:
            queries[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in queries.items() if "".join(lines).strip()}


def build_sqlite() -> Path:
    data_path = PATHS.processed / "model_data.csv"
    if not data_path.exists():
        raise FileNotFoundError("Run integrate before building the database.")
    data = pd.read_csv(data_path, dtype={"station_id": "string"})
    stations = (
        data[["station_id", "station_name", "region", "canton", "station_type", "latitude", "longitude"]]
        .drop_duplicates("station_id")
    )
    weather_cols = [col for col in WEATHER_COLUMNS if col in data]
    weather = data[["station_id", "observation_hour", *weather_cols]].drop_duplicates(
        ["station_id", "observation_hour"]
    )
    observation_cols = [
        "observation_id", "data_source", "station_id", "journey_id", "operator",
        "transport_mode", "category_raw", "line", "destination", "scheduled_time",
        "reported_time", "observation_hour", "delay_minutes_signed", "delay_minutes",
        "is_delayed_5", "cancelled", "event_type", "reported_status", "service_date",
        "scheduled_hour", "weekday", "is_weekend", "is_peak", "day_period",
    ]
    observations = data[[col for col in observation_cols if col in data]].copy()
    db_path = PATHS.database / "sptdelays.sqlite"
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as connection:
        stations.to_sql("stations", connection, index=False, if_exists="replace")
        weather.to_sql("weather_hourly", connection, index=False, if_exists="replace")
        observations.to_sql("observations", connection, index=False, if_exists="replace")
        connection.executescript(
            """
            CREATE UNIQUE INDEX idx_stations_id ON stations(station_id);
            CREATE UNIQUE INDEX idx_weather_key ON weather_hourly(station_id, observation_hour);
            CREATE UNIQUE INDEX idx_observation_id ON observations(observation_id);
            CREATE INDEX idx_observation_station_hour ON observations(station_id, observation_hour);
            CREATE INDEX idx_observation_mode_region ON observations(transport_mode, station_id);
            """
        )
        queries = _parse_named_queries(PATHS.root / "sql" / "sqlite_analysis.sql")
        for name, query in queries.items():
            result = pd.read_sql_query(query, connection)
            result.to_csv(PATHS.tables / f"sqlite_{name}.csv", index=False)
            print(f"SQL query {name}: {len(result):,} result rows")
    print(f"SQLite database created: {db_path}")
    return db_path

