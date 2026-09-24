from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from .http import get_json
from .settings import PATHS, load_settings
from .utils import normalize_station_id, write_json


def _endpoint_for(end_date: date, settings: dict) -> str:
    if end_date >= datetime.now(UTC).date() - timedelta(days=5):
        return settings["weather_forecast_api"]
    return settings["weather_archive_api"]


def _weather_windows(start: date, end: date, settings: dict, today: date | None = None) -> list[tuple]:
    """Keep historical and recent weather separate, with explicit provenance."""
    if start > end:
        raise ValueError("Weather start date must not follow the end date.")
    archive_end = (today or datetime.now(UTC).date()) - timedelta(days=5)
    windows = []
    if start <= archive_end:
        windows.append((start, min(end, archive_end), settings["weather_archive_api"], "archive_reanalysis"))
    if end > archive_end:
        windows.append((max(start, archive_end + timedelta(days=1)), end, settings["weather_forecast_api"], "forecast_recent"))
    return windows


def _hourly_frame(payload: dict, station: pd.Series, endpoint: str, source: str, fetched_at: str) -> pd.DataFrame:
    hourly = payload.get("hourly") or {}
    if not hourly.get("time"):
        raise ValueError("Weather response does not contain hourly times.")
    weather = pd.DataFrame(hourly)
    weather.insert(0, "station_id", normalize_station_id(station["station_id"]))
    weather.insert(1, "station_name", station["station_name"])
    # Requests explicitly use UTC; repeated autumn hours stay distinct.
    utc_time = pd.to_datetime(weather.pop("time"), errors="coerce", utc=True)
    if utc_time.isna().any() or utc_time.duplicated().any():
        raise ValueError("Weather response contains invalid or duplicate UTC hours.")
    weather["observation_hour"] = utc_time.dt.strftime("%Y-%m-%dT%H:00:00%z")
    weather["weather_source"] = source
    weather["weather_endpoint"] = endpoint
    weather["weather_fetched_at"] = fetched_at
    return weather


def collect_weather() -> pd.DataFrame:
    settings = load_settings()
    PATHS.ensure()
    transport_path = PATHS.interim / "transport_prepared.csv"
    if not transport_path.exists():
        raise FileNotFoundError("Run the prepare step before collecting weather.")
    transport = pd.read_csv(transport_path, dtype={"station_id": "string"})
    times = pd.to_datetime(transport["scheduled_time"], format="mixed", errors="coerce", utc=True)
    if times.notna().sum() == 0:
        raise ValueError("Prepared transport contains no valid timestamps for weather collection.")
    # Bounds follow UTC dates, including the previous UTC day for local midnight.
    start_date = times.min().date()
    end_date = times.max().date()
    stations = (
        transport[["station_id", "station_name", "latitude", "longitude"]]
        .dropna(subset=["latitude", "longitude"])
        .drop_duplicates("station_id")
    )
    records: list[pd.DataFrame] = []
    collection_log = []
    windows = _weather_windows(start_date, end_date, settings)
    for _, station in stations.iterrows():
        for window_start, window_end, endpoint, source in windows:
            params = {
                "latitude": float(station["latitude"]),
                "longitude": float(station["longitude"]),
                "start_date": window_start.isoformat(),
                "end_date": window_end.isoformat(),
                "hourly": ",".join(settings["weather_hourly_variables"]),
                "timezone": "UTC",
            }
            fetched = datetime.now(UTC)
            entry = {
                "station_id": station["station_id"], "start_date": window_start,
                "end_date": window_end, "endpoint": endpoint, "weather_source": source,
                "fetched_at_utc": fetched.isoformat(), "rows": 0, "status": "failed", "error": "",
            }
            try:
                payload = get_json(endpoint, params=params, timeout=settings["request_timeout_seconds"])
                stamp = fetched.strftime("%Y%m%dT%H%M%S%fZ")
                raw_path = PATHS.raw / "weather" / f"{station['station_id']}_{window_start}_{window_end}_{stamp}.json"
                write_json(raw_path, {**payload, "_collection": {"endpoint": endpoint, "params": params, "fetched_at_utc": fetched.isoformat()}}, exclusive=True)
                weather = _hourly_frame(payload, station, endpoint, source, fetched.isoformat())
                records.append(weather)
                entry.update(rows=len(weather), status="ok", raw_file=raw_path.name)
            except (RuntimeError, ValueError) as exc:
                # A partial collection is usable, but every failed station/window
                # remains visible. Never silently switch weather products.
                entry["error"] = str(exc)
            collection_log.append(entry)
            time.sleep(settings["request_pause_seconds"])
    log_path = PATHS.interim / "weather_collection_log.csv"
    log = pd.DataFrame(collection_log)
    if log_path.exists():
        log = pd.concat([pd.read_csv(log_path), log], ignore_index=True)
    log.to_csv(log_path, index=False)
    if not records:
        raise RuntimeError(f"No weather observations were returned; see {log_path}")
    result = pd.concat(records, ignore_index=True)
    output = PATHS.interim / "weather_hourly.csv"
    if output.exists():
        prior = pd.read_csv(output, dtype={"station_id": "string"})
        result = pd.concat([prior, result], ignore_index=True)
    result["station_id"] = result["station_id"].map(normalize_station_id)
    result["observation_hour"] = pd.to_datetime(result["observation_hour"], format="mixed", errors="coerce", utc=True).dt.strftime("%Y-%m-%dT%H:00:00%z")
    result["weather_source"] = result["weather_source"].fillna("legacy_unspecified")
    result = result.drop_duplicates(["station_id", "observation_hour"], keep="last")
    result.to_csv(output, index=False)
    failures = sum(entry["status"] != "ok" for entry in collection_log)
    print(f"Stored {len(result):,} station-hour weather rows; failed station-windows: {failures}")
    return result
