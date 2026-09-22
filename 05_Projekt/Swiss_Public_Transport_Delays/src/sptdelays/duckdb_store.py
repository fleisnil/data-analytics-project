from __future__ import annotations

from pathlib import Path

import duckdb

from .settings import PATHS


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''").replace("\\", "/")


def build_duckdb() -> Path:
    observations = PATHS.interim / "transport_prepared.csv"
    weather = PATHS.interim / "weather_hourly.csv"
    stations = PATHS.interim / "stations_resolved.csv"
    for source in [observations, weather, stations]:
        if not source.exists():
            raise FileNotFoundError(f"Required input does not exist: {source}")
    database_path = PATHS.database / "sptdelays.duckdb"
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(
            f"CREATE OR REPLACE TABLE observations AS SELECT * FROM read_csv_auto('{_sql_path(observations)}')"
        )
        connection.execute(
            f"CREATE OR REPLACE TABLE weather_hourly AS SELECT * FROM read_csv_auto('{_sql_path(weather)}')"
        )
        connection.execute(
            f"CREATE OR REPLACE TABLE stations AS SELECT * FROM read_csv_auto('{_sql_path(stations)}')"
        )
        sql = (PATHS.root / "sql" / "duckdb_analysis.sql").read_text(encoding="utf-8")
        connection.execute(sql)
        connection.sql("SELECT * FROM delay_region_mode ORDER BY mean_delay_minutes DESC").df().to_csv(
            PATHS.tables / "duckdb_region_mode_summary.csv", index=False
        )
        connection.sql(
            "SELECT region, transport_mode, COUNT(*) AS observations, "
            "AVG(delay_minutes) AS mean_delay_minutes, AVG(precipitation) AS mean_precipitation "
            "FROM delay_weather_join GROUP BY region, transport_mode ORDER BY mean_delay_minutes DESC"
        ).df().to_csv(PATHS.tables / "duckdb_join_summary.csv", index=False)
    finally:
        connection.close()
    print(f"DuckDB database and SQL join evidence created: {database_path}")
    return database_path

