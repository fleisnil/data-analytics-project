from __future__ import annotations

import time

import pandas as pd

from .http import get_json
from .settings import PATHS, load_settings
from .utils import normalize_station_id


def resolve_stations() -> pd.DataFrame:
    settings = load_settings()
    panel = pd.read_csv(PATHS.config / "stations.csv", dtype={"station_id": "string"})
    rows: list[dict] = []
    for _, row in panel.iterrows():
        payload = get_json(
            f"{settings['transport_api']}/locations",
            params={"query": row["station_name"], "type": "station"},
            timeout=settings["request_timeout_seconds"],
        )
        stations = [item for item in payload.get("stations", []) if item.get("id")]
        best = stations[0] if stations else {}
        coordinate = best.get("coordinate") or {}
        rows.append(
            {
                **row.to_dict(),
                "configured_station_id": normalize_station_id(row["station_id"]),
                "station_id": normalize_station_id(best.get("id") or row["station_id"]),
                "api_station_name": best.get("name"),
                "latitude": coordinate.get("x"),
                "longitude": coordinate.get("y"),
                "api_match_score": best.get("score"),
            }
        )
        time.sleep(settings["request_pause_seconds"])
    resolved = pd.DataFrame(rows)
    resolved.to_csv(PATHS.interim / "stations_resolved.csv", index=False)
    changed = resolved[resolved["configured_station_id"] != resolved["station_id"]]
    print(f"Resolved {len(resolved)} stations; {len(changed)} configured IDs changed by API resolution")
    return resolved


def load_station_panel(resolve_if_missing: bool = True) -> pd.DataFrame:
    path = PATHS.interim / "stations_resolved.csv"
    if path.exists():
        return pd.read_csv(path, dtype={"station_id": "string", "configured_station_id": "string"})
    if resolve_if_missing:
        return resolve_stations()
    return pd.read_csv(PATHS.config / "stations.csv", dtype={"station_id": "string"})

