from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pandas as pd

from .collect_stations import load_station_panel
from .http import get_json
from .settings import PATHS, load_settings
from .utils import normalize_station_id, parse_transport_mode, stable_id


def _to_utc(value: object) -> pd.Timestamp | pd.NaT:
    return pd.to_datetime(value, errors="coerce", utc=True)


def _normalise_entry(entry: dict, station: pd.Series, observed_at: str) -> dict:
    stop = entry.get("stop") or {}
    prognosis = stop.get("prognosis") or {}
    station_object = stop.get("station") or {}
    coordinate = station_object.get("coordinate") or {}
    scheduled = stop.get("departure") or stop.get("arrival")
    predicted = prognosis.get("departure") or prognosis.get("arrival")
    scheduled_ts = _to_utc(scheduled)
    predicted_ts = _to_utc(predicted)
    delay = stop.get("delay")
    if delay is None and pd.notna(scheduled_ts) and pd.notna(predicted_ts):
        delay = (predicted_ts - scheduled_ts).total_seconds() / 60
    station_id = normalize_station_id(station_object.get("id") or station["station_id"])
    journey = entry.get("name") or entry.get("number") or ""
    observation_id = stable_id(
        [observed_at, station_id, journey, scheduled, entry.get("to"), entry.get("category")]
    )
    return {
        "observation_id": observation_id,
        "data_source": "transport_opendata_live",
        "observed_at": observed_at,
        "station_id": station_id,
        "station_name": station_object.get("name") or station["station_name"],
        "region": station["region"],
        "canton": station["canton"],
        "station_type": station["station_type"],
        "latitude": coordinate.get("x"),
        "longitude": coordinate.get("y"),
        "journey_id": journey,
        "operator": entry.get("operator"),
        "category_raw": entry.get("category"),
        "transport_mode": parse_transport_mode(entry.get("category")),
        "line": entry.get("number"),
        "destination": entry.get("to"),
        "scheduled_time": scheduled,
        "reported_time": predicted,
        "delay_minutes_signed": delay,
        "cancelled": False,
        "platform": stop.get("platform"),
        "prognosis_platform": prognosis.get("platform"),
    }


def collect_live() -> pd.DataFrame:
    settings = load_settings()
    PATHS.ensure()
    stations = load_station_panel()
    observed_at = datetime.now(UTC).isoformat()
    raw_payload: dict[str, object] = {"observed_at": observed_at, "stations": {}}
    rows: list[dict] = []
    station_errors: list[dict] = []
    for _, station in stations.iterrows():
        try:
            payload = get_json(
                f"{settings['transport_api']}/stationboard",
                params={
                    "id": station["station_id"],
                    "limit": settings["live_stationboard_limit"],
                },
                timeout=settings["request_timeout_seconds"],
            )
        except RuntimeError as exc:
            error = {
                "station_id": str(station["station_id"]),
                "station_name": station["station_name"],
                "error": str(exc),
            }
            raw_payload["stations"][str(station["station_id"])] = error
            station_errors.append(error)
            continue
        raw_payload["stations"][str(station["station_id"])] = payload
        rows.extend(_normalise_entry(entry, station, observed_at) for entry in payload.get("stationboard", []))
        time.sleep(settings["request_pause_seconds"])

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw_payload["station_errors"] = station_errors
    raw_path = PATHS.raw / "transport_live" / f"stationboards_{stamp}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False), encoding="utf-8")

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"The snapshot returned no observations. Raw response: {raw_path}")
    interim_path = PATHS.interim / "live_observations.csv"
    if interim_path.exists():
        prior = pd.read_csv(interim_path, dtype={"station_id": "string"})
        frame = pd.concat([prior, frame], ignore_index=True)
    frame = frame.drop_duplicates("observation_id", keep="last")
    frame.to_csv(interim_path, index=False)
    log_path = PATHS.interim / "collection_log.csv"
    log_entry = pd.DataFrame(
        [
            {
                "observed_at_utc": observed_at,
                "raw_file": raw_path.name,
                "stations_requested": len(stations),
                "stations_succeeded": len(stations) - len(station_errors),
                "stations_failed": len(station_errors),
                "rows_returned": len(rows),
                "cumulative_snapshot_rows": len(frame),
            }
        ]
    )
    if log_path.exists():
        log_entry = pd.concat([pd.read_csv(log_path), log_entry], ignore_index=True)
    log_entry.to_csv(log_path, index=False)
    print(f"Collected {len(rows):,} rows; cumulative live observations: {len(frame):,}")
    if station_errors:
        print(f"Warning: {len(station_errors)} station requests failed; see {raw_path.name}")
    return frame
