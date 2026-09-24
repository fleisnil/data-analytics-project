from __future__ import annotations

import argparse
import importlib


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
    subparsers.add_parser("validate", help="Check data integrity and study coverage")
    pipeline = subparsers.add_parser("pipeline", help="Rebuild results using saved data (no API calls)")
    pipeline.add_argument("--source", choices=["live", "actuals"], default="live")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    commands = {
        "collect-live": ("collect_live", "collect_live"),
        "status": ("status", "print_collection_status"),
        "resolve-stations": ("collect_stations", "resolve_stations"),
        "list-actuals": ("collect_actuals", "list_resources"),
        "collect-actuals": ("collect_actuals", "collect_actuals"),
        "collect-weather": ("collect_weather", "collect_weather"),
        "prepare": ("prepare", "prepare_transport"),
        "integrate": ("prepare", "integrate_weather"),
        "sqlite": ("database", "build_sqlite"),
        "duckdb": ("duckdb_store", "build_duckdb"),
        "analyse": ("eda", "run_eda"),
        "model": ("modeling", "run_models"),
        "cluster": ("clustering", "run_clustering"),
        "map": ("geo", "create_map"),
        "postgres": ("postgres", "load_postgres"),
        "validate": ("quality", "run_quality_audit"),
        "pipeline": ("pipeline", "run_pipeline"),
    }
    module, function_name = commands[args.command]
    function = getattr(importlib.import_module(f"sptdelays.{module}"), function_name)
    arguments = ([args.dates] if args.command == "collect-actuals" else
                 [args.source] if args.command in {"prepare", "pipeline"} else [])
    result = function(*arguments)
    if args.command == "validate" and result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
