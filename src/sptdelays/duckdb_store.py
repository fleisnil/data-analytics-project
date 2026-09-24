from __future__ import annotations

import json
import uuid
from pathlib import Path

import duckdb

from .database import (
    STATION_SCHEMA,
    WEATHER_SCHEMA,
    normalized_tables,
    observation_schema,
    storage_audit,
)
from .settings import PATHS


def build_duckdb() -> Path:
    tables = normalized_tables(PATHS.processed / "model_data.csv")
    PATHS.database.mkdir(parents=True, exist_ok=True)
    PATHS.tables.mkdir(parents=True, exist_ok=True)
    database_path = PATHS.database / "sptdelays.duckdb"
    staging = PATHS.database / f"sptdelays_{uuid.uuid4().hex}.duckdb"
    try:
        connection = duckdb.connect(str(staging))
        try:
            # DOUBLE retains pandas float64 precision across SQLite and DuckDB.
            connection.execute((STATION_SCHEMA + WEATHER_SCHEMA).replace("REAL", "DOUBLE"))
            connection.execute(observation_schema(tables["observations"]).replace("REAL", "DOUBLE"))
            for name, frame in tables.items():
                connection.register("input_frame", frame)
                connection.execute(f"INSERT INTO {name} SELECT * FROM input_frame")
                connection.unregister("input_frame")
            connection.execute((PATHS.root / "sql" / "duckdb_analysis.sql").read_text(encoding="utf-8"))
            audit = storage_audit(connection, len(tables["observations"]))
            summary = connection.sql(
                "SELECT * FROM delay_region_mode ORDER BY mean_delay_minutes DESC"
            ).df()
            joined = connection.sql(
                "SELECT region, transport_mode, COUNT(*) AS observations, "
                "AVG(delay_minutes) AS mean_delay_minutes, AVG(precipitation) AS mean_precipitation "
                "FROM delay_weather_join GROUP BY region, transport_mode ORDER BY mean_delay_minutes DESC"
            ).df()
        finally:
            connection.close()
        staging.replace(database_path)
    finally:
        staging.unlink(missing_ok=True)
        Path(str(staging) + ".wal").unlink(missing_ok=True)
    summary.to_csv(PATHS.tables / "duckdb_region_mode_summary.csv", index=False)
    joined.to_csv(PATHS.tables / "duckdb_join_summary.csv", index=False)
    (PATHS.tables / "duckdb_storage_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(f"DuckDB database and SQL join evidence created: {database_path}")
    return database_path
