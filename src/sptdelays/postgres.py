from __future__ import annotations

import json
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from .database import normalized_tables, storage_audit
from .settings import PATHS


def load_postgres() -> None:
    load_dotenv(PATHS.root / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and load it first.")
    tables = normalized_tables(PATHS.processed / "model_data.csv")
    engine = create_engine(database_url, future=True)
    try:
        if engine.dialect.name != "postgresql":
            raise ValueError("DATABASE_URL must refer to a PostgreSQL database.")
        # PostgreSQL DDL is transactional: a failed load rolls back the previous tables.
        with engine.begin() as connection:
            connection.execute(text("DROP MATERIALIZED VIEW IF EXISTS delay_region_mode"))
            connection.execute(text("DROP VIEW IF EXISTS delay_weather_join"))
            for name in ["observations", "weather_hourly", "stations"]:
                connection.execute(text(f"DROP TABLE IF EXISTS {name}"))
            for name, frame in tables.items():
                frame.to_sql(
                    name, connection, index=False, if_exists="fail", chunksize=1000, method="multi"
                )
            constraints = [
                "ALTER TABLE stations ADD PRIMARY KEY (station_id)",
                "ALTER TABLE weather_hourly ADD PRIMARY KEY (station_id, observation_hour)",
                "ALTER TABLE weather_hourly ADD FOREIGN KEY (station_id) REFERENCES stations(station_id)",
                "ALTER TABLE observations ADD PRIMARY KEY (observation_id)",
                "ALTER TABLE observations ALTER COLUMN observation_hour SET NOT NULL",
                "ALTER TABLE observations ALTER COLUMN station_id SET NOT NULL",
                "ALTER TABLE observations ADD FOREIGN KEY (station_id) REFERENCES stations(station_id)",
                "CREATE INDEX idx_observation_station_hour ON observations(station_id, observation_hour)",
            ]
            for statement in constraints:
                connection.execute(text(statement))
            sql = (PATHS.root / "sql" / "postgres_analysis.sql").read_text(encoding="utf-8")
            for statement in [part.strip() for part in sql.split(";") if part.strip()]:
                connection.execute(text(statement))
            audit = storage_audit(
                connection.connection.driver_connection, len(tables["observations"])
            )
            result = pd.read_sql_query(
                text("SELECT * FROM delay_region_mode ORDER BY mean_delay_minutes DESC"), connection
            )
        PATHS.tables.mkdir(parents=True, exist_ok=True)
        result.to_csv(PATHS.tables / "postgres_region_mode_summary.csv", index=False)
        (PATHS.tables / "postgres_storage_audit.json").write_text(
            json.dumps(audit, indent=2), encoding="utf-8"
        )
        print("PostgreSQL normalized tables, SQL joins and aggregation completed.")
    finally:
        engine.dispose()
