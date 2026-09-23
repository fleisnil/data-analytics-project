#!/usr/bin/env python3
"""
Build and query the project's SQLite database from the cleaned OJP and
MeteoSwiss source data.

The database is generated locally at:
    data/database/transport_weather.sqlite

Tables:
- transport_observations
- weather_observations
- stations

View:
- transport_weather_joined

The SQL view joins the two independently collected sources by city and time:
for every transport observation it selects the latest weather measurement in
the same city at or before the OJP collection timestamp, with a 30-minute
maximum gap.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

import pandas as pd

from build_dataset import (
    load_ojp_snapshots,
    load_weather_measurements,
    select_transport_observations,
)


DATABASE_DIR = Path("data/database")
DATABASE_PATH = DATABASE_DIR / "transport_weather.sqlite"
SCHEMA_PATH = Path("sql/schema.sql")
QUERIES_PATH = Path("sql/analysis_queries.sql")
RESULTS_DIR = Path("results/tables")

TRANSPORT_COLUMNS = [
    "operating_day",
    "journey_ref",
    "station_id",
    "station_name",
    "station_type",
    "city",
    "transport_mode",
    "product_category",
    "public_code",
    "line",
    "train_number",
    "origin",
    "destination",
    "collection_timestamp",
    "scheduled_departure",
    "estimated_departure",
    "predicted_delay_minutes",
    "minutes_until_departure",
    "is_predicted_delayed_5min",
    "hour",
    "weekday",
    "weekend",
]

WEATHER_COLUMNS = [
    "city",
    "weather_station_abbr",
    "weather_station_name",
    "reference_timestamp",
    "temperature_c",
    "precipitation_mm_10min",
    "relative_humidity_pct",
    "wind_speed_kmh_10min",
    "wind_gust_kmh",
    "station_pressure_hpa",
]


def _utc_text(series: pd.Series) -> pd.Series:
    """Convert timestamps to SQLite-friendly UTC text."""
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    return dt.dt.strftime("%Y-%m-%d %H:%M:%S")


def prepare_transport_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    """Select and normalize transport fields for SQLite."""
    missing = [c for c in TRANSPORT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Transport data missing required columns: {missing}")

    out = df[TRANSPORT_COLUMNS].copy()

    for column in [
        "collection_timestamp",
        "scheduled_departure",
        "estimated_departure",
    ]:
        out[column] = _utc_text(out[column])

    for column in ["is_predicted_delayed_5min", "weekend"]:
        out[column] = out[column].astype("boolean").astype("Int64")

    out.insert(0, "transport_id", range(1, len(out) + 1))
    return out


def prepare_weather_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    """Select and normalize MeteoSwiss fields for SQLite."""
    missing = [c for c in WEATHER_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Weather data missing required columns: {missing}")

    out = df[WEATHER_COLUMNS].copy()
    out["reference_timestamp"] = _utc_text(out["reference_timestamp"])
    out.insert(0, "weather_id", range(1, len(out) + 1))
    return out


def build_station_table(
    transport: pd.DataFrame,
    weather: pd.DataFrame,
) -> pd.DataFrame:
    """Create shared station metadata for both source systems."""
    transport_stations = (
        transport[
            ["city", "station_id", "station_name", "station_type"]
        ]
        .drop_duplicates()
        .rename(columns={"station_id": "source_station_id"})
    )
    transport_stations["source"] = "OJP"

    weather_stations = (
        weather[
            ["city", "weather_station_abbr", "weather_station_name"]
        ]
        .drop_duplicates()
        .rename(
            columns={
                "weather_station_abbr": "source_station_id",
                "weather_station_name": "station_name",
            }
        )
    )
    weather_stations["station_type"] = "weather"
    weather_stations["source"] = "MeteoSwiss"

    stations = pd.concat(
        [transport_stations, weather_stations],
        ignore_index=True,
    )
    stations.insert(0, "station_key", range(1, len(stations) + 1))

    return stations[
        [
            "station_key",
            "city",
            "source",
            "source_station_id",
            "station_name",
            "station_type",
        ]
    ]


def load_named_queries(path: Path) -> Dict[str, str]:
    """
    Parse SQL statements introduced by:
        -- name: query_name
    """
    if not path.exists():
        raise FileNotFoundError(f"SQL query file not found: {path}")

    queries: Dict[str, str] = {}
    current_name = None
    current_lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if stripped.lower().startswith("-- name:"):
            if current_name and current_lines:
                sql = "\n".join(current_lines).strip()
                if sql:
                    queries[current_name] = sql.rstrip(";")

            current_name = stripped.split(":", 1)[1].strip()
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)

    if current_name and current_lines:
        sql = "\n".join(current_lines).strip()
        if sql:
            queries[current_name] = sql.rstrip(";")

    if not queries:
        raise ValueError(f"No named SQL queries found in {path}")

    return queries


def create_database(
    transport: pd.DataFrame,
    weather: pd.DataFrame,
    database_path: Path = DATABASE_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> None:
    """Create/replace the SQLite database and apply the SQL schema."""
    if not schema_path.exists():
        raise FileNotFoundError(f"SQL schema file not found: {schema_path}")

    database_path.parent.mkdir(parents=True, exist_ok=True)

    transport_sql = prepare_transport_for_sql(transport)
    weather_sql = prepare_weather_for_sql(weather)
    stations_sql = build_station_table(transport_sql, weather_sql)

    if database_path.exists():
        database_path.unlink()

    with sqlite3.connect(database_path) as connection:
        transport_sql.to_sql(
            "transport_observations",
            connection,
            if_exists="replace",
            index=False,
        )
        weather_sql.to_sql(
            "weather_observations",
            connection,
            if_exists="replace",
            index=False,
        )
        stations_sql.to_sql(
            "stations",
            connection,
            if_exists="replace",
            index=False,
        )

        connection.executescript(
            schema_path.read_text(encoding="utf-8")
        )
        connection.commit()


def validate_database(database_path: Path = DATABASE_PATH) -> dict:
    """Check integrity, row counts and SQL join cardinality."""
    with sqlite3.connect(database_path) as connection:
        integrity = connection.execute(
            "PRAGMA integrity_check;"
        ).fetchone()[0]

        transport_rows = connection.execute(
            "SELECT COUNT(*) FROM transport_observations;"
        ).fetchone()[0]
        weather_rows = connection.execute(
            "SELECT COUNT(*) FROM weather_observations;"
        ).fetchone()[0]
        station_rows = connection.execute(
            "SELECT COUNT(*) FROM stations;"
        ).fetchone()[0]
        joined_rows = connection.execute(
            "SELECT COUNT(*) FROM transport_weather_joined;"
        ).fetchone()[0]
        matched_rows = connection.execute(
            """
            SELECT COUNT(*)
            FROM transport_weather_joined
            WHERE weather_id IS NOT NULL;
            """
        ).fetchone()[0]

    if integrity != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")

    if joined_rows != transport_rows:
        raise RuntimeError(
            "SQL join view changed transport row count: "
            f"{joined_rows} joined vs {transport_rows} transport."
        )

    return {
        "integrity_check": integrity,
        "transport_rows": transport_rows,
        "weather_rows": weather_rows,
        "station_rows": station_rows,
        "joined_rows": joined_rows,
        "weather_matched_rows": matched_rows,
        "weather_match_rate_pct": (
            round(100 * matched_rows / joined_rows, 2)
            if joined_rows
            else 0.0
        ),
    }


def run_analysis_queries(
    database_path: Path = DATABASE_PATH,
    queries_path: Path = QUERIES_PATH,
    results_dir: Path = RESULTS_DIR,
) -> Dict[str, pd.DataFrame]:
    """Execute the documented SQL queries from Python."""
    results_dir.mkdir(parents=True, exist_ok=True)
    queries = load_named_queries(queries_path)
    outputs: Dict[str, pd.DataFrame] = {}

    with sqlite3.connect(database_path) as connection:
        for name, sql in queries.items():
            result = pd.read_sql_query(sql, connection)
            outputs[name] = result
            result.to_csv(
                results_dir / f"sql_{name}.csv",
                index=False,
            )

    return outputs


def main() -> int:
    print("=" * 72)
    print("BUILD SQLITE DATABASE")
    print("=" * 72)

    ojp_raw = load_ojp_snapshots()
    transport = select_transport_observations(ojp_raw)
    weather = load_weather_measurements()

    print(f"Selected transport observations: {len(transport)}")
    print(f"Unique weather observations: {len(weather)}")

    create_database(
        transport=transport,
        weather=weather,
    )

    validation = validate_database()

    print(f"\nSQLite database: {DATABASE_PATH}")
    print("\nValidation:")
    for key, value in validation.items():
        print(f"  {key}: {value}")

    print("\nSQL analysis queries:")
    query_results = run_analysis_queries()

    for name, result in query_results.items():
        print(f"\n--- {name} ({len(result)} rows) ---")
        print(result.head(20).to_string(index=False))

    print("\nSaved SQL result tables in results/tables/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
