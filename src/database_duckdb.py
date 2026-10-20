#!/usr/bin/env python3
from pathlib import Path
from typing import Dict
import duckdb
import pandas as pd

from build_dataset import load_ojp_snapshots, load_weather_measurements, select_transport_observations
from database import TRANSPORT_COLUMNS, WEATHER_COLUMNS, build_station_table, load_named_queries

DATABASE_PATH=Path("data/database/transport_weather.duckdb")
SCHEMA_PATH=Path("sql/duckdb_schema.sql")
QUERIES_PATH=Path("sql/duckdb_analysis_queries.sql")
RESULTS_DIR=Path("results/tables")

def _utc_naive(series):
    return pd.to_datetime(series,utc=True,errors="coerce").dt.tz_convert(None)

def prepare_transport(df):
    missing=[c for c in TRANSPORT_COLUMNS if c not in df.columns]
    if missing: raise ValueError(f"Transport data missing required columns: {missing}")
    out=df[TRANSPORT_COLUMNS].copy()
    for c in ["collection_timestamp","scheduled_departure","estimated_departure"]:
        out[c]=_utc_naive(out[c])
    out.insert(0,"transport_id",range(1,len(out)+1))
    return out

def prepare_weather(df):
    missing=[c for c in WEATHER_COLUMNS if c not in df.columns]
    if missing: raise ValueError(f"Weather data missing required columns: {missing}")
    out=df[WEATHER_COLUMNS].copy()
    out["reference_timestamp"]=_utc_naive(out["reference_timestamp"])
    out.insert(0,"weather_id",range(1,len(out)+1))
    return out

def create_database(transport,weather,database_path=DATABASE_PATH,schema_path=SCHEMA_PATH):
    if not schema_path.exists(): raise FileNotFoundError(f"Missing {schema_path}")
    database_path.parent.mkdir(parents=True,exist_ok=True)
    if database_path.exists(): database_path.unlink()
    t=prepare_transport(transport); w=prepare_weather(weather); s=build_station_table(t,w)
    con=duckdb.connect(str(database_path))
    try:
        con.register("_transport_df",t); con.register("_weather_df",w); con.register("_stations_df",s)
        con.execute("CREATE TABLE transport_observations AS SELECT * FROM _transport_df")
        con.execute("CREATE TABLE weather_observations AS SELECT * FROM _weather_df")
        con.execute("CREATE TABLE stations AS SELECT * FROM _stations_df")
        con.execute(schema_path.read_text(encoding="utf-8"))
    finally:
        con.close()

def validate_database(database_path=DATABASE_PATH):
    con=duckdb.connect(str(database_path),read_only=True)
    try:
        transport_rows=con.execute("SELECT COUNT(*) FROM transport_observations").fetchone()[0]
        weather_rows=con.execute("SELECT COUNT(*) FROM weather_observations").fetchone()[0]
        joined_rows=con.execute("SELECT COUNT(*) FROM transport_weather_duckdb").fetchone()[0]
        matched_rows=con.execute("SELECT COUNT(*) FROM transport_weather_duckdb WHERE weather_id IS NOT NULL").fetchone()[0]
        future=con.execute("SELECT COUNT(*) FROM transport_weather_duckdb WHERE reference_timestamp > collection_timestamp").fetchone()[0]
        too_old=con.execute("SELECT COUNT(*) FROM transport_weather_duckdb WHERE weather_time_gap_minutes > 30").fetchone()[0]
    finally:
        con.close()
    if joined_rows!=transport_rows: raise RuntimeError("DuckDB join changed transport row count.")
    if future: raise RuntimeError("DuckDB join used future weather.")
    if too_old: raise RuntimeError("DuckDB join used weather older than 30 minutes.")
    return {"transport_rows":transport_rows,"weather_rows":weather_rows,"joined_rows":joined_rows,
            "weather_matched_rows":matched_rows,
            "weather_match_rate_pct":round(100*matched_rows/joined_rows,2) if joined_rows else 0.0,
            "future_weather_matches":future,"weather_matches_over_30min":too_old}

def run_analysis_queries(database_path=DATABASE_PATH,queries_path=QUERIES_PATH,results_dir=RESULTS_DIR)->Dict[str,pd.DataFrame]:
    results_dir.mkdir(parents=True,exist_ok=True)
    queries=load_named_queries(queries_path); outputs={}
    con=duckdb.connect(str(database_path),read_only=True)
    try:
        for name,sql in queries.items():
            result=con.execute(sql).fetchdf()
            outputs[name]=result
            result.to_csv(results_dir/f"duckdb_{name}.csv",index=False)
    finally:
        con.close()
    return outputs

def main():
    print("="*72); print("BUILD DUCKDB BONUS DATABASE"); print("="*72)
    transport=select_transport_observations(load_ojp_snapshots())
    weather=load_weather_measurements()
    create_database(transport,weather)
    validation=validate_database()
    print(f"\nDuckDB database: {DATABASE_PATH}")
    print("\nValidation:")
    for k,v in validation.items(): print(f"  {k}: {v}")
    outputs=run_analysis_queries()
    for name,result in outputs.items():
        print(f"\n--- {name} ({len(result)} rows) ---")
        print(result.head(20).to_string(index=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
