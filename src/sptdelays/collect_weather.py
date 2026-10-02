from __future__ import annotations

import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
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


def _hourly_frame(
    payload: dict, station: pd.Series, endpoint: str, source: str, fetched_at: str,
    variables: list[str] | None = None,
) -> pd.DataFrame:
    if not isinstance(payload, dict):
        raise TypeError("Weather response must be a JSON object.")
    hourly = payload.get("hourly") or {}
    if not isinstance(hourly, dict):
        raise TypeError("Weather hourly data must be a JSON object.")
    if not hourly.get("time"):
        raise ValueError("Weather response does not contain hourly times.")
    weather = pd.DataFrame(hourly)
    missing = set(variables or []) - set(weather.columns)
    if missing:
        raise ValueError(f"Weather response is missing requested variables: {sorted(missing)}")
    for column in variables or []:
        weather[column] = pd.to_numeric(weather[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
    weather.insert(0, "station_id", normalize_station_id(station["station_id"]))
    weather.insert(1, "station_name", station["station_name"])
    # Requests explicitly use UTC; repeated autumn hours stay distinct.
    utc_time = pd.to_datetime(weather.pop("time"), errors="coerce", utc=True)
    if utc_time.isna().any() or utc_time.duplicated().any():
        raise ValueError("Weather response contains invalid or duplicate UTC hours.")
    if utc_time.ne(utc_time.dt.floor("h")).any():
        raise ValueError("Weather timestamps must be exact UTC hours; refusing to round them.")
    weather["observation_hour"] = utc_time.dt.strftime("%Y-%m-%dT%H:00:00%z")
    weather["weather_source"] = source
    weather["weather_endpoint"] = endpoint
    weather["weather_fetched_at"] = fetched_at
    return weather


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    """Keep the previous CSV intact if serialization or replacement fails."""
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                     suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        frame.to_csv(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _merge_weather_updates(
    prior: pd.DataFrame, incoming: pd.DataFrame, variables: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prefer more complete whole rows; ties use the incoming fetch, never mix products."""
    keys = ["station_id", "observation_hour"]

    def normalize(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        if frame.empty:
            return pd.DataFrame(columns=[*keys, *variables, "weather_source", "weather_fetched_at"])
        frame["station_id"] = frame["station_id"].map(normalize_station_id)
        hours = pd.to_datetime(frame["observation_hour"], format="mixed", errors="coerce", utc=True)
        if hours.isna().any() or hours.ne(hours.dt.floor("h")).any():
            raise ValueError("Saved weather updates require valid, exact UTC hour keys.")
        if frame["station_id"].isna().any() or frame["station_id"].eq("").any():
            raise ValueError("Weather updates contain missing station IDs.")
        frame["observation_hour"] = hours.dt.strftime("%Y-%m-%dT%H:00:00%z")
        if frame.duplicated(keys).any():
            raise ValueError("Weather updates contain duplicate station-hour keys.")
        for column in variables:
            frame[column] = pd.to_numeric(
                frame[column] if column in frame else pd.Series(np.nan, index=frame.index),
                errors="coerce",
            ).replace([np.inf, -np.inf], np.nan)
        if "weather_source" not in frame:
            frame["weather_source"] = "legacy_unspecified"
        frame["weather_source"] = frame["weather_source"].fillna("legacy_unspecified")
        return frame

    old, new = normalize(prior).set_index(keys), normalize(incoming).set_index(keys)
    old_counts = old[variables].notna().sum(axis=1).reindex(new.index)
    new_counts = new[variables].notna().sum(axis=1)
    retain = old_counts.gt(new_counts)
    accepted = new.loc[~retain]
    kept = old.loc[~old.index.isin(accepted.index)]
    parts = [part for part in [kept, accepted] if not part.empty]
    result = (pd.concat(parts) if parts else old.iloc[:0]).sort_index()
    audit = pd.DataFrame({
        "prior_valid_variables": old_counts,
        "incoming_valid_variables": new_counts,
        "decision": np.where(retain, "retained_more_complete_prior",
                             np.where(old_counts.isna(), "added", "updated")),
        "incoming_source": new["weather_source"],
        "selected_source": result["weather_source"].reindex(new.index),
    })
    for column in ["weather_fetched_at", "weather_endpoint"]:
        if column in new:
            audit[f"incoming_{column}"] = new[column]
        if column in result:
            audit[f"selected_{column}"] = result[column].reindex(new.index)
    return result.reset_index(), audit.reset_index()


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
    if stations.empty:
        raise ValueError("No station coordinates available. Resolve stations and run prepare first.")
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
                if not isinstance(payload, dict):
                    raise TypeError("Weather response must be a JSON object.")
                stamp = fetched.strftime("%Y%m%dT%H%M%S%fZ")
                raw_path = PATHS.raw / "weather" / f"{station['station_id']}_{window_start}_{window_end}_{stamp}.json"
                write_json(raw_path, {**payload, "_collection": {"endpoint": endpoint, "params": params, "fetched_at_utc": fetched.isoformat()}}, exclusive=True)
                entry["raw_file"] = raw_path.name
                weather = _hourly_frame(payload, station, endpoint, source, fetched.isoformat(),
                                        settings["weather_hourly_variables"])
                records.append(weather)
                entry.update(rows=len(weather), status="ok",
                             incomplete_rows=int(weather[settings["weather_hourly_variables"]].isna().any(axis=1).sum()))
            except (RuntimeError, ValueError, TypeError) as exc:
                # A partial collection is usable, but every failed station/window
                # remains visible. Never silently switch weather products.
                entry["error"] = str(exc)
            collection_log.append(entry)
            time.sleep(settings["request_pause_seconds"])
    log_path = PATHS.interim / "weather_collection_log.csv"
    log = pd.DataFrame(collection_log)
    if log_path.exists():
        log = pd.concat([pd.read_csv(log_path), log], ignore_index=True)
    _write_csv_atomic(log, log_path)
    if not records:
        raise RuntimeError(f"No weather observations were returned; see {log_path}")
    incoming = pd.concat(records, ignore_index=True)
    output = PATHS.interim / "weather_hourly.csv"
    prior = pd.read_csv(output, dtype={"station_id": "string"}) if output.exists() else pd.DataFrame()
    result, audit = _merge_weather_updates(prior, incoming, settings["weather_hourly_variables"])
    _write_csv_atomic(result, output)
    _write_csv_atomic(audit, PATHS.tables / "weather_update_audit.csv")
    failures = sum(entry["status"] != "ok" for entry in collection_log)
    retained = audit["decision"].eq("retained_more_complete_prior").sum()
    print(f"Stored {len(result):,} station-hour weather rows; failed station-windows: {failures}; "
          f"more complete prior rows retained: {retained}")
    return result
