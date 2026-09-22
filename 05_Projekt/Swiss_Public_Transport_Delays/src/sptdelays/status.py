from __future__ import annotations

import pandas as pd

from .settings import PATHS


def print_collection_status() -> None:
    log_path = PATHS.interim / "collection_log.csv"
    observations_path = PATHS.interim / "live_observations.csv"
    if not log_path.exists():
        print("No collection log exists yet. Run: sptdelays collect-live")
        return
    log = pd.read_csv(log_path)
    observed = pd.to_datetime(log["observed_at_utc"], errors="coerce", utc=True)
    observations = (
        pd.read_csv(observations_path, usecols=["observation_id"])
        if observations_path.exists()
        else pd.DataFrame()
    )
    print(f"Snapshots: {len(log):,}")
    print(f"Collection start (UTC): {observed.min()}")
    print(f"Collection end (UTC):   {observed.max()}")
    print(f"Distinct collection dates: {observed.dt.date.nunique():,}")
    print(f"Station-request failures: {log['stations_failed'].sum():,.0f}")
    print(f"Cumulative snapshot observations: {len(observations):,}")

