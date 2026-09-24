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
    event_type = "departure" if stop.get("departure") else "arrival"
    scheduled = stop.get(event_type)
    # Compare matching events only; an arrival prognosis is not a departure.
    predicted = prognosis.get(event_type)
    scheduled_ts = _to_utc(scheduled)
    predicted_ts = _to_utc(predicted)
    delay = pd.to_numeric(stop.get("delay"), errors="coerce")
    delay_source = "api_delay" if pd.notna(delay) else "missing"
    if pd.isna(delay) and pd.notna(scheduled_ts) and pd.notna(predicted_ts):
        delay = (predicted_ts - scheduled_ts).total_seconds() / 60
        delay_source = "prognosis_difference"
    station_id = normalize_station_id(station_object.get("id") or station["station_id"])
    journey = entry.get("name") or entry.get("number") or ""
    observation_id = stable_id(
        [observed_at, station_id, journey, scheduled, event_type, entry.get("to"), entry.get("operator")]
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
        "delay_source": delay_source,
        "event_type": event_type,
        # This endpoint does not document a cancellation indicator.
        "cancelled": None,
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
                    "type": "departure",
                },
                timeout=settings["request_timeout_seconds"],
            )
            if not isinstance(payload.get("stationboard"), list):
                raise TypeError("Response does not contain a stationboard list.")
        except (RuntimeError, TypeError) as exc:
            error = {
                "station_id": str(station["station_id"]),
                "station_name": station["station_name"],
                "error": str(exc),
            }
            raw_payload["stations"][str(station["station_id"])] = error
            station_errors.append(error)
            time.sleep(settings["request_pause_seconds"])
            continue
        raw_payload["stations"][str(station["station_id"])] = payload
        received_at = datetime.now(UTC).isoformat()
        rows.extend(_normalise_entry(entry, station, received_at) for entry in payload["stationboard"])
        time.sleep(settings["request_pause_seconds"])

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    raw_payload["station_errors"] = station_errors
    raw_path = PATHS.raw / "transport_live" / f"stationboards_{stamp}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("x", encoding="utf-8") as handle:
        json.dump(raw_payload, handle, ensure_ascii=False)

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"The snapshot returned no observations. Raw response: {raw_path}")
    # Append-only snapshots avoid reading and rewriting the entire growing study
    # dataset on every scheduled collection. The old cumulative CSV remains a
    # read-only legacy input and is combined with these parts during preparation.
    frame = frame.drop_duplicates("observation_id", keep="last")
    normalized_path = PATHS.interim / "live_snapshots" / f"stationboards_{stamp}.csv"
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    with normalized_path.open("x", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False)
    log_path = PATHS.interim / "collection_log.csv"
    prior_log = pd.read_csv(log_path) if log_path.exists() else pd.DataFrame()
    totals = (
        pd.to_numeric(prior_log["cumulative_snapshot_rows"], errors="coerce").dropna()
        if "cumulative_snapshot_rows" in prior_log else pd.Series(dtype="float64")
    )
    has_new_log_entries = "normalized_file" in prior_log and prior_log["normalized_file"].notna().any()
    if not totals.empty and has_new_log_entries:
        previous_total = int(totals.iloc[-1])
    else:
        # Historical development data include an unlogged raw snapshot. The
        # legacy normalized CSV, not the old log, is the authoritative base.
        legacy_path = PATHS.interim / "live_observations.csv"
        previous_total = 0
        if legacy_path.exists():
            with legacy_path.open(encoding="utf-8") as handle:
                previous_total = max(0, sum(1 for _ in handle) - 1)
    log_entry = pd.DataFrame(
        [
            {
                "observed_at_utc": observed_at,
                "raw_file": raw_path.name,
                "normalized_file": normalized_path.name,
                "stations_requested": len(stations),
                "stations_succeeded": len(stations) - len(station_errors),
                "stations_failed": len(station_errors),
                "rows_returned": len(rows),
                "cumulative_snapshot_rows": previous_total + len(frame),
            }
        ]
    )
    if not prior_log.empty:
        log_entry = pd.concat([prior_log, log_entry], ignore_index=True)
    log_entry.to_csv(log_path, index=False)
    print(f"Collected {len(frame):,} distinct snapshot rows; logged cumulative rows: {previous_total + len(frame):,}")
    if station_errors:
        print(f"Warning: {len(station_errors)} station requests failed; see {raw_path.name}")
    return frame
