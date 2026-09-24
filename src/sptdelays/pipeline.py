"""Rebuild results from saved inputs and record which inputs produced them."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from .settings import PATHS, load_settings


def fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def run_pipeline(source: str = "live") -> dict:
    PATHS.ensure()
    settings = load_settings()
    inputs = [PATHS.interim / "weather_hourly.csv"]
    if source == "live":
        legacy = PATHS.interim / "live_observations.csv"
        live_inputs = ([legacy] if legacy.exists() else []) + sorted(
            (PATHS.interim / "live_snapshots").glob("stationboards_*.csv")
        )
        if not live_inputs:
            raise FileNotFoundError("No saved live observations exist. Run collect-live first.")
        inputs.extend(live_inputs)
    elif source == "actuals":
        actuals = sorted((PATHS.raw / "actuals_v2").glob("*_selected_stations.csv"))
        if not actuals:
            raise FileNotFoundError("No selected Actual data v2 files exist.")
        inputs.extend(actuals)
    else:
        raise ValueError("source must be live or actuals")
    for path in inputs:
        if not path.exists():
            raise FileNotFoundError(f"Missing input: {path}. Collect data before running pipeline.")
    inputs.extend(PATHS.config.glob("*.json"))
    inputs.extend(PATHS.config.glob("*.csv"))
    inputs.extend(PATHS.interim.glob("stations_resolved.csv"))
    inputs.extend(PATHS.interim.glob("collection_log.csv"))
    versions = {name: importlib.metadata.version(name) for name in
                ["pandas", "numpy", "scikit-learn", "statsmodels", "scipy", "duckdb"]}
    manifest = {
        "started_at_utc": datetime.now(UTC).isoformat(), "status": "running", "source": source,
        "python": platform.python_version(), "versions": versions, "settings": settings,
        "inputs": {str(p.relative_to(PATHS.root)).replace("\\", "/"): fingerprint(p)
                   for p in inputs},
        "code": {str(p.relative_to(PATHS.root)).replace("\\", "/"): fingerprint(p)
                 for p in sorted((PATHS.root / "src" / "sptdelays").glob("*.py"))},
        "steps": [],
    }
    manifest_path = PATHS.tables / "run_manifest.json"

    def save_manifest() -> None:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    steps = [("prepare", "prepare_transport", [source]), ("prepare", "integrate_weather", []),
             ("quality", "run_quality_audit", []), ("database", "build_sqlite", []),
             ("duckdb_store", "build_duckdb", []), ("eda", "run_eda", []),
             ("modeling", "run_models", []), ("clustering", "run_clustering", []),
             ("geo", "create_map", [])]
    save_manifest()
    for module_name, function_name, arguments in steps:
        started = perf_counter()
        step = {"step": function_name, "status": "running"}
        manifest["steps"].append(step)
        save_manifest()
        try:
            function = getattr(importlib.import_module(f"sptdelays.{module_name}"), function_name)
            result = function(*arguments)
            if function_name == "run_quality_audit":
                manifest["data_status"] = result["status"]
                if result["errors"]:
                    raise ValueError("Structural data checks failed; inspect quality_checks.csv.")
            step["status"] = "completed"
        except Exception as exc:
            step.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            manifest["status"] = "failed"
            raise
        finally:
            step["seconds"] = round(perf_counter() - started, 3)
            save_manifest()
    manifest["outputs"] = {"data/processed/model_data.csv": fingerprint(
        PATHS.processed / "model_data.csv"
    )}
    manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
    manifest["status"] = "completed"
    save_manifest()
    print(f"Offline pipeline completed ({manifest['data_status']}). "
          "Inputs, settings and stage results: reports/tables/run_manifest.json")
    return manifest
