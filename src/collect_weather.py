#!/usr/bin/env python3
"""
Collect one MeteoSwiss weather snapshot for the eight project regions.

Source:
    MeteoSwiss Open Data, SwissMetNet automatic weather stations
    https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/

Each run:
- downloads the current 10-minute station file (`t_now`) for each region
- stores the raw CSV response for reproducibility
- keeps the latest available measurement per weather station
- writes one combined weather snapshot to data/interim/weather_snapshots/

MeteoSwiss reference timestamps are UTC.
Source attribution: MeteoSwiss.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn"
REQUEST_TIMEOUT_SECONDS = 30

RAW_DIR = Path("data/raw/weather")
SNAPSHOT_DIR = Path("data/interim/weather_snapshots")


# Weather stations chosen to represent the same eight regions as the OJP collector.
# Lausanne uses Pully, the nearby SwissMetNet station.
WEATHER_STATIONS = [
    {"city": "Zürich",     "station_abbr": "SMA", "station_name": "Zürich / Fluntern"},
    {"city": "Bern",       "station_abbr": "BER", "station_name": "Bern / Zollikofen"},
    {"city": "Basel",      "station_abbr": "BAS", "station_name": "Basel / Binningen"},
    {"city": "Luzern",     "station_abbr": "LUZ", "station_name": "Luzern"},
    {"city": "St. Gallen", "station_abbr": "STG", "station_name": "St. Gallen"},
    {"city": "Lausanne",   "station_abbr": "PUY", "station_name": "Pully"},
    {"city": "Genève",     "station_abbr": "GVE", "station_name": "Genève / Cointrin"},
    {"city": "Lugano",     "station_abbr": "LUG", "station_name": "Lugano"},
]


# Official MeteoSwiss SwissMetNet identifiers for the 10-minute files.
PARAMETER_MAP = {
    "tre200s0": "temperature_c",
    "rre150z0": "precipitation_mm_10min",
    "ure200s0": "relative_humidity_pct",
    "fu3010z0": "wind_speed_kmh_10min",
    "fu3010z1": "wind_gust_kmh",
    "prestas0": "station_pressure_hpa",
}

# These four variables are the core weather predictors for the project.
# MeteoSwiss can publish a newest timestamp before all parameters for that
# timestamp are populated. We therefore prefer the latest row where all core
# variables are available instead of blindly taking the final CSV row.
CORE_PARAMETER_COLUMNS = [
    "tre200s0",
    "rre150z0",
    "ure200s0",
    "fu3010z0",
]


def station_url(station_abbr: str) -> str:
    """Return the MeteoSwiss current 10-minute CSV URL for one station."""
    code = station_abbr.lower()
    return f"{BASE_URL}/{code}/ogd-smn_{code}_t_now.csv"


def read_meteoswiss_csv(content: bytes) -> pd.DataFrame:
    """
    Parse a MeteoSwiss semicolon-separated CSV.

    The current files are normally UTF-8/UTF-8-SIG. A latin-1 fallback is kept
    for robustness with accented station/metadata text.
    """
    last_error = None

    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = content.decode(encoding)
            df = pd.read_csv(io.StringIO(text), sep=";")
            break
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    else:
        raise ValueError(f"Could not decode MeteoSwiss CSV: {last_error}")

    # Some MeteoSwiss files/documentation note quoted/inconsistent column names.
    df.columns = (
        pd.Index(df.columns)
        .astype(str)
        .str.strip()
        .str.replace("'", "", regex=False)
        .str.replace('"', "", regex=False)
    )

    return df


def latest_measurement(
    df: pd.DataFrame,
    city: str,
    station_abbr: str,
    station_name: str,
    collection_timestamp: str,
    source_url: str,
) -> pd.DataFrame:
    """Return a one-row DataFrame containing the latest valid station reading."""
    if "reference_timestamp" not in df.columns:
        # Compatibility fallback for older/recent MeteoSwiss file variants.
        if "REFERENCE_TS" in df.columns:
            df = df.rename(columns={"REFERENCE_TS": "reference_timestamp"})
        else:
            raise ValueError("No reference_timestamp column found.")

    df = df.copy()

    # MeteoSwiss documents reference timestamps as UTC in dd.mm.yyyy HH:MM.
    df["reference_timestamp"] = pd.to_datetime(
        df["reference_timestamp"],
        format="%d.%m.%Y %H:%M",
        utc=True,
        errors="coerce",
    )

    df = df.dropna(subset=["reference_timestamp"]).sort_values(
        "reference_timestamp"
    )

    if df.empty:
        raise ValueError("No valid MeteoSwiss measurement timestamps found.")

    # Convert the weather parameters before testing completeness. This also
    # converts placeholders/non-numeric values to NaN.
    for source_column in PARAMETER_MAP:
        if source_column in df.columns:
            df[source_column] = pd.to_numeric(
                df[source_column],
                errors="coerce",
            )

    available_core = [
        column
        for column in CORE_PARAMETER_COLUMNS
        if column in df.columns
    ]

    if not available_core:
        raise ValueError("None of the required core weather parameters found.")

    df["_core_parameter_count"] = df[available_core].notna().sum(axis=1)

    # Preferred case: choose the newest row with all four core parameters.
    if len(available_core) == len(CORE_PARAMETER_COLUMNS):
        complete_core = df[df[available_core].notna().all(axis=1)]
    else:
        complete_core = df.iloc[0:0]

    if not complete_core.empty:
        latest = complete_core.iloc[[-1]].copy()
        selection_method = "latest_core_complete"
    else:
        # Robust fallback: use the newest row among those with the highest
        # number of available core parameters. The completeness flag below
        # makes this visible in the saved dataset.
        max_count = int(df["_core_parameter_count"].max())
        best_rows = df[df["_core_parameter_count"] == max_count]
        latest = best_rows.iloc[[-1]].copy()
        selection_method = "latest_best_available"

    core_parameter_count = int(latest["_core_parameter_count"].iloc[0])
    core_complete = (
        len(available_core) == len(CORE_PARAMETER_COLUMNS)
        and core_parameter_count == len(CORE_PARAMETER_COLUMNS)
    )

    row = {
        "collection_timestamp": pd.to_datetime(collection_timestamp, utc=True),
        "city": city,
        "weather_station_abbr": station_abbr,
        "weather_station_name": station_name,
        "reference_timestamp": latest["reference_timestamp"].iloc[0],
        "weather_selection_method": selection_method,
        "weather_core_complete": core_complete,
        "weather_core_parameter_count": core_parameter_count,
        "source_url": source_url,
    }

    for source_column, output_column in PARAMETER_MAP.items():
        if source_column in latest.columns:
            row[output_column] = latest[source_column].iloc[0]
        else:
            row[output_column] = pd.NA

    out = pd.DataFrame([row])

    out["collection_timestamp_local"] = (
        out["collection_timestamp"].dt.tz_convert("Europe/Zurich")
    )
    out["reference_timestamp_local"] = (
        out["reference_timestamp"].dt.tz_convert("Europe/Zurich")
    )

    out["weather_age_minutes"] = (
        out["collection_timestamp"] - out["reference_timestamp"]
    ).dt.total_seconds() / 60

    return out


def collect_weather_station(
    session: requests.Session,
    station: dict,
    collection_timestamp: str,
    batch_id: str,
) -> pd.DataFrame:
    """Download, save, and parse the current MeteoSwiss data for one station."""
    url = station_url(station["station_abbr"])

    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "ZHAW-Data-Analytics-Project/1.0"},
    )
    response.raise_for_status()

    raw_batch_dir = RAW_DIR / batch_id
    raw_batch_dir.mkdir(parents=True, exist_ok=True)

    raw_path = (
        raw_batch_dir
        / f"{station['station_abbr'].lower()}_t_now.csv"
    )
    raw_path.write_bytes(response.content)

    df = read_meteoswiss_csv(response.content)

    return latest_measurement(
        df=df,
        city=station["city"],
        station_abbr=station["station_abbr"],
        station_name=station["station_name"],
        collection_timestamp=collection_timestamp,
        source_url=url,
    )


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc)
    batch_id = now_utc.strftime("%Y%m%d_%H%M%S")
    collection_timestamp = (
        now_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )

    print("=" * 70)
    print("METEOSWISS MULTI-STATION COLLECTION")
    print("=" * 70)
    print(f"Batch: {batch_id}")
    print(f"Weather stations configured: {len(WEATHER_STATIONS)}")
    print()

    frames = []
    failures = []

    with requests.Session() as session:
        for index, station in enumerate(WEATHER_STATIONS, start=1):
            print(
                f"[{index:02d}/{len(WEATHER_STATIONS)}] "
                f"{station['city']} | "
                f"{station['station_abbr']} | "
                f"{station['station_name']}"
            )

            try:
                df_station = collect_weather_station(
                    session=session,
                    station=station,
                    collection_timestamp=collection_timestamp,
                    batch_id=batch_id,
                )

                frames.append(df_station)

                ref_ts = df_station["reference_timestamp_local"].iloc[0]
                age = df_station["weather_age_minutes"].iloc[0]

                core_complete = bool(
                    df_station["weather_core_complete"].iloc[0]
                )
                selection_method = (
                    df_station["weather_selection_method"].iloc[0]
                )

                print(
                    f"  OK: measurement {ref_ts} "
                    f"(age {age:.1f} min, "
                    f"core_complete={core_complete}, "
                    f"selection={selection_method})"
                )

            except Exception as exc:
                failures.append(
                    {
                        "city": station["city"],
                        "station_abbr": station["station_abbr"],
                        "error": str(exc),
                    }
                )
                print(f"  ERROR: {exc}")

    print()
    print("=" * 70)
    print("COLLECTION SUMMARY")
    print("=" * 70)

    if not frames:
        print("No weather observations were collected.")
        print(f"Failed stations: {len(failures)}")
        return 1

    df_all = pd.concat(frames, ignore_index=True)

    snapshot_path = (
        SNAPSHOT_DIR
        / f"weather_snapshot_{batch_id}.csv"
    )
    df_all.to_csv(snapshot_path, index=False)

    print(f"Weather observations: {len(df_all)}")
    print(
        f"Successful stations: "
        f"{len(df_all)}/{len(WEATHER_STATIONS)}"
    )
    print(f"Failed stations: {len(failures)}")
    print(f"Combined snapshot: {snapshot_path}")

    display_columns = [
        "city",
        "weather_station_abbr",
        "reference_timestamp_local",
        "weather_core_complete",
        "temperature_c",
        "precipitation_mm_10min",
        "relative_humidity_pct",
        "wind_speed_kmh_10min",
    ]

    print("\nLatest weather values:")
    print(df_all[display_columns].to_string(index=False))

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(
                f"- {failure['city']} | "
                f"{failure['station_abbr']}: "
                f"{failure['error']}"
            )

    # Partial success is saved and remains useful.
    return 0


if __name__ == "__main__":
    sys.exit(main())
