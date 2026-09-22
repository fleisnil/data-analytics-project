from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from .http import get_json
from .settings import PATHS, load_settings
from .utils import write_json


def _endpoint_for(end_date: date, settings: dict) -> str:
    if end_date >= datetime.now(UTC).date() - timedelta(days=5):
        return settings["weather_forecast_api"]
    return settings["weather_archive_api"]


def collect_weather() -> pd.DataFrame:
    settings = load_settings()
    transport_path = PATHS.interim / "transport_prepared.csv"
    if not transport_path.exists():
        raise FileNotFoundError("Run the prepare step before collecting weather.")
    transport = pd.read_csv(transport_path, dtype={"station_id": "string"})
    transport["service_date"] = pd.to_datetime(transport["service_date"], errors="coerce")
    start_date = transport["service_date"].min().date()
    end_date = transport["service_date"].max().date()
    stations = (
        transport[["station_id", "station_name", "latitude", "longitude"]]
        .dropna(subset=["latitude", "longitude"])
        .drop_duplicates("station_id")
    )
    records: list[pd.DataFrame] = []
    endpoint = _endpoint_for(end_date, settings)
    for _, station in stations.iterrows():
        params = {
            "latitude": float(station["latitude"]),
            "longitude": float(station["longitude"]),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(settings["weather_hourly_variables"]),
            "timezone": settings["timezone"],
        }
        try:
            payload = get_json(endpoint, params=params, timeout=settings["request_timeout_seconds"])
        except RuntimeError:
            fallback = settings["weather_archive_api"] if endpoint != settings["weather_archive_api"] else settings["weather_forecast_api"]
            payload = get_json(fallback, params=params, timeout=settings["request_timeout_seconds"])
        raw_path = PATHS.raw / "weather" / f"{station['station_id']}_{start_date}_{end_date}.json"
        write_json(raw_path, payload)
        hourly = payload.get("hourly") or {}
        if not hourly.get("time"):
            continue
        weather = pd.DataFrame(hourly)
        weather.insert(0, "station_id", str(station["station_id"]))
        weather.insert(1, "station_name", station["station_name"])
        local_time = pd.to_datetime(weather.pop("time"), errors="coerce")
        localized = local_time.dt.tz_localize(
            settings["timezone"], ambiguous="infer", nonexistent="shift_forward"
        )
        weather["observation_hour"] = localized.dt.strftime("%Y-%m-%dT%H:00:00%z")
        records.append(weather)
        time.sleep(settings["request_pause_seconds"])
    if not records:
        raise RuntimeError("No weather observations were returned.")
    result = pd.concat(records, ignore_index=True)
    result = result.drop_duplicates(["station_id", "observation_hour"])
    output = PATHS.interim / "weather_hourly.csv"
    result.to_csv(output, index=False)
    print(f"Collected {len(result):,} station-hour weather rows")
    return result
