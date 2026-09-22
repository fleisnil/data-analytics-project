#!/usr/bin/env python3
"""
Build the first integrated OJP + MeteoSwiss analysis dataset.

Pipeline:
1. Load all combined OJP snapshot CSV files.
2. Keep one consistent pre-departure observation per journey/stop.
3. Load the complete 10-minute MeteoSwiss measurements from saved raw files.
4. Deduplicate repeated weather downloads.
5. Join transport observations to the most recent weather measurement in the
   same city/region.
6. Save the integrated dataset and a transparent integration-quality report.

Important:
- OJP predicted_delay_minutes is based on EstimatedTime and is not labelled
  as a realised/actual delay.
- Missing real-time delay values are not converted to zero.
- Weather matching uses only a measurement at or before the OJP observation
  timestamp to avoid look-ahead.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd


OJP_SNAPSHOT_DIR = Path("data/interim/ojp_snapshots")
WEATHER_RAW_DIR = Path("data/raw/weather")
PROCESSED_DIR = Path("data/processed")
RESULTS_TABLE_DIR = Path("results/tables")

OUTPUT_DATASET = PROCESSED_DIR / "analysis_dataset.csv"
OUTPUT_REPORT = RESULTS_TABLE_DIR / "data_integration_report.csv"

OBSERVATION_WINDOW_MIN = 5
OBSERVATION_WINDOW_MAX = 15
OBSERVATION_TARGET_MIN = 10
WEATHER_TOLERANCE_MINUTES = 30

JOURNEY_KEY = ["operating_day", "journey_ref", "station_id"]

WEATHER_STATIONS = {
    "SMA": {"city": "Zürich", "station_name": "Zürich / Fluntern"},
    "BER": {"city": "Bern", "station_name": "Bern / Zollikofen"},
    "BAS": {"city": "Basel", "station_name": "Basel / Binningen"},
    "LUZ": {"city": "Luzern", "station_name": "Luzern"},
    "STG": {"city": "St. Gallen", "station_name": "St. Gallen"},
    "PUY": {"city": "Lausanne", "station_name": "Pully"},
    "GVE": {"city": "Genève", "station_name": "Genève / Cointrin"},
    "LUG": {"city": "Lugano", "station_name": "Lugano"},
}

WEATHER_PARAMETER_MAP = {
    "tre200s0": "temperature_c",
    "rre150z0": "precipitation_mm_10min",
    "ure200s0": "relative_humidity_pct",
    "fu3010z0": "wind_speed_kmh_10min",
    "fu3010z1": "wind_gust_kmh",
    "prestas0": "station_pressure_hpa",
}


def read_semicolon_csv(path: Path) -> pd.DataFrame:
    """Read a MeteoSwiss semicolon-separated CSV with an encoding fallback."""
    content = path.read_bytes()
    last_error = None

    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = content.decode(encoding)
            df = pd.read_csv(io.StringIO(text), sep=";")
            break
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    else:
        raise ValueError(f"Could not read {path}: {last_error}")

    df.columns = (
        pd.Index(df.columns)
        .astype(str)
        .str.strip()
        .str.replace("'", "", regex=False)
        .str.replace('"', "", regex=False)
    )

    return df


def load_ojp_snapshots() -> pd.DataFrame:
    """Load and combine all OJP snapshot CSV files."""
    files = sorted(OJP_SNAPSHOT_DIR.glob("ojp_snapshot_*.csv"))

    if not files:
        raise FileNotFoundError(
            f"No OJP snapshots found in {OJP_SNAPSHOT_DIR.resolve()}"
        )

    frames = []

    for path in files:
        df = pd.read_csv(path)
        df["ojp_source_file"] = path.name
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)

    for column in [
        "collection_timestamp",
        "scheduled_departure",
        "estimated_departure",
    ]:
        if column in df.columns:
            df[column] = pd.to_datetime(
                df[column],
                utc=True,
                errors="coerce",
            )

    if "operating_day" in df.columns:
        df["operating_day"] = df["operating_day"].astype("string")

    df["predicted_delay_minutes"] = pd.to_numeric(
        df["predicted_delay_minutes"],
        errors="coerce",
    )

    if "minutes_until_departure" in df.columns:
        df["minutes_until_departure"] = pd.to_numeric(
            df["minutes_until_departure"],
            errors="coerce",
        )
    else:
        df["minutes_until_departure"] = (
            df["scheduled_departure"] - df["collection_timestamp"]
        ).dt.total_seconds() / 60

    return df


def select_transport_observations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep one pre-departure OJP observation per journey/stop.

    The chosen row is the available observation inside the configured window
    that is closest to the target number of minutes before departure.
    """
    required = JOURNEY_KEY + [
        "collection_timestamp",
        "scheduled_departure",
        "minutes_until_departure",
        "predicted_delay_minutes",
        "city",
    ]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"OJP data missing required columns: {missing}")

    eligible = df.dropna(
        subset=JOURNEY_KEY
        + [
            "collection_timestamp",
            "scheduled_departure",
            "predicted_delay_minutes",
            "city",
        ]
    ).copy()

    eligible = eligible[
        eligible["minutes_until_departure"].between(
            OBSERVATION_WINDOW_MIN,
            OBSERVATION_WINDOW_MAX,
            inclusive="both",
        )
    ].copy()

    eligible["observation_distance_to_target_min"] = (
        eligible["minutes_until_departure"] - OBSERVATION_TARGET_MIN
    ).abs()

    eligible = eligible.sort_values(
        JOURNEY_KEY
        + [
            "observation_distance_to_target_min",
            "collection_timestamp",
        ],
        ascending=[True, True, True, True, False],
    )

    selected = eligible.drop_duplicates(
        subset=JOURNEY_KEY,
        keep="first",
    ).copy()

    selected["is_predicted_delayed_5min"] = (
        selected["predicted_delay_minutes"] >= 5
    )

    return selected


def infer_weather_station(path: Path) -> tuple[str, dict]:
    """Infer the MeteoSwiss station code and project city from the file name."""
    station_abbr = path.stem.split("_")[0].upper()

    if station_abbr not in WEATHER_STATIONS:
        raise ValueError(
            f"Unknown MeteoSwiss station code {station_abbr} in {path}"
        )

    return station_abbr, WEATHER_STATIONS[station_abbr]


def load_weather_measurements() -> pd.DataFrame:
    """
    Load complete 10-minute weather series from all saved raw MeteoSwiss files.

    Repeated collector runs download overlapping measurements. For each
    city/station/timestamp, the row with the greatest number of available
    project weather parameters is retained; newer raw batches break ties.
    """
    files = sorted(WEATHER_RAW_DIR.glob("*/*.csv"))

    if not files:
        raise FileNotFoundError(
            f"No raw MeteoSwiss files found in {WEATHER_RAW_DIR.resolve()}"
        )

    frames = []

    for path in files:
        station_abbr, metadata = infer_weather_station(path)
        df = read_semicolon_csv(path)

        if "reference_timestamp" not in df.columns:
            if "REFERENCE_TS" in df.columns:
                df = df.rename(
                    columns={"REFERENCE_TS": "reference_timestamp"}
                )
            else:
                raise ValueError(
                    f"No reference_timestamp column in {path}"
                )

        df["reference_timestamp"] = pd.to_datetime(
            df["reference_timestamp"],
            format="%d.%m.%Y %H:%M",
            utc=True,
            errors="coerce",
        )

        df = df.dropna(subset=["reference_timestamp"]).copy()

        for source_column in WEATHER_PARAMETER_MAP:
            if source_column in df.columns:
                df[source_column] = pd.to_numeric(
                    df[source_column],
                    errors="coerce",
                )
            else:
                df[source_column] = pd.NA

        df["city"] = metadata["city"]
        df["weather_station_abbr"] = station_abbr
        df["weather_station_name"] = metadata["station_name"]
        df["weather_raw_batch"] = path.parent.name
        df["weather_source_file"] = str(path)

        keep_columns = [
            "city",
            "weather_station_abbr",
            "weather_station_name",
            "reference_timestamp",
            "weather_raw_batch",
            "weather_source_file",
        ] + list(WEATHER_PARAMETER_MAP.keys())

        frames.append(df[keep_columns])

    weather = pd.concat(frames, ignore_index=True)

    parameter_columns = list(WEATHER_PARAMETER_MAP.keys())
    weather["_weather_parameter_count"] = (
        weather[parameter_columns].notna().sum(axis=1)
    )

    weather = weather.sort_values(
        [
            "city",
            "weather_station_abbr",
            "reference_timestamp",
            "_weather_parameter_count",
            "weather_raw_batch",
        ],
        ascending=[True, True, True, False, False],
    )

    weather = weather.drop_duplicates(
        subset=[
            "city",
            "weather_station_abbr",
            "reference_timestamp",
        ],
        keep="first",
    ).copy()

    weather = weather.rename(columns=WEATHER_PARAMETER_MAP)
    weather = weather.drop(columns=["_weather_parameter_count"])

    return weather


def join_transport_weather(
    transport: pd.DataFrame,
    weather: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join each transport observation to the latest weather measurement at or
    before that OJP observation, within the configured tolerance.
    """
    # pandas.merge_asof requires the merge timestamp to be globally sorted.
    # city is still used as an exact grouping key via by.
    transport = transport.sort_values(
        ["collection_timestamp", "city"]
    ).copy()
    weather = weather.sort_values(
        ["reference_timestamp", "city"]
    ).copy()

    joined = pd.merge_asof(
        transport,
        weather,
        left_on="collection_timestamp",
        right_on="reference_timestamp",
        by="city",
        direction="backward",
        tolerance=pd.Timedelta(
            minutes=WEATHER_TOLERANCE_MINUTES
        ),
    )

    joined["weather_matched"] = (
        joined["reference_timestamp"].notna()
    )

    joined["weather_time_gap_minutes"] = (
        joined["collection_timestamp"]
        - joined["reference_timestamp"]
    ).dt.total_seconds() / 60

    return joined


def build_integration_report(
    ojp_raw: pd.DataFrame,
    selected: pd.DataFrame,
    weather: pd.DataFrame,
    joined: pd.DataFrame,
) -> pd.DataFrame:
    """Create transparent counts for the integration/join requirement."""
    raw_unique_journeys = (
        ojp_raw[JOURNEY_KEY]
        .dropna()
        .drop_duplicates()
        .shape[0]
    )

    rows_with_realtime = int(
        ojp_raw["predicted_delay_minutes"].notna().sum()
    )

    rows_in_window = int(
        (
            ojp_raw["minutes_until_departure"].between(
                OBSERVATION_WINDOW_MIN,
                OBSERVATION_WINDOW_MAX,
                inclusive="both",
            )
            & ojp_raw["predicted_delay_minutes"].notna()
        ).sum()
    )

    matched = int(joined["weather_matched"].sum())
    unmatched = int((~joined["weather_matched"]).sum())

    matched_gaps = joined.loc[
        joined["weather_matched"],
        "weather_time_gap_minutes",
    ]

    metrics = [
        (
            "ojp_snapshot_files",
            len(list(OJP_SNAPSHOT_DIR.glob("ojp_snapshot_*.csv"))),
        ),
        ("ojp_raw_rows", len(ojp_raw)),
        ("ojp_unique_journey_stops_raw", raw_unique_journeys),
        ("ojp_rows_with_realtime", rows_with_realtime),
        ("ojp_rows_in_5_to_15_min_window", rows_in_window),
        ("selected_unique_journey_stops", len(selected)),
        (
            "weather_raw_files",
            len(list(WEATHER_RAW_DIR.glob("*/*.csv"))),
        ),
        ("weather_unique_10min_measurements", len(weather)),
        ("joined_rows_total", len(joined)),
        ("weather_matched_rows", matched),
        ("weather_unmatched_rows", unmatched),
        (
            "weather_match_rate_pct",
            round(100 * matched / len(joined), 2)
            if len(joined)
            else 0.0,
        ),
        (
            "median_weather_gap_minutes",
            round(float(matched_gaps.median()), 2)
            if not matched_gaps.empty
            else pd.NA,
        ),
        (
            "max_weather_gap_minutes",
            round(float(matched_gaps.max()), 2)
            if not matched_gaps.empty
            else pd.NA,
        ),
    ]

    return pd.DataFrame(metrics, columns=["metric", "value"])


def main() -> int:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_TABLE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("BUILD OJP + METEOSWISS ANALYSIS DATASET")
    print("=" * 72)

    ojp_raw = load_ojp_snapshots()
    print(f"OJP raw rows: {len(ojp_raw)}")

    selected = select_transport_observations(ojp_raw)
    print(
        f"Selected journey/stop observations "
        f"({OBSERVATION_WINDOW_MIN}-{OBSERVATION_WINDOW_MAX} min before departure): "
        f"{len(selected)}"
    )

    weather = load_weather_measurements()
    print(f"Unique MeteoSwiss 10-minute measurements: {len(weather)}")

    joined = join_transport_weather(selected, weather)

    matched = int(joined["weather_matched"].sum())
    print(
        f"Weather matches: {matched}/{len(joined)} "
        f"({100 * matched / len(joined):.1f}%)"
        if len(joined)
        else "Weather matches: 0/0"
    )

    joined.to_csv(OUTPUT_DATASET, index=False)

    report = build_integration_report(
        ojp_raw=ojp_raw,
        selected=selected,
        weather=weather,
        joined=joined,
    )
    report.to_csv(OUTPUT_REPORT, index=False)

    print(f"\nSaved integrated dataset: {OUTPUT_DATASET}")
    print(f"Saved integration report: {OUTPUT_REPORT}")

    print("\nIntegration report:")
    print(report.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
