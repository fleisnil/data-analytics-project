"""Explicit, reproducible VS Code actions for the existing main-branch pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

if __package__:
    from .analysis_summary import build_summary
else:
    from analysis_summary import build_summary

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("results/run_manifest.json")
SUMMARY = Path("results/analysis_summary.md")
STAGES = (
    "build_dataset", "database", "database_duckdb", "eda", "statistics_analysis",
    "model_regression", "clustering", "geographic_analysis", "final_results",
)
REQUIRED_OUTPUTS = (
    "data/processed/analysis_dataset.csv", "data/database/transport_weather.sqlite",
    "data/database/transport_weather.duckdb", "results/tables/data_integration_report.csv",
    "results/tables/model_temporal_validation.csv", "results/tables/model_paired_comparisons.csv",
    "results/tables/model_holdout_benchmarks.csv", "results/tables/model_holdout_coverage.csv",
    "results/tables/model_metrics_by_day_period.csv",
    "results/model/final_results_summary.md",
)


def input_groups(root: Path) -> dict[str, list[Path]]:
    return {
        "OJP snapshots": sorted((root / "data/interim/ojp_snapshots").glob("ojp_snapshot_*.csv")),
        "MeteoSwiss weather": sorted([
            *(root / "data/interim/weather_snapshots").glob("weather_snapshot_*.csv"),
            *(root / "data/raw/weather").glob("*/*.csv"),
        ]),
        "SQL and geographic reference": [
            root / "sql/schema.sql", root / "sql/analysis_queries.sql",
            root / "sql/duckdb_schema.sql", root / "sql/duckdb_analysis_queries.sql",
            root / "data/reference/hub_coordinates.csv",
        ],
    }


def doctor(root: Path) -> bool:
    print("Checking local files only; no data collected or changed.", flush=True)
    ready = True
    for name, files in input_groups(root).items():
        problems = []
        for file in files:
            try:
                with file.open("rb") as handle:
                    if not handle.read(1):
                        problems.append(f"{file.relative_to(root)} is empty")
            except OSError:
                problems.append(f"{file.relative_to(root)} is missing or unreadable")
        if not files or problems:
            ready = False
            print(f"[MISSING] {name}: {'; '.join(problems) or 'no matching files'}")
        else:
            print(f"[OK] {name}: {len(files)} file(s)")
    if not ready:
        print("Use 'Daten von GitHub holen' for the archived data; restore missing SQL/reference files from Git.")
    return ready


@contextmanager
def workflow_lock(root: Path):
    lock = root / "results/.workflow.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        if not handle.seek(0, os.SEEK_END):
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another analysis or archive sync is running. Wait and retry.") from exc
        # Closing the descriptor releases the OS lock, also after interruptions.
        yield


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fingerprints(root: Path, paths: list[Path]) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(set(paths))}


def input_fingerprints(root: Path) -> dict[str, str]:
    paths = [file for files in input_groups(root).values() for file in files]
    manifest = root / "data/collection_manifest.csv"
    if manifest.is_file():
        paths.append(manifest)
    return fingerprints(root, paths)


def code_fingerprints(root: Path) -> dict[str, str]:
    return fingerprints(root, [
        *(root / "src").glob("*.py"), root / "pyproject.toml", root / "uv.lock",
    ])


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".workflow-", dir=path.parent) as temporary:
        new = Path(temporary) / path.name
        new.write_text(value, encoding="utf-8")
        new.replace(path)


def write_manifest(root: Path, manifest: dict) -> None:
    atomic_text(root / MANIFEST, json.dumps(manifest, indent=2) + "\n")


def run_child(root: Path, *args: str) -> None:
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONUTF8": "1"}
    subprocess.run([sys.executable, *args], cwd=root, env=env, check=True)


def result_files(root: Path) -> list[Path]:
    return sorted({
        *(root / "results/figures").glob("*.png"),
        *(root / "results/tables").glob("*.csv"),
        *(root / "results/model").glob("*.csv"),
        *(root / "results/model").glob("*.joblib"),
        *(root / "results/model").glob("*.md"),
        *(root / relative for relative in REQUIRED_OUTPUTS),
    } - {root / SUMMARY})


def file_stamp(path: Path) -> tuple[int, int] | None:
    if not path.is_file():
        return None
    st = path.stat()
    return st.st_mtime_ns, st.st_size


def write_summary(root: Path, figures: list[Path], generated: str) -> None:
    atomic_text(root / SUMMARY, build_summary(root, figures, generated))


def run_pipeline(root: Path) -> None:
    if not doctor(root):
        raise RuntimeError("Cannot start: missing local inputs. Existing results were left untouched.")
    with workflow_lock(root):
        old_outputs = {file: file_stamp(file) for file in result_files(root)}
        manifest = {
            "schema_version": 1, "status": "running", "started_utc": datetime.now(UTC).isoformat(),
            "inputs": input_fingerprints(root), "code": code_fingerprints(root),
            "python": sys.version, "packages": {
                name: version(name) for name in ("pandas", "numpy", "scikit-learn", "duckdb", "scipy")
            }, "stages": {},
        }
        write_manifest(root, manifest)
        try:
            for stage in STAGES:
                print(f"\n--- {stage} ---", flush=True)
                manifest["stages"][stage] = "running"
                write_manifest(root, manifest)
                try:
                    run_child(root, f"src/{stage}.py")
                except (Exception, KeyboardInterrupt):
                    manifest["stages"][stage] = "failed"
                    raise
                manifest["stages"][stage] = "completed"
            if manifest["inputs"] != input_fingerprints(root) or manifest["code"] != code_fingerprints(root):
                raise RuntimeError("Inputs or analysis code changed during the run. Re-run the analysis.")
            fresh = [
                file for file in result_files(root)
                if (stamp := file_stamp(file)) and stamp[1] > 0 and stamp != old_outputs.get(file)
            ]
            missing = [relative for relative in REQUIRED_OUTPUTS if root / relative not in fresh]
            if missing:
                raise RuntimeError("Required outputs were not regenerated: " + ", ".join(missing))
            generated = datetime.now(UTC).isoformat()
            write_summary(root, [file for file in fresh if file.suffix == ".png"], generated)
            manifest["outputs"] = fingerprints(root, [*fresh, root / SUMMARY])
            manifest.update(status="completed", finished_utc=generated)
        except (Exception, KeyboardInterrupt) as exc:
            manifest.update(status="failed", error=str(exc), finished_utc=datetime.now(UTC).isoformat())
            write_manifest(root, manifest)
            raise
        write_manifest(root, manifest)
    print("\nAnalysis completed. Open results/analysis_summary.md in VS Code.", flush=True)


def verify(root: Path) -> bool:
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("status") != "completed"
            or any(not isinstance(manifest.get(key), dict) for key in ("inputs", "code", "outputs"))):
        print("No completed compatible run. Run 'Analyse starten' first.")
        return False
    checks = [
        ("inputs", input_fingerprints(root)),
        ("code", code_fingerprints(root)),
    ]
    expected_outputs = manifest.get("outputs", {})
    if not set([*REQUIRED_OUTPUTS, SUMMARY.as_posix()]).issubset(expected_outputs):
        print("The run manifest is missing required outputs.")
        return False
    outputs = {}
    for name in expected_outputs:
        file = root / name
        if not file.resolve().is_relative_to(root.resolve()) or Path(name).is_absolute():
            print(f"Unsafe output path in manifest: {name}")
            return False
        if file.is_file():
            outputs[name] = digest(file)
    checks.append(("outputs", outputs))
    valid = True
    for label, current in checks:
        recorded = manifest[label]
        changed = sorted(name for name in current.keys() | recorded.keys()
                         if current.get(name) != recorded.get(name))
        if changed:
            valid = False
            print(f"[CHANGED] {label}: {', '.join(changed)}")
        else:
            print(f"[OK] {label}: {len(current)} file(s)")
    return valid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("test", "sync", "doctor", "run", "verify"))
    parser.add_argument("--ref", help="Optional already-fetched archive ref for sync only.")
    args = parser.parse_args()
    if args.ref and args.action != "sync":
        parser.error("--ref is only supported by sync")
    try:
        if args.action == "test":
            run_child(ROOT, "-m", "unittest", "discover", "-v")
            run_child(ROOT, "-m", "ruff", "check", "--no-cache", "src", "tests")
        elif args.action == "sync":
            with workflow_lock(ROOT):
                extra = ["--ref", args.ref] if args.ref else []
                run_child(ROOT, "src/sync_collection_data.py", *extra)
        elif args.action == "doctor":
            return 0 if doctor(ROOT) else 1
        elif args.action == "run":
            run_pipeline(ROOT)
        else:
            return 0 if verify(ROOT) else 1
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Action failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
