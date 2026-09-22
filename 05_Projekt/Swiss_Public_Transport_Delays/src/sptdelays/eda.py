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


def run_eda() -> None:
    data = pd.read_csv(PATHS.processed / "model_data.csv", dtype={"station_id": "string"})
    if data.empty:
        raise ValueError("The processed dataset is empty.")
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
    sns.barplot(data=data, x="region", y="delay_minutes", order=region_order, errorbar=("ci", 95))
    plt.xticks(rotation=30, ha="right")
    plt.xlabel("Region")
    plt.ylabel("Mean reported delay (minutes)")
    plt.title("Mean delay by region with 95% confidence intervals")
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
