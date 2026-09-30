#!/usr/bin/env python3
"""
Exploratory data analysis for the integrated OJP + MeteoSwiss dataset.

Every run reads data/processed/analysis_dataset.csv and overwrites stable
CSV/PNG outputs. Because collection is still growing, outputs are descriptive
and provisional rather than causal conclusions.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DATASET_PATH = Path("data/processed/analysis_dataset.csv")
FIGURE_DIR = Path("results/figures")
TABLE_DIR = Path("results/tables")

WEEKDAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

WEATHER_COLUMNS = [
    "temperature_c",
    "precipitation_mm_10min",
    "relative_humidity_pct",
    "wind_speed_kmh_10min",
    "wind_gust_kmh",
    "station_pressure_hpa",
]


def load_analysis_dataset(
    path: Path = DATASET_PATH,
) -> pd.DataFrame:
    """Load and normalize the integrated analysis dataset."""
    if not path.exists():
        raise FileNotFoundError(
            f"Analysis dataset not found: {path}. "
            "Run sync_collection_data.py and build_dataset.py first."
        )

    df = pd.read_csv(path)

    required = [
        "city",
        "transport_mode",
        "predicted_delay_minutes",
        "collection_timestamp",
        "scheduled_departure",
    ]
    missing = [
        column
        for column in required
        if column not in df.columns
    ]
    if missing:
        raise ValueError(
            f"Analysis dataset missing required columns: {missing}"
        )

    for column in [
        "collection_timestamp",
        "scheduled_departure",
        "scheduled_departure_local",
        "reference_timestamp",
    ]:
        if column in df.columns:
            df[column] = pd.to_datetime(
                df[column],
                utc=True,
                errors="coerce",
            )

    df["predicted_delay_minutes"] = pd.to_numeric(
        df["predicted_delay_minutes"],
        errors="coerce",
    )

    if "is_predicted_delayed_5min" not in df.columns:
        df["is_predicted_delayed_5min"] = (
            df["predicted_delay_minutes"] >= 5
        )
    else:
        target = df["is_predicted_delayed_5min"]
        if target.dtype == object:
            df["is_predicted_delayed_5min"] = (
                target.astype(str)
                .str.strip()
                .str.lower()
                .map(
                    {
                        "true": True,
                        "false": False,
                        "1": True,
                        "0": False,
                    }
                )
            )
        else:
            df["is_predicted_delayed_5min"] = (
                pd.to_numeric(
                    target,
                    errors="coerce",
                ).astype("boolean")
            )

    for column in (
        WEATHER_COLUMNS
        + ["weather_time_gap_minutes", "hour"]
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    if "date" in df.columns:
        df["analysis_date"] = pd.to_datetime(
            df["date"],
            errors="coerce",
        )
    elif "scheduled_departure_local" in df.columns:
        df["analysis_date"] = (
            df["scheduled_departure_local"]
            .dt.tz_convert("Europe/Zurich")
            .dt.tz_localize(None)
            .dt.normalize()
        )
    else:
        df["analysis_date"] = (
            df["scheduled_departure"]
            .dt.tz_convert("Europe/Zurich")
            .dt.tz_localize(None)
            .dt.normalize()
        )

    if "weekday" not in df.columns:
        df["weekday"] = (
            df["analysis_date"].dt.day_name()
        )

    if "hour" not in df.columns:
        source = (
            "scheduled_departure_local"
            if "scheduled_departure_local" in df.columns
            else "scheduled_departure"
        )
        df["hour"] = (
            df[source]
            .dt.tz_convert("Europe/Zurich")
            .dt.hour
        )

    return df


def _safe_share(series: pd.Series) -> float:
    valid = series.dropna()
    if valid.empty:
        return np.nan
    return float(
        valid.astype(bool).mean() * 100
    )


def build_overview_table(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Create a compact non-graphical EDA overview."""
    delay = (
        df["predicted_delay_minutes"]
        .dropna()
    )

    metrics = [
        ("rows", len(df)),
        ("cities", df["city"].nunique()),
        (
            "transport_modes",
            df["transport_mode"].nunique(),
        ),
        (
            "date_min",
            df["analysis_date"].min().date()
            if df["analysis_date"].notna().any()
            else pd.NA,
        ),
        (
            "date_max",
            df["analysis_date"].max().date()
            if df["analysis_date"].notna().any()
            else pd.NA,
        ),
        (
            "delay_mean_min",
            round(float(delay.mean()), 3)
            if not delay.empty
            else pd.NA,
        ),
        (
            "delay_median_min",
            round(float(delay.median()), 3)
            if not delay.empty
            else pd.NA,
        ),
        (
            "delay_p90_min",
            round(float(delay.quantile(0.90)), 3)
            if not delay.empty
            else pd.NA,
        ),
        (
            "delay_max_min",
            round(float(delay.max()), 3)
            if not delay.empty
            else pd.NA,
        ),
        (
            "negative_delay_share_pct",
            round(
                float((delay < 0).mean() * 100),
                2,
            )
            if not delay.empty
            else pd.NA,
        ),
        (
            "delayed_5min_share_pct",
            round(
                _safe_share(
                    df["is_predicted_delayed_5min"]
                ),
                2,
            ),
        ),
    ]

    if "weather_matched" in df.columns:
        weather_match = df["weather_matched"]
        if weather_match.dtype == object:
            weather_match = (
                weather_match.astype(str)
                .str.lower()
                .map(
                    {
                        "true": True,
                        "false": False,
                    }
                )
            )
        metrics.append(
            (
                "weather_match_rate_pct",
                round(
                    _safe_share(weather_match),
                    2,
                ),
            )
        )

    return pd.DataFrame(
        metrics,
        columns=["metric", "value"],
    )


def build_missingness_table(
    df: pd.DataFrame,
) -> pd.DataFrame:
    missing = df.isna().sum()
    result = pd.DataFrame(
        {
            "column": missing.index,
            "missing_count": missing.values,
            "missing_pct": (
                100 * missing.values / len(df)
                if len(df)
                else np.nan
            ),
        }
    )
    return result.sort_values(
        ["missing_pct", "column"],
        ascending=[False, True],
    ).reset_index(drop=True)


def build_city_mode_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:
    work = df.dropna(
        subset=[
            "city",
            "transport_mode",
            "predicted_delay_minutes",
        ]
    ).copy()

    result = (
        work.groupby(
            ["city", "transport_mode"],
            observed=True,
        )
        .agg(
            observations=(
                "predicted_delay_minutes",
                "size",
            ),
            avg_predicted_delay_min=(
                "predicted_delay_minutes",
                "mean",
            ),
            median_predicted_delay_min=(
                "predicted_delay_minutes",
                "median",
            ),
            p90_predicted_delay_min=(
                "predicted_delay_minutes",
                lambda s: s.quantile(0.90),
            ),
            delayed_5min_share_pct=(
                "is_predicted_delayed_5min",
                lambda s: _safe_share(s),
            ),
            negative_delay_share_pct=(
                "predicted_delay_minutes",
                lambda s: float(
                    (s < 0).mean() * 100
                ),
            ),
        )
        .reset_index()
    )

    numeric = result.select_dtypes(
        include="number"
    ).columns
    result[numeric] = result[numeric].round(2)
    return result


def build_hour_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:
    work = df.dropna(
        subset=[
            "hour",
            "transport_mode",
            "predicted_delay_minutes",
        ]
    ).copy()

    result = (
        work.groupby(
            ["hour", "transport_mode"],
            observed=True,
        )
        .agg(
            observations=(
                "predicted_delay_minutes",
                "size",
            ),
            avg_predicted_delay_min=(
                "predicted_delay_minutes",
                "mean",
            ),
            delayed_5min_share_pct=(
                "is_predicted_delayed_5min",
                lambda s: _safe_share(s),
            ),
        )
        .reset_index()
        .sort_values(
            ["hour", "transport_mode"]
        )
    )

    numeric = result.select_dtypes(
        include="number"
    ).columns
    result[numeric] = result[numeric].round(2)
    return result


def build_weather_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:
    available = [
        column
        for column in WEATHER_COLUMNS
        if column in df.columns
    ]

    rows = []
    for column in available:
        series = pd.to_numeric(
            df[column],
            errors="coerce",
        ).dropna()

        rows.append(
            {
                "variable": column,
                "observations": len(series),
                "mean": (
                    series.mean()
                    if not series.empty
                    else np.nan
                ),
                "median": (
                    series.median()
                    if not series.empty
                    else np.nan
                ),
                "min": (
                    series.min()
                    if not series.empty
                    else np.nan
                ),
                "max": (
                    series.max()
                    if not series.empty
                    else np.nan
                ),
                "std": (
                    series.std()
                    if len(series) > 1
                    else np.nan
                ),
            }
        )

    result = pd.DataFrame(rows)
    numeric = result.select_dtypes(
        include="number"
    ).columns
    if len(numeric):
        result[numeric] = result[numeric].round(3)
    return result


def create_summary_tables(
    df: pd.DataFrame,
    output_dir: Path = TABLE_DIR,
) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    tables = {
        "eda_overview": build_overview_table(df),
        "eda_missingness": (
            build_missingness_table(df)
        ),
        "eda_city_mode_summary": (
            build_city_mode_summary(df)
        ),
        "eda_hour_summary": (
            build_hour_summary(df)
        ),
        "eda_weather_summary": (
            build_weather_summary(df)
        ),
    }

    for name, table in tables.items():
        table.to_csv(
            output_dir / f"{name}.csv",
            index=False,
        )

    return tables


def _save_current_figure(
    output_dir: Path,
    filename: str,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    plt.tight_layout()
    plt.savefig(
        output_dir / filename,
        dpi=180,
        bbox_inches="tight",
    )
    plt.close()


def plot_delay_distribution(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    delay = (
        df["predicted_delay_minutes"]
        .dropna()
    )

    plt.figure(figsize=(8, 5))
    plt.hist(delay, bins=40)
    plt.axvline(
        5,
        linestyle="--",
        linewidth=1.5,
    )
    plt.xlabel("Predicted delay (minutes)")
    plt.ylabel("Observations")
    plt.title(
        "Distribution of predicted departure delay\n"
        "Dashed line = provisional 5-minute threshold"
    )
    _save_current_figure(
        output_dir,
        "01_delay_distribution.png",
    )


def plot_delay_rate_by_mode(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    rates = (
        df.dropna(
            subset=[
                "transport_mode",
                "is_predicted_delayed_5min",
            ]
        )
        .groupby(
            "transport_mode",
            observed=True,
        )["is_predicted_delayed_5min"]
        .mean()
        .mul(100)
        .sort_values(ascending=False)
    )

    plt.figure(figsize=(8, 5))
    rates.plot(kind="bar")
    plt.xlabel("Transport mode")
    plt.ylabel(
        "Share with predicted delay ≥ 5 min (%)"
    )
    plt.title(
        "Predicted delay rate by transport mode"
    )
    plt.xticks(rotation=0)
    _save_current_figure(
        output_dir,
        "02_delay_rate_by_mode.png",
    )


def plot_average_delay_by_city(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    values = (
        df.groupby(
            "city",
            observed=True,
        )["predicted_delay_minutes"]
        .mean()
        .sort_values(ascending=False)
    )

    plt.figure(figsize=(9, 5))
    values.plot(kind="bar")
    plt.xlabel("Region / city")
    plt.ylabel(
        "Average predicted delay (minutes)"
    )
    plt.title(
        "Average predicted departure delay by region"
    )
    plt.xticks(
        rotation=35,
        ha="right",
    )
    _save_current_figure(
        output_dir,
        "03_average_delay_by_city.png",
    )


def plot_delay_boxplot_by_mode(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    modes = sorted(
        df["transport_mode"]
        .dropna()
        .unique()
        .tolist()
    )
    values = [
        df.loc[
            df["transport_mode"] == mode,
            "predicted_delay_minutes",
        ]
        .dropna()
        .to_numpy()
        for mode in modes
    ]

    plt.figure(figsize=(8, 5))
    plt.boxplot(
        values,
        tick_labels=modes,
        showfliers=True,
    )
    plt.xlabel("Transport mode")
    plt.ylabel("Predicted delay (minutes)")
    plt.title(
        "Predicted delay distribution by transport mode"
    )
    _save_current_figure(
        output_dir,
        "04_delay_boxplot_by_mode.png",
    )


def plot_weekday_city_heatmap(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    work = df.dropna(
        subset=[
            "weekday",
            "city",
            "is_predicted_delayed_5min",
        ]
    ).copy()

    pivot = work.pivot_table(
        index="weekday",
        columns="city",
        values="is_predicted_delayed_5min",
        aggfunc="mean",
    ).mul(100)

    present_order = [
        day
        for day in WEEKDAY_ORDER
        if day in pivot.index
    ]
    pivot = pivot.reindex(
        present_order
    )

    plt.figure(
        figsize=(
            max(
                8,
                1.1 * max(
                    1,
                    len(pivot.columns),
                ),
            ),
            max(
                4,
                0.65 * max(
                    1,
                    len(pivot.index),
                ),
            ),
        )
    )

    image = plt.imshow(
        pivot.to_numpy(dtype=float),
        aspect="auto",
    )
    plt.colorbar(
        image,
        label=(
            "Predicted delay ≥ 5 min (%)"
        ),
    )
    plt.xticks(
        range(len(pivot.columns)),
        pivot.columns,
        rotation=35,
        ha="right",
    )
    plt.yticks(
        range(len(pivot.index)),
        pivot.index,
    )
    plt.title(
        "Predicted delay rate by weekday and region"
    )
    _save_current_figure(
        output_dir,
        "05_weekday_city_delay_heatmap.png",
    )


def plot_hourly_delay_pattern(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    hourly = (
        df.dropna(
            subset=[
                "hour",
                "transport_mode",
                "predicted_delay_minutes",
            ]
        )
        .groupby(
            ["hour", "transport_mode"],
            observed=True,
        )["predicted_delay_minutes"]
        .mean()
        .unstack("transport_mode")
        .sort_index()
    )

    plt.figure(figsize=(9, 5))
    for mode in hourly.columns:
        plt.plot(
            hourly.index,
            hourly[mode],
            marker="o",
            label=mode,
        )

    plt.xlabel(
        "Scheduled departure hour"
    )
    plt.ylabel(
        "Average predicted delay (minutes)"
    )
    plt.title(
        "Hourly predicted-delay pattern by transport mode"
    )
    plt.legend(title="Mode")
    _save_current_figure(
        output_dir,
        "06_hourly_delay_pattern.png",
    )


def plot_weather_relationship(
    df: pd.DataFrame,
    output_dir: Path,
    weather_column: str,
    filename: str,
    x_label: str,
) -> None:
    if weather_column not in df.columns:
        return

    work = df[
        [
            weather_column,
            "predicted_delay_minutes",
        ]
    ].dropna()

    if work.empty:
        return

    plt.figure(figsize=(8, 5))
    plt.scatter(
        work[weather_column],
        work["predicted_delay_minutes"],
        alpha=0.55,
    )
    plt.xlabel(x_label)
    plt.ylabel(
        "Predicted delay (minutes)"
    )
    plt.title(
        f"{x_label} vs predicted departure delay"
    )

    if work[weather_column].nunique() < 2:
        plt.text(
            0.5,
            0.95,
            (
                "No meaningful variation in this "
                "weather variable yet"
            ),
            transform=plt.gca().transAxes,
            ha="center",
            va="top",
        )

    _save_current_figure(
        output_dir,
        filename,
    )


def plot_daily_collection_coverage(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    daily = (
        df.dropna(
            subset=["analysis_date"]
        )
        .groupby("analysis_date")
        .size()
        .sort_index()
    )

    plt.figure(figsize=(9, 5))
    plt.plot(
        daily.index,
        daily.values,
        marker="o",
    )
    plt.xlabel("Date")
    plt.ylabel(
        "Selected journey/stop observations"
    )
    plt.title(
        "Analysis sample coverage over collection period"
    )
    plt.xticks(
        rotation=35,
        ha="right",
    )
    _save_current_figure(
        output_dir,
        "09_observations_over_time.png",
    )


def plot_daily_delay(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    daily = (
        df.dropna(
            subset=[
                "analysis_date",
                "predicted_delay_minutes",
            ]
        )
        .groupby(
            "analysis_date"
        )["predicted_delay_minutes"]
        .mean()
        .sort_index()
    )

    plt.figure(figsize=(9, 5))
    plt.plot(
        daily.index,
        daily.values,
        marker="o",
    )
    plt.xlabel("Date")
    plt.ylabel(
        "Average predicted delay (minutes)"
    )
    plt.title(
        "Average predicted delay over collection period"
    )
    plt.xticks(
        rotation=35,
        ha="right",
    )
    _save_current_figure(
        output_dir,
        "10_daily_average_delay.png",
    )


def plot_sample_balance(
    df: pd.DataFrame,
    output_dir: Path,
) -> None:
    balance = (
        df.groupby(
            ["city", "transport_mode"],
            observed=True,
        )
        .size()
        .unstack(
            "transport_mode",
            fill_value=0,
        )
    )

    plt.figure(figsize=(10, 5))
    balance.plot(
        kind="bar",
        ax=plt.gca(),
    )
    plt.xlabel("Region / city")
    plt.ylabel(
        "Selected observations"
    )
    plt.title(
        "Sample balance by region and transport mode"
    )
    plt.xticks(
        rotation=35,
        ha="right",
    )
    plt.legend(title="Mode")
    _save_current_figure(
        output_dir,
        "11_sample_balance_city_mode.png",
    )


def create_figures(
    df: pd.DataFrame,
    output_dir: Path = FIGURE_DIR,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    plot_delay_distribution(
        df,
        output_dir,
    )
    plot_delay_rate_by_mode(
        df,
        output_dir,
    )
    plot_average_delay_by_city(
        df,
        output_dir,
    )
    plot_delay_boxplot_by_mode(
        df,
        output_dir,
    )
    plot_weekday_city_heatmap(
        df,
        output_dir,
    )
    plot_hourly_delay_pattern(
        df,
        output_dir,
    )

    plot_weather_relationship(
        df,
        output_dir,
        "temperature_c",
        "07_temperature_vs_delay.png",
        "Temperature (°C)",
    )
    plot_weather_relationship(
        df,
        output_dir,
        "precipitation_mm_10min",
        "08_precipitation_vs_delay.png",
        "10-minute precipitation (mm)",
    )

    plot_daily_collection_coverage(
        df,
        output_dir,
    )
    plot_daily_delay(
        df,
        output_dir,
    )
    plot_sample_balance(
        df,
        output_dir,
    )


def main() -> int:
    print("=" * 72)
    print("EXPLORATORY DATA ANALYSIS")
    print("=" * 72)

    df = load_analysis_dataset()

    tables = create_summary_tables(df)
    create_figures(df)

    overview = tables["eda_overview"]

    print(f"Rows: {len(df)}")
    print(
        f"Cities: "
        f"{df['city'].nunique()}"
    )
    print(
        "Transport modes: "
        + ", ".join(
            sorted(
                df["transport_mode"]
                .dropna()
                .astype(str)
                .unique()
            )
        )
    )
    print(
        f"Figures saved to: "
        f"{FIGURE_DIR}"
    )
    print(
        f"EDA tables saved to: "
        f"{TABLE_DIR}"
    )

    print("\nEDA overview:")
    print(
        overview.to_string(index=False)
    )
    print(
        "\nNote: the collection is still growing. "
        "Treat current patterns as descriptive "
        "and provisional."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
