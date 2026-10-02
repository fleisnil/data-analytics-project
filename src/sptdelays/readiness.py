"""Read-only input checks: no API requests, directory creation or data replacement."""

from __future__ import annotations

from pathlib import Path

from .settings import PATHS, ProjectPaths


def inspect_readiness(paths: ProjectPaths, source: str = "live") -> dict:
    if source not in {"live", "actuals"}:
        raise ValueError("source must be live or actuals")
    if source == "live":
        legacy = paths.interim / "live_observations.csv"
        transport = ([legacy] if legacy.exists() else []) + sorted(
            (paths.interim / "live_snapshots").glob("stationboards_*.csv")
        )
        transport_hint = "Restore group-collected live data or run sptdelays collect-live explicitly."
    else:
        transport = sorted((paths.raw / "actuals_v2").glob("*_selected_stations.csv"))
        transport_hint = "Restore selected Actual data files or use collect-actuals --dates YYYY-MM-DD."
    resolved = paths.interim / "stations_resolved.csv"
    station_panel = resolved if resolved.exists() else paths.config / "stations.csv"
    groups = [
        ("Study settings", [paths.config / "study.json"], "Restore config/study.json from Git."),
        ("Station panel", [station_panel], "Restore config/stations.csv or resolved station data."),
        ("Transport inputs", transport, transport_hint),
        ("Weather inputs", [paths.interim / "weather_hourly.csv"],
         f"Restore saved weather or run sptdelays prepare --source {source}, then collect-weather explicitly."),
    ]
    checks = []
    for label, files, hint in groups:
        problems = [] if files else ["No matching files found"]
        for path in files:
            try:
                if not path.is_file() or path.stat().st_size == 0:
                    problems.append(f"Missing or empty file: {path.relative_to(paths.root)}")
                else:
                    with path.open("rb") as handle:
                        handle.read(1)
            except OSError as exc:
                problems.append(f"Cannot read {path.relative_to(paths.root)}: {exc}")
        checks.append({"name": label, "ready": not problems, "files": len(files),
                       "problems": problems, "next_step": hint})
    return {"ready": all(check["ready"] for check in checks), "source": source,
            "checks": checks, "transport_inputs": transport}


def require_pipeline_inputs(paths: ProjectPaths, source: str) -> list[Path]:
    report = inspect_readiness(paths, source)
    missing = [check for check in report["checks"] if not check["ready"]]
    if missing:
        details = "\n".join(
            f"- {check['name']}: {'; '.join(check['problems'])}. {check['next_step']}"
            for check in missing
        )
        raise FileNotFoundError(f"Analysis cannot start yet:\n{details}")
    return report["transport_inputs"]


def print_readiness(source: str = "live") -> dict:
    report = inspect_readiness(PATHS, source)
    print(f"Input readiness ({source}) - no data collected or changed")
    for check in report["checks"]:
        print(f"[{'OK' if check['ready'] else 'MISSING'}] {check['name']}: {check['files']} file(s)")
        for problem in check["problems"]:
            print(f"  {problem}")
        if not check["ready"]:
            print(f"  Next: {check['next_step']}")
    print("Inputs present; Analyse starten can now check and process their contents."
          if report["ready"] else "Restore or collect the missing inputs before Analyse starten.")
    print("File presence is not proof of data quality or final study coverage. "
          "After analysis, run Ergebnisse pruefen / sptdelays validate.")
    return report
