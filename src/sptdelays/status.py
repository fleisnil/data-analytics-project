from __future__ import annotations

import pandas as pd

from .settings import PATHS, load_settings


def print_collection_status() -> None:
    log_path = PATHS.interim / "collection_log.csv"
    if not log_path.exists():
        print("No collection log exists yet. Run: sptdelays collect-live")
        return
    log = pd.read_csv(log_path)
    observed = pd.to_datetime(log["observed_at_utc"], errors="coerce", utc=True)
    timezone = load_settings().get("timezone", "Europe/Zurich")
    print(f"Logged snapshots: {len(log):,}")
    print(f"Collection start (UTC): {observed.min()}")
    print(f"Collection end (UTC):   {observed.max()}")
    print(f"Distinct collection dates ({timezone}): "
          f"{observed.dt.tz_convert(timezone).dt.date.nunique():,}")
    print(f"Station-request failures: {log['stations_failed'].sum():,.0f}")
    if "cumulative_snapshot_rows" in log:
        total = pd.to_numeric(log["cumulative_snapshot_rows"], errors="coerce").dropna()
        if not total.empty:
            print(f"Logged cumulative snapshot rows: {int(total.iloc[-1]):,}")
    ordered = observed.dropna().drop_duplicates().sort_values()
    if len(ordered) >= 2:
        gap = ordered.diff().dt.total_seconds().max() / 60
        print(f"Longest logged collection gap: {gap:.1f} minutes")
    else:
        print("Collection intervals cannot be checked with fewer than two logged snapshots.")
    raw_files = sorted((PATHS.raw / "transport_live").glob("stationboards_*.json"))
    logged_files = set(log["raw_file"].dropna().astype(str)) if "raw_file" in log else set()
    unlogged_files = [file.name for file in raw_files if file.name not in logged_files]
    print(f"Raw snapshot files: {len(raw_files):,}")
    if unlogged_files:
        print(f"Warning: {len(unlogged_files)} raw snapshot file(s) have no log entry; "
              f"first: {unlogged_files[0]}")
    parts = sorted((PATHS.interim / "live_snapshots").glob("stationboards_*.csv"))
    logged_parts = set(log["normalized_file"].dropna().astype(str)) if "normalized_file" in log else set()
    unlogged_parts = [part.name for part in parts if part.name not in logged_parts]
    print(f"Normalized snapshot files: {len(parts):,}")
    if unlogged_parts:
        print(f"Warning: {len(unlogged_parts)} normalized snapshot file(s) have no log entry; "
              f"first: {unlogged_parts[0]}")
    print("Snapshot rows include repeated forecasts; prepare deduplicates station calls.")
    print("Run sptdelays validate after integration for data quality and study coverage.")
