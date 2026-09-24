from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .collect_stations import load_station_panel
from .settings import PATHS, load_settings
from .utils import add_time_features, normalize_station_id, parse_transport_mode, stable_id


def _parse_local(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="mixed", dayfirst=True, errors="coerce").dt.tz_localize(
        "Europe/Zurich", ambiguous="NaT", nonexistent="NaT"
    ).dt.tz_convert("UTC")


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame[name] if name in frame else pd.Series(pd.NA, index=frame.index, dtype="string")


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
    scheduled_arrival = _parse_local(_column(raw, "ANKUNFTSZEIT"))
    reported_arrival = _parse_local(_column(raw, "AN_PROGNOSE"))
    scheduled_departure = _parse_local(_column(raw, "ABFAHRTSZEIT"))
    reported_departure = _parse_local(_column(raw, "AB_PROGNOSE"))
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
            "operator": _column(raw, "BETREIBER_ABK").fillna(_column(raw, "BETREIBER_NAME")),
            "category_raw": _column(raw, "PRODUKT_ID").fillna(_column(raw, "VERKEHRSMITTEL_TEXT")),
            "line": _column(raw, "LINIEN_TEXT").fillna(_column(raw, "LINIEN_ID")),
            "scheduled_time": scheduled,
            "reported_time": reported,
            "delay_minutes_signed": signed_delay,
            "event_type": np.where(use_arrival, "arrival", "departure"),
            "reported_status": _column(raw, "AN_PROGNOSE_STATUS").where(use_arrival, _column(raw, "AB_PROGNOSE_STATUS")),
            "cancelled": _column(raw, "FAELLT_AUS_TF").str.lower().eq("true"),
            "sloid": _column(raw, "SLOID"),
        }
    )
    return frame


def _prepare_live(files: list[Path]) -> pd.DataFrame:
    frame = pd.concat(
        [pd.read_csv(path, dtype={"station_id": "string", "journey_id": "string", "line": "string"})
         for path in files],
        ignore_index=True,
    )
    for column in ["scheduled_time", "reported_time", "observed_at"]:
        frame[column] = pd.to_datetime(_column(frame, column), format="mixed", errors="coerce", utc=True)
    # The stationboard endpoint defaults to departures, including old snapshots.
    frame["event_type"] = _column(frame, "event_type").replace("departure_or_arrival", "departure").fillna("departure")
    frame["cancelled"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    frame["snapshot_lead_minutes"] = (frame["scheduled_time"] - frame["observed_at"]).dt.total_seconds() / 60
    frame["reported_status"] = "live_prognosis"
    return frame


def prepare_transport(source: str = "live") -> pd.DataFrame:
    settings = load_settings()
    PATHS.ensure()
    stations = load_station_panel()
    stations["station_id"] = stations["station_id"].map(normalize_station_id)
    if source == "actuals":
        files = sorted((PATHS.raw / "actuals_v2").glob("*_selected_stations.csv"))
        if not files:
            raise FileNotFoundError("No selected Actual data v2 files found.")
        frame = _prepare_actuals(files)
    elif source == "live":
        legacy = PATHS.interim / "live_observations.csv"
        files = ([legacy] if legacy.exists() else []) + sorted(
            (PATHS.interim / "live_snapshots").glob("stationboards_*.csv")
        )
        if not files:
            raise FileNotFoundError("Run collect-live first.")
        frame = _prepare_live(files)
    else:
        raise ValueError("source must be 'live' or 'actuals'")

    raw_count = len(frame)
    audit_rows = [["raw_rows", raw_count], ["station_panel_rows", len(stations)]]
    if stations["station_id"].isna().any() or stations["station_id"].duplicated().any():
        raise ValueError("Station panel must contain one nonmissing row per normalized station_id.")
    station_columns = [
        col for col in ["station_id", "station_name", "region", "canton", "station_type", "latitude", "longitude"]
        if col in stations
    ]
    frame["station_id"] = frame["station_id"].map(normalize_station_id)
    frame = frame.drop(columns=[col for col in ["region", "canton", "station_type"] if col in frame], errors="ignore")
    frame = frame.merge(stations[station_columns], on="station_id", how="left", suffixes=("", "_panel"), validate="many_to_one", indicator=True)
    audit_rows.extend([
        ["rows_after_station_join", len(frame)],
        ["station_join_matched", int(frame["_merge"].eq("both").sum())],
        ["station_join_unmatched", int(frame["_merge"].eq("left_only").sum())],
        ["station_join_row_gain_or_loss", len(frame) - raw_count],
    ])
    frame = frame.drop(columns="_merge")
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
    event_columns = ["data_source", "station_id", "journey_id", "scheduled_time", "event_type", "destination", "operator", "line"]
    frame["observation_id"] = [
        stable_id(values) for values in zip(*[_column(frame, col) for col in event_columns], strict=True)
    ]
    frame["snapshot_count"] = frame.groupby("observation_id")["observation_id"].transform("size")
    before_dedup = len(frame)
    if "observed_at" in frame:
        # Input files can be appended or reimported out of order. Missing
        # timestamps cannot displace a known latest snapshot.
        frame = frame.sort_values("observed_at", kind="stable", na_position="first")
    frame = frame.drop_duplicates("observation_id", keep="last")
    after_dedup = len(frame)
    audit_rows.extend([
        ["duplicate_rows_removed", before_dedup - after_dedup],
        ["unique_event_keys", after_dedup],
        ["rows_before_plausibility_filter", after_dedup],
    ])
    # Sequential exclusion counts reconcile exactly to raw_rows - prepared_rows.
    invalid_masks = {
        "cancelled": _column(frame, "cancelled").astype("string").str.lower().eq("true").fillna(False),
        "invalid_scheduled_time": frame["scheduled_time"].isna(),
        "missing_delay": frame["delay_minutes_signed"].isna(),
        "nonfinite_delay": ~np.isfinite(frame["delay_minutes_signed"]),
        "implausible_signed_delay": frame["delay_minutes_signed"].abs().gt(settings["maximum_plausible_delay_minutes"]),
        "unmatched_station": frame["region"].isna(),
    }
    excluded = pd.Series(False, index=frame.index)
    for reason, mask in invalid_masks.items():
        removed = mask & ~excluded
        audit_rows.append([f"excluded_{reason}", int(removed.sum())])
        excluded |= mask
    frame = frame.loc[~excluded].copy()
    frame["is_delayed_5"] = frame["delay_minutes"].ge(settings["delay_threshold_minutes"]).astype(int)
    frame = add_time_features(frame)
    frame = frame.sort_values(["scheduled_time", "station_id", "journey_id"])
    output = PATHS.interim / "transport_prepared.csv"
    frame.to_csv(output, index=False)
    audit = pd.DataFrame(
        [*audit_rows,
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
    PATHS.ensure()
    settings = load_settings()
    transport = pd.read_csv(PATHS.interim / "transport_prepared.csv", dtype={"station_id": "string"})
    weather = pd.read_csv(PATHS.interim / "weather_hourly.csv", dtype={"station_id": "string"})
    weather_input_rows = len(weather)
    keys = ["station_id", "observation_hour"]
    for frame in [transport, weather]:
        frame["station_id"] = frame["station_id"].map(normalize_station_id)
        frame["observation_hour"] = pd.to_datetime(
            frame["observation_hour"], format="mixed", errors="coerce", utc=True
        ).dt.floor("h")
    if transport[keys].isna().any(axis=None):
        raise ValueError("Prepared transport has missing station-hour join keys; run prepare again.")
    weather_invalid_keys = int(weather[keys].isna().any(axis=1).sum())
    weather = weather.dropna(subset=keys)
    weather = weather.drop_duplicates()
    if weather.duplicated(keys).any():
        raise ValueError("Weather contains conflicting duplicate station-hour keys; resolve them before joining.")
    variables = settings["weather_hourly_variables"]
    missing_columns = set(variables) - set(weather)
    if missing_columns:
        raise ValueError(f"Weather data is missing required columns: {sorted(missing_columns)}")
    for column in variables:
        weather[column] = pd.to_numeric(weather[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    before = len(transport)
    merged = transport.merge(
        weather,
        on=keys,
        how="left",
        validate="many_to_one",
        suffixes=("", "_weather"),
        indicator=True,
    )
    matched = int(merged["_merge"].eq("both").sum())
    merged["weather_matched"] = merged["_merge"].eq("both")
    merged["weather_complete"] = merged[variables].notna().all(axis=1)
    unmatched = merged.loc[~merged["weather_matched"], keys].drop_duplicates()
    unmatched.to_csv(PATHS.tables / "weather_unmatched_keys.csv", index=False)
    merged = merged.drop(columns="_merge")
    merged["observation_hour"] = merged["observation_hour"].dt.strftime("%Y-%m-%dT%H:00:00%z")
    output = PATHS.processed / "model_data.csv"
    merged.to_csv(output, index=False)
    audit_path = PATHS.tables / "integration_audit.csv"
    pd.DataFrame(
        {
            "metric": [
                "transport_rows_before_weather_join", "rows_after_weather_join",
                "weather_matches", "weather_unmatched", "row_gain_or_loss",
                "weather_input_rows", "weather_invalid_key_rows", "weather_unique_keys",
                "weather_exact_duplicate_rows_removed", "transport_unique_station_hour_keys",
                "weather_matched_but_incomplete", "weather_complete_rows",
                *[f"missing_{column}" for column in variables],
            ],
            "value": [
                before, len(merged), matched, len(merged) - matched, len(merged) - before,
                weather_input_rows, weather_invalid_keys, len(weather),
                weather_input_rows - weather_invalid_keys - len(weather),
                len(transport[keys].drop_duplicates()),
                int((merged["weather_matched"] & ~merged["weather_complete"]).sum()),
                int(merged["weather_complete"].sum()),
                *[int(merged[column].isna().sum()) for column in variables],
            ],
        }
    ).to_csv(audit_path, index=False)
    merged.groupby(["region", "transport_mode"], dropna=False).agg(
        observations=("observation_id", "size"),
        weather_matched=("weather_matched", "sum"),
        weather_complete=("weather_complete", "sum"),
    ).reset_index().to_csv(PATHS.tables / "weather_coverage_by_group.csv", index=False)
    print(f"Weather matched for {matched:,}/{len(merged):,} rows; row count change: {len(merged) - before:+,}")
    return merged
