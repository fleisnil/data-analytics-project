from __future__ import annotations

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from .settings import PATHS


def load_postgres() -> None:
    load_dotenv(PATHS.root / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and load it first.")
    data = pd.read_csv(PATHS.processed / "model_data.csv", dtype={"station_id": "string"})
    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        data.to_sql("model_data", connection, index=False, if_exists="replace", chunksize=5000, method="multi")
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_model_station_hour ON model_data(station_id, observation_hour)"))
        sql = (PATHS.root / "sql" / "postgres_analysis.sql").read_text(encoding="utf-8")
        for statement in [part.strip() for part in sql.split(";") if part.strip()]:
            connection.execute(text(statement))
        result = pd.read_sql_query(
            text("SELECT region, transport_mode, COUNT(*) AS n, AVG(delay_minutes) AS mean_delay FROM model_data GROUP BY region, transport_mode ORDER BY mean_delay DESC"),
            connection,
        )
    result.to_csv(PATHS.tables / "postgres_region_mode_summary.csv", index=False)
    print("PostgreSQL load and aggregation completed.")
