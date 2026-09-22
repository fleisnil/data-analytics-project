from __future__ import annotations

import argparse

from .clustering import run_clustering
from .collect_actuals import collect_actuals, list_resources
from .collect_live import collect_live
from .collect_stations import resolve_stations
from .collect_weather import collect_weather
from .database import build_sqlite
from .duckdb_store import build_duckdb
from .eda import run_eda
from .geo import create_map
from .modeling import run_models
from .postgres import load_postgres
from .prepare import integrate_weather, prepare_transport
from .status import print_collection_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Swiss public transport delay analytics")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("collect-live", help="Collect a timestamped stationboard snapshot")
    subparsers.add_parser("status", help="Show progress and failures in the live collection")
    subparsers.add_parser("resolve-stations", help="Resolve station IDs and coordinates from the locations API")
    subparsers.add_parser("list-actuals", help="List official Actual data v2 dates")
    actuals = subparsers.add_parser("collect-actuals", help="Stream selected official daily Actual data files")
    actuals.add_argument("--dates", nargs="+", required=True, help="YYYY-MM-DD dates")
    prepare = subparsers.add_parser("prepare", help="Prepare transport records")
    prepare.add_argument("--source", choices=["live", "actuals"], default="live")
    subparsers.add_parser("collect-weather", help="Collect station-hour weather")
    subparsers.add_parser("integrate", help="Join prepared transport and weather")
    subparsers.add_parser("sqlite", help="Build SQLite and execute SQL queries")
    subparsers.add_parser("duckdb", help="Build DuckDB and execute SQL joins and aggregations")
    subparsers.add_parser("analyse", help="Run EDA and statistical tests")
    subparsers.add_parser("model", help="Fit and evaluate regression models")
    subparsers.add_parser("cluster", help="Cluster station profiles using k-means")
    subparsers.add_parser("map", help="Create the interactive station map")
    subparsers.add_parser("postgres", help="Load the processed dataset into PostgreSQL")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    commands = {
        "collect-live": collect_live,
        "status": print_collection_status,
        "resolve-stations": resolve_stations,
        "list-actuals": list_resources,
        "collect-weather": collect_weather,
        "integrate": integrate_weather,
        "sqlite": build_sqlite,
        "duckdb": build_duckdb,
        "analyse": run_eda,
        "model": run_models,
        "cluster": run_clustering,
        "map": create_map,
        "postgres": load_postgres,
    }
    if args.command == "collect-actuals":
        collect_actuals(args.dates)
    elif args.command == "prepare":
        prepare_transport(args.source)
    else:
        commands[args.command]()


if __name__ == "__main__":
    main()
