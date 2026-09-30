#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def newest_file(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matching {pattern} in {directory}")
    return files[-1]


def archive_collection(source_root: Path, archive_root: Path) -> dict:
    ojp_file = newest_file(
        source_root / "data/interim/ojp_snapshots",
        "ojp_snapshot_*.csv",
    )
    weather_file = newest_file(
        source_root / "data/interim/weather_snapshots",
        "weather_snapshot_*.csv",
    )

    ojp = pd.read_csv(ojp_file)
    weather = pd.read_csv(weather_file)

    if ojp.empty:
        raise ValueError(f"OJP snapshot is empty: {ojp_file}")
    if weather.empty:
        raise ValueError(f"Weather snapshot is empty: {weather_file}")

    ojp_target_dir = archive_root / "data/interim/ojp_snapshots"
    weather_target_dir = archive_root / "data/interim/weather_snapshots"
    ojp_target_dir.mkdir(parents=True, exist_ok=True)
    weather_target_dir.mkdir(parents=True, exist_ok=True)

    ojp_target = ojp_target_dir / ojp_file.name
    weather_target = weather_target_dir / weather_file.name

    shutil.copy2(ojp_file, ojp_target)
    shutil.copy2(weather_file, weather_target)

    manifest_path = archive_root / "data/collection_manifest.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "archived_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ojp_file": ojp_file.name,
        "ojp_rows": len(ojp),
        "ojp_cities": ojp["city"].nunique() if "city" in ojp.columns else pd.NA,
        "ojp_stations": ojp["station_id"].nunique() if "station_id" in ojp.columns else pd.NA,
        "weather_file": weather_file.name,
        "weather_rows": len(weather),
        "weather_cities": weather["city"].nunique() if "city" in weather.columns else pd.NA,
    }

    new_row = pd.DataFrame([record])

    if manifest_path.exists():
        manifest = pd.read_csv(manifest_path)
        if "ojp_file" in manifest.columns and ojp_file.name in set(manifest["ojp_file"].astype(str)):
            print(f"Run already present: {ojp_file.name}")
            return record
        manifest = pd.concat([manifest, new_row], ignore_index=True)
    else:
        manifest = new_row

    manifest.to_csv(manifest_path, index=False)

    print(f"Archived: {ojp_target}")
    print(f"Archived: {weather_target}")
    print(f"Updated: {manifest_path}")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument("--archive-root", type=Path, required=True)
    args = parser.parse_args()

    archive_collection(
        source_root=args.source_root.resolve(),
        archive_root=args.archive_root.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
