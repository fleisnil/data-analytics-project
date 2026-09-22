from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .collect_stations import load_station_panel
from .settings import PATHS, load_settings
from .utils import add_time_features, normalize_station_id, parse_transport_mode, stable_id


def _parse_local(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, dayfirst=True, errors="coerce").dt.tz_localize(
        "Europe/Zurich", ambiguous="NaT", nonexistent="shift_forward"
    ).dt.tz_convert("UTC")


def _prepare_actuals(files: list[Path]) -> pd.DataFrame:
    usecols = [
        "BETRIEBSTAG", "FAHRT_BEZEICHNER", "BETREIBER_ABK", "BETREIBER_NAME",
        "PRODUKT_ID", "LINIEN_ID", "LINIEN_TEXT", "VERKEHRSMITTEL_TEXT",
        "FAELLT_AUS_TF", "BPUIC", "HALTESTELLEN_NAME", "ANKUNFTSZEIT",
        "AN_PROGNOSE", "AN_PROGNOSE_STATUS", "ABFAHRTSZEIT", "AB_PROGNOSE",
        "AB_PROGNOSE_STATUS", "SLOID",
    ]
    chunks = [pd.read_csv(path, sep=";", usecols=lambda col: col in usecols, dtype="string") for path in files]
    raw = pd.concat(chunks, ignore_index=True)
    scheduled_arrival = _parse_local(raw.get("ANKUNFTSZEIT"))
    reported_arrival = _parse_local(raw.get("AN_PROGNOSE"))
    scheduled_departure = _parse_local(raw.get("ABFAHRTSZEIT"))
    reported_departure = _parse_local(raw.get("AB_PROGNOSE"))
    use_arrival = scheduled_arrival.notna() & reported_arrival.notna()
    scheduled = scheduled_arrival.where(use_arrival, scheduled_departure)
    reported = reported_arrival.where(use_arrival, reported_departure)
    signed_delay = (reported - scheduled).dt.total_seconds() / 60
    frame = pd.DataFrame(
        {
            "data_source": "opentransportdata_actuals_v2",
            "station_id": raw["BPUIC"].map(normalize_station_id),
            "station_name": raw["HALTESTELLEN_NAME"],
            "journey_id": raw["FAHRT_BEZEICHNER"],
            "operator": raw["BETREIBER_ABK"].fillna(raw["BETREIBER_NAME"]),
            "category_raw": raw["PRODUKT_ID"].fillna(raw["VERKEHRSMITTEL_TEXT"]),
            "line": raw["LINIEN_TEXT"].fillna(raw["LINIEN_ID"]),
            "scheduled_time": scheduled,
            "reported_time": reported,
            "delay_minutes_signed": signed_delay,
            "event_type": np.where(use_arrival, "arrival", "departure"),
            "reported_status": raw["AN_PROGNOSE_STATUS"].where(use_arrival, raw["AB_PROGNOSE_STATUS"]),
            "cancelled": raw["FAELLT_AUS_TF"].str.lower().eq("true"),
            "sloid": raw.get("SLOID"),
        }
    )
    return frame


def _prepare_live(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"station_id": "string"})
    frame["scheduled_time"] = pd.to_datetime(frame["scheduled_time"], errors="coerce", utc=True)
    frame["reported_time"] = pd.to_datetime(frame["reported_time"], errors="coerce", utc=True)
    frame["event_type"] = "departure_or_arrival"
    frame["reported_status"] = "live_prognosis"
    return frame


def prepare_transport(source: str = "live") -> pd.DataFrame:
    settings = load_settings()
    stations = load_station_panel()
    stations["station_id"] = stations["station_id"].map(normalize_station_id)
    if source == "actuals":
        files = sorted((PATHS.raw / "actuals_v2").glob("*_selected_stations.csv"))
        if not files:
            raise FileNotFoundError("No selected Actual data v2 files found.")
        frame = _prepare_actuals(files)
    elif source == "live":
        path = PATHS.interim / "live_observations.csv"
        if not path.exists():
            raise FileNotFoundError("Run collect-live first.")
        frame = _prepare_live(path)
    else:
        raise ValueError("source must be 'live' or 'actuals'")

    raw_count = len(frame)
    station_columns = [
        col for col in ["station_id", "station_name", "region", "canton", "station_type", "latitude", "longitude"]
        if col in stations
    ]
    frame["station_id"] = frame["station_id"].map(normalize_station_id)
    frame = frame.drop(columns=[col for col in ["region", "canton", "station_type"] if col in frame], errors="ignore")
    frame = frame.merge(stations[station_columns], on="station_id", how="left", suffixes=("", "_panel"), validate="many_to_one")
    if "station_name_panel" in frame:
        frame["station_name"] = frame["station_name"].fillna(frame["station_name_panel"])
        frame = frame.drop(columns="station_name_panel")
    for coordinate in ["latitude", "longitude"]:
        panel_coordinate = f"{coordinate}_panel"
        if panel_coordinate in frame:
            frame[coordinate] = pd.to_numeric(frame[coordinate], errors="coerce").fillna(
                pd.to_numeric(frame[panel_coordinate], errors="coerce")
            )
            frame = frame.drop(columns=panel_coordinate)
    frame["transport_mode"] = frame["category_raw"].map(parse_transport_mode)
    frame["delay_minutes_signed"] = pd.to_numeric(frame["delay_minutes_signed"], errors="coerce")
    frame["delay_minutes"] = frame["delay_minutes_signed"].clip(lower=0)
    frame["is_delayed_5"] = frame["delay_minutes"].ge(settings["delay_threshold_minutes"]).astype(int)
    frame["observation_id"] = [
        stable_id(values)
        for values in zip(
            frame["data_source"], frame["station_id"], frame["journey_id"],
            frame["scheduled_time"], frame["event_type"], strict=False,
        )
    ]
    before_dedup = len(frame)
    frame = frame.drop_duplicates("observation_id", keep="last")
    after_dedup = len(frame)
    before_plausibility = len(frame)
    frame = frame[
        frame["scheduled_time"].notna()
        & frame["delay_minutes"].notna()
        & frame["delay_minutes"].le(settings["maximum_plausible_delay_minutes"])
        & frame["region"].notna()
    ].copy()
    frame = add_time_features(frame)
    frame = frame.sort_values(["scheduled_time", "station_id", "journey_id"])
    output = PATHS.interim / "transport_prepared.csv"
    frame.to_csv(output, index=False)
    audit = pd.DataFrame(
        [
            ["raw_rows", raw_count],
            ["duplicate_rows_removed", before_dedup - after_dedup],
            ["rows_before_plausibility_filter", before_plausibility],
            ["prepared_rows", len(frame)],
            ["rows_lost_total", raw_count - len(frame)],
            ["unique_stations", frame["station_id"].nunique()],
            ["unique_service_dates", frame["service_date"].nunique()],
        ],
        columns=["integration_step", "row_count"],
    )
    audit.to_csv(PATHS.tables / "preparation_audit.csv", index=False)
    print(f"Prepared {len(frame):,} of {raw_count:,} transport rows")
    return frame


def integrate_weather() -> pd.DataFrame:
    transport = pd.read_csv(PATHS.interim / "transport_prepared.csv", dtype={"station_id": "string"})
    weather = pd.read_csv(PATHS.interim / "weather_hourly.csv", dtype={"station_id": "string"})
    before = len(transport)
    merged = transport.merge(
        weather,
        on=["station_id", "observation_hour"],
        how="left",
        validate="many_to_one",
        suffixes=("", "_weather"),
        indicator=True,
    )
    matched = int(merged["_merge"].eq("both").sum())
    merged = merged.drop(columns="_merge")
    output = PATHS.processed / "model_data.csv"
    merged.to_csv(output, index=False)
    audit_path = PATHS.tables / "integration_audit.csv"
    pd.DataFrame(
        {
            "metric": [
                "transport_rows_before_weather_join", "rows_after_weather_join",
                "weather_matches", "weather_unmatched", "row_gain_or_loss",
            ],
            "value": [before, len(merged), matched, len(merged) - matched, len(merged) - before],
        }
    ).to_csv(audit_path, index=False)
    print(f"Weather matched for {matched:,}/{len(merged):,} rows; row count change: {len(merged) - before:+,}")
    return merged
