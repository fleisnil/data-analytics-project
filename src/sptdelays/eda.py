from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from .settings import PATHS
from .statistics import run_statistical_tests

plt.switch_backend("Agg")


def _save(name: str) -> None:
    plt.tight_layout()
    plt.savefig(PATHS.figures / name, dpi=180, bbox_inches="tight")
    plt.close()


def _daily_region_coverage(data: pd.DataFrame, regions: list[str]) -> pd.DataFrame:
    """Include zero-observation days, not only region-days present in the data."""
    dates = pd.to_datetime(data["service_date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("Valid service dates are required for the region-day coverage table.")
    all_dates = pd.date_range(dates.min(), dates.max(), freq="D").strftime("%Y-%m-%d")
    all_regions = sorted(set(regions) | set(data["region"].dropna().astype(str)))
    index = pd.MultiIndex.from_product(
        [all_dates, all_regions], names=["service_date", "region"]
    )
    observed = data.groupby(["service_date", "region"], observed=True).agg(
        station_calls=("observation_id", "size"),
        stations=("station_id", "nunique"),
        transport_modes=("transport_mode", "nunique"),
        day_periods=("day_period", "nunique"),
        mean_delay=("delay_minutes", "mean"),
    )
    result = observed.reindex(index).reset_index()
    for column in ["station_calls", "stations", "transport_modes", "day_periods"]:
        result[column] = result[column].fillna(0).astype(int)
    result["has_usable_calls"] = result["station_calls"].gt(0)
    return result


def run_eda() -> None:
    PATHS.ensure()
    data = pd.read_csv(PATHS.processed / "model_data.csv", dtype={"station_id": "string"})
    if data.empty:
        raise ValueError("The processed dataset is empty.")
    configured_regions = pd.read_csv(PATHS.config / "stations.csv")["region"].dropna().tolist()
    _daily_region_coverage(data, configured_regions).to_csv(
        PATHS.tables / "daily_region_coverage.csv", index=False
    )
    sns.set_theme(style="whitegrid", context="notebook")
    summary = data["delay_minutes"].describe(percentiles=[0.5, 0.75, 0.9, 0.95, 0.99])
    summary.rename("value").to_csv(PATHS.tables / "delay_summary.csv")
    group_summary = (
        data.groupby(["region", "transport_mode", "day_period"], observed=True)
        .agg(
            observations=("observation_id", "size"),
            mean_delay=("delay_minutes", "mean"),
            median_delay=("delay_minutes", "median"),
            p90_delay=("delay_minutes", lambda values: values.quantile(0.90)),
            delayed_5_rate=("is_delayed_5", "mean"),
        )
        .reset_index()
    )
    group_summary.to_csv(PATHS.tables / "delay_by_region_mode_period.csv", index=False)
    missing = data.isna().mean().sort_values(ascending=False).rename("missing_share")
    missing.to_csv(PATHS.tables / "missingness.csv")
    station_days = data.groupby(["station_id", "service_date", "region"], observed=True).agg(
        observations=("observation_id", "size"), mean_delay=("delay_minutes", "mean"),
        delayed_5_rate=("is_delayed_5", "mean"),
    ).reset_index()
    station_days.to_csv(PATHS.tables / "station_day_summary.csv", index=False)
    station_means = data.groupby(["region", "station_id"], observed=True)["delay_minutes"].mean()
    regional = data.groupby("region", observed=True).agg(
        observations=("observation_id", "size"), stations=("station_id", "nunique"),
        service_dates=("service_date", "nunique"), call_weighted_mean_delay=("delay_minutes", "mean"),
    )
    regional["equal_station_weight_mean_delay"] = station_means.groupby("region").mean()
    regional.to_csv(PATHS.tables / "regional_weighting_comparison.csv")
    coverage = pd.crosstab(data["region"], data["transport_mode"])
    coverage.to_csv(PATHS.tables / "region_mode_coverage.csv")
    weather_cols = [c for c in ["precipitation", "temperature_2m", "wind_speed_10m"] if c in data]
    if weather_cols:
        data.assign(weather_complete=data[weather_cols].notna().all(axis=1)).groupby(
            ["region", "transport_mode"], observed=True
        ).agg(observations=("observation_id", "size"),
              weather_complete_share=("weather_complete", "mean")).to_csv(
                  PATHS.tables / "weather_coverage_by_group.csv"
              )

    clipped = data["delay_minutes"].clip(upper=30)
    sns.histplot(clipped, bins=31)
    plt.xlabel("Reported delay (minutes, clipped at 30)")
    plt.ylabel("Station calls")
    plt.title("Distribution of reported delays")
    _save("01_delay_distribution.png")

    plt.figure(figsize=(10, 5))
    order = data.groupby("transport_mode")["delay_minutes"].median().sort_values().index
    sns.boxplot(data=data, x="transport_mode", y=data["delay_minutes"].clip(upper=30), order=order)
    plt.xlabel("Transport mode")
    plt.ylabel("Reported delay (minutes, clipped at 30)")
    plt.title("Delay distribution by transport mode")
    _save("02_delay_by_mode.png")

    plt.figure(figsize=(12, 6))
    region_order = data.groupby("region")["delay_minutes"].mean().sort_values().index
    sns.barplot(data=data, x="region", y="delay_minutes", order=region_order, errorbar=None)
    plt.xticks(rotation=30, ha="right")
    plt.xlabel("Region")
    plt.ylabel("Mean reported delay (minutes)")
    plt.title("Mean delay in the sampled calls by region (descriptive)")
    _save("03_mean_delay_by_region.png")

    pivot = data.pivot_table(
        index="transport_mode", columns="day_period", values="delay_minutes", aggfunc="mean"
    )
    plt.figure(figsize=(9, 5))
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="YlOrRd")
    plt.xlabel("Time period")
    plt.ylabel("Transport mode")
    plt.title("Mean delay by mode and time period")
    _save("04_mode_time_heatmap.png")

    plt.figure(figsize=(9, 5))
    sns.heatmap(coverage, annot=True, fmt="d", cmap="Blues")
    plt.xlabel("Transport mode")
    plt.ylabel("Region")
    plt.title("Sample coverage: station calls by region and mode")
    _save("08_region_mode_coverage.png")

    daily = data.groupby("service_date", observed=True).agg(
        observations=("observation_id", "size"), mean_delay=("delay_minutes", "mean"),
        stations=("station_id", "nunique"),
    ).reset_index()
    daily.to_csv(PATHS.tables / "daily_coverage_delay.csv", index=False)
    plt.figure(figsize=(10, 4))
    plt.plot(pd.to_datetime(daily["service_date"]), daily["mean_delay"], marker="o")
    plt.xlabel("Service date")
    plt.ylabel("Mean reported delay (minutes)")
    plt.title("Daily delay in the sampled station calls")
    plt.gcf().autofmt_xdate()
    _save("07_daily_delay.png")

    if "precipitation" in data and data["precipitation"].notna().any():
        sample = data.sample(min(len(data), 5000), random_state=42)
        plt.figure(figsize=(8, 5))
        sns.scatterplot(
            data=sample,
            x="precipitation",
            y=sample["delay_minutes"].clip(upper=30),
            hue="transport_mode",
            alpha=0.35,
        )
        plt.xlabel("Hourly precipitation (mm)")
        plt.ylabel("Reported delay (minutes, clipped at 30)")
        plt.title("Delay and precipitation by transport mode")
        _save("05_delay_precipitation.png")

    run_statistical_tests(data)
    print("EDA figures, summaries and p-value tests created.")
