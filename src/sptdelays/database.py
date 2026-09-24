from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from .settings import PATHS

WEATHER_COLUMNS = [
    "temperature_2m", "precipitation", "wind_speed_10m", "wind_gusts_10m", "snowfall"
]
STATION_COLUMNS = [
    "station_id", "station_name", "region", "canton", "station_type", "latitude", "longitude"
]
STATION_SCHEMA = """
CREATE TABLE stations (
    station_id TEXT PRIMARY KEY NOT NULL,
    station_name TEXT, region TEXT, canton TEXT, station_type TEXT,
    latitude REAL, longitude REAL
);
"""
WEATHER_SCHEMA = """
CREATE TABLE weather_hourly (
    station_id TEXT NOT NULL REFERENCES stations(station_id),
    observation_hour TEXT NOT NULL,
    temperature_2m REAL, precipitation REAL, wind_speed_10m REAL,
    wind_gusts_10m REAL, snowfall REAL,
    PRIMARY KEY (station_id, observation_hour)
);
"""


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


def normalized_tables(data_path: Path) -> dict[str, pd.DataFrame]:
    """Use exactly the same validated analysis population for every SQL engine."""
    if not data_path.exists():
        raise FileNotFoundError("Run integrate before building the database.")
    data = pd.read_csv(data_path, dtype={"station_id": "string"})
    required = {
        *STATION_COLUMNS, "observation_id", "observation_hour", "transport_mode",
        "delay_minutes", "is_delayed_5", "scheduled_hour",
    }
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Integrated data is missing columns: {sorted(missing)}")
    if data.empty:
        raise ValueError("Integrated data has no observations; database was not replaced.")
    for key in ["station_id", "observation_id", "observation_hour"]:
        if data[key].isna().any() or data[key].astype(str).str.strip().eq("").any():
            raise ValueError(f"Missing database key: {key}")
    if data["observation_id"].duplicated().any():
        raise ValueError("Duplicate observation_id values; run preparation before storage.")

    # Repeated dimension rows are expected. Arbitrarily keeping conflicting rows
    # would conceal an integration error.
    stations = data[STATION_COLUMNS].drop_duplicates()
    if stations["station_id"].duplicated().any():
        raise ValueError("Conflicting station metadata for the same station_id.")
    for column in WEATHER_COLUMNS:
        if column not in data:
            data[column] = float("nan")
    weather = data[["station_id", "observation_hour", *WEATHER_COLUMNS]].drop_duplicates()
    if weather.duplicated(["station_id", "observation_hour"]).any():
        raise ValueError("Conflicting weather values for the same station-hour key.")
    # An unmatched left-join row is not evidence of a weather observation.
    weather = weather.loc[weather[WEATHER_COLUMNS].notna().any(axis=1)].copy()
    excluded = {*STATION_COLUMNS[1:], *WEATHER_COLUMNS, "station_name_weather"}
    observations = data.drop(columns=[column for column in excluded if column in data])
    return {"stations": stations, "weather_hourly": weather, "observations": observations}


def observation_schema(observations: pd.DataFrame) -> str:
    columns = []
    for name, series in observations.items():
        if not isinstance(name, str) or not name.replace("_", "").isalnum():
            raise ValueError(f"Invalid SQL column name: {name!r}")
        sql_type = "TEXT"
        if pd.api.types.is_bool_dtype(series) or pd.api.types.is_integer_dtype(series):
            sql_type = "INTEGER"
        elif pd.api.types.is_numeric_dtype(series):
            sql_type = "REAL"
        constraints = ""
        if name == "observation_id":
            constraints = " PRIMARY KEY NOT NULL"
        elif name == "station_id":
            sql_type = "TEXT"
            constraints = " NOT NULL REFERENCES stations(station_id)"
        elif name == "observation_hour":
            constraints = " NOT NULL"
        columns.append(f'"{name}" {sql_type}{constraints}')
    return "CREATE TABLE observations (" + ", ".join(columns) + ");"


def storage_audit(connection, expected_rows: int) -> dict:
    """Validate full joins, not just the limited example query exported for slides."""
    count, distinct_ids, unmatched = connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT o.observation_id), "
        "COALESCE(SUM(CASE WHEN w.station_id IS NULL THEN 1 ELSE 0 END), 0) "
        "FROM observations o JOIN stations s ON o.station_id = s.station_id "
        "LEFT JOIN weather_hourly w ON o.station_id = w.station_id "
        "AND o.observation_hour = w.observation_hour"
    ).fetchone()
    if count != expected_rows or distinct_ids != expected_rows:
        raise ValueError("SQL join changed the observation population or duplicated keys.")
    return {
        "source": "data/processed/model_data.csv",
        "input_observations": expected_rows,
        "joined_observations": count,
        "unique_joined_observations": distinct_ids,
        "row_gain_or_loss": count - expected_rows,
        "observations_without_weather_values": unmatched,
        "primary_and_foreign_keys_enforced": True,
    }


def build_sqlite() -> Path:
    tables = normalized_tables(PATHS.processed / "model_data.csv")
    PATHS.database.mkdir(parents=True, exist_ok=True)
    PATHS.tables.mkdir(parents=True, exist_ok=True)
    db_path = PATHS.database / "sptdelays.sqlite"
    # A failed build must preserve the previous database.
    with tempfile.NamedTemporaryFile(dir=PATHS.database, suffix=".sqlite", delete=False) as handle:
        staging = Path(handle.name)
    try:
        connection = sqlite3.connect(staging)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(STATION_SCHEMA + WEATHER_SCHEMA)
            connection.execute(observation_schema(tables["observations"]))
            for name, frame in tables.items():
                frame.to_sql(name, connection, index=False, if_exists="append")
            connection.executescript(
                "CREATE INDEX idx_observation_station_hour "
                "ON observations(station_id, observation_hour);"
                "CREATE INDEX idx_observation_mode_station "
                "ON observations(transport_mode, station_id);"
            )
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("SQLite foreign-key validation failed.")
            audit = storage_audit(connection, len(tables["observations"]))
            queries = _parse_named_queries(PATHS.root / "sql" / "sqlite_analysis.sql")
            results = {name: pd.read_sql_query(query, connection) for name, query in queries.items()}
            connection.commit()
        finally:
            connection.close()
        staging.replace(db_path)
    finally:
        staging.unlink(missing_ok=True)
    for name, result in results.items():
        result.to_csv(PATHS.tables / f"sqlite_{name}.csv", index=False)
        print(f"SQL query {name}: {len(result):,} result rows")
    (PATHS.tables / "sqlite_storage_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(f"SQLite database created: {db_path}")
    return db_path
