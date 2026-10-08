#!/usr/bin/env python3
"""
Statistical analysis for the integrated OJP + MeteoSwiss dataset.

The script focuses on associations rather than causal effects. Weather
correlations are calculated on city + weather-timestamp aggregates so the same
weather measurement is not counted once for every departure sharing it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


DATASET_PATH = Path("data/processed/analysis_dataset.csv")
TABLE_DIR = Path("results/tables")

WEATHER_COLUMNS = [
    "temperature_c",
    "precipitation_mm_10min",
    "relative_humidity_pct",
    "wind_speed_kmh_10min",
    "wind_gust_kmh",
]


def load_dataset(path: Path = DATASET_PATH) -> pd.DataFrame:
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
        "reference_timestamp",
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

    df["predicted_delay_minutes"] = pd.to_numeric(
        df["predicted_delay_minutes"],
        errors="coerce",
    )
    df["reference_timestamp"] = pd.to_datetime(
        df["reference_timestamp"],
        utc=True,
        errors="coerce",
    )

    for column in WEATHER_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
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

    return df


def aggregate_for_weather_tests(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate departures that share one city/weather measurement.

    This reduces pseudo-replication in weather p-values because one
    MeteoSwiss reading can be matched to many departures.
    """
    required = [
        "city",
        "reference_timestamp",
        "predicted_delay_minutes",
    ] + [
        column
        for column in WEATHER_COLUMNS
        if column in df.columns
    ]

    work = df[required].dropna(
        subset=[
            "city",
            "reference_timestamp",
            "predicted_delay_minutes",
        ]
    ).copy()

    aggregations = {
        "mean_predicted_delay_minutes": (
            "predicted_delay_minutes",
            "mean",
        ),
        "observations": (
            "predicted_delay_minutes",
            "size",
        ),
    }

    for column in WEATHER_COLUMNS:
        if column in work.columns:
            aggregations[column] = (
                column,
                "first",
            )

    return (
        work.groupby(
            ["city", "reference_timestamp"],
            as_index=False,
        )
        .agg(**aggregations)
        .sort_values(
            ["city", "reference_timestamp"]
        )
        .reset_index(drop=True)
    )


def spearman_weather_tests(
    aggregated: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate Spearman correlations overall and after within-city centering.

    Within-city centering reduces simple between-region confounding from
    persistent differences in weather and baseline delay levels.
    """
    rows = []

    for column in WEATHER_COLUMNS:
        if column not in aggregated.columns:
            continue

        overall = aggregated[
            [
                column,
                "mean_predicted_delay_minutes",
            ]
        ].dropna()

        if (
            len(overall) >= 3
            and overall[column].nunique() >= 2
        ):
            rho, p_value = stats.spearmanr(
                overall[column],
                overall[
                    "mean_predicted_delay_minutes"
                ],
            )
        else:
            rho, p_value = np.nan, np.nan

        rows.append(
            {
                "scope": (
                    "overall_city_weather_aggregate"
                ),
                "weather_variable": column,
                "n_city_weather_groups": len(
                    overall
                ),
                "spearman_rho": rho,
                "p_value": p_value,
            }
        )

        centered = aggregated[
            [
                "city",
                column,
                "mean_predicted_delay_minutes",
            ]
        ].dropna().copy()

        centered["weather_centered"] = (
            centered[column]
            - centered.groupby("city")[
                column
            ].transform("mean")
        )
        centered["delay_centered"] = (
            centered[
                "mean_predicted_delay_minutes"
            ]
            - centered.groupby("city")[
                "mean_predicted_delay_minutes"
            ].transform("mean")
        )

        if (
            len(centered) >= 3
            and centered[
                "weather_centered"
            ].nunique()
            >= 2
        ):
            rho, p_value = stats.spearmanr(
                centered["weather_centered"],
                centered["delay_centered"],
            )
        else:
            rho, p_value = np.nan, np.nan

        rows.append(
            {
                "scope": "within_city_centered",
                "weather_variable": column,
                "n_city_weather_groups": len(
                    centered
                ),
                "spearman_rho": rho,
                "p_value": p_value,
            }
        )

    result = pd.DataFrame(rows)

    if not result.empty:
        result["significant_0_05"] = (
            result["p_value"] < 0.05
        )
        result["spearman_rho"] = (
            result["spearman_rho"].round(4)
        )

    return result


def kruskal_group_test(
    df: pd.DataFrame,
    group_column: str,
) -> dict:
    work = df[
        [
            group_column,
            "predicted_delay_minutes",
        ]
    ].dropna()

    groups = [
        group[
            "predicted_delay_minutes"
        ].to_numpy()
        for _, group in work.groupby(
            group_column,
            observed=True,
        )
        if len(group) > 0
    ]

    if len(groups) < 2:
        return {
            "test": "Kruskal-Wallis",
            "group_variable": group_column,
            "groups": len(groups),
            "n": len(work),
            "statistic": np.nan,
            "p_value": np.nan,
            "epsilon_squared": np.nan,
        }

    statistic, p_value = stats.kruskal(
        *groups
    )
    k = len(groups)
    n = len(work)

    epsilon_squared = (
        (statistic - k + 1) / (n - k)
        if n > k
        else np.nan
    )

    return {
        "test": "Kruskal-Wallis",
        "group_variable": group_column,
        "groups": k,
        "n": n,
        "statistic": statistic,
        "p_value": p_value,
        "epsilon_squared": epsilon_squared,
    }


def chi_square_test(
    df: pd.DataFrame,
    group_column: str,
) -> dict:
    work = df[
        [
            group_column,
            "is_predicted_delayed_5min",
        ]
    ].dropna()

    contingency = pd.crosstab(
        work[group_column],
        work[
            "is_predicted_delayed_5min"
        ],
    )

    if (
        contingency.shape[0] < 2
        or contingency.shape[1] < 2
    ):
        return {
            "test": "Chi-square",
            "group_variable": group_column,
            "n": int(
                contingency.to_numpy().sum()
            ),
            "statistic": np.nan,
            "degrees_of_freedom": np.nan,
            "p_value": np.nan,
            "cramers_v": np.nan,
            "min_expected_count": np.nan,
            "expected_counts_ge_5": False,
        }

    (
        statistic,
        p_value,
        dof,
        expected,
    ) = stats.chi2_contingency(
        contingency
    )

    n = contingency.to_numpy().sum()
    rows, cols = contingency.shape
    denominator = min(
        rows - 1,
        cols - 1,
    )

    cramers_v = (
        np.sqrt(
            (statistic / n)
            / denominator
        )
        if n > 0 and denominator > 0
        else np.nan
    )

    return {
        "test": "Chi-square",
        "group_variable": group_column,
        "n": int(n),
        "statistic": statistic,
        "degrees_of_freedom": dof,
        "p_value": p_value,
        "cramers_v": cramers_v,
        "min_expected_count": float(
            expected.min()
        ),
        "expected_counts_ge_5": bool(
            (expected >= 5).all()
        ),
    }


def wet_dry_test(
    aggregated: pd.DataFrame,
) -> pd.DataFrame:
    column = "precipitation_mm_10min"

    if column not in aggregated.columns:
        return pd.DataFrame()

    work = aggregated[
        [
            column,
            "mean_predicted_delay_minutes",
        ]
    ].dropna().copy()

    work["wet"] = work[column] > 0

    wet = work.loc[
        work["wet"],
        "mean_predicted_delay_minutes",
    ]
    dry = work.loc[
        ~work["wet"],
        "mean_predicted_delay_minutes",
    ]

    if (
        len(wet) > 0
        and len(dry) > 0
    ):
        (
            statistic,
            p_value,
        ) = stats.mannwhitneyu(
            wet,
            dry,
            alternative="two-sided",
        )
    else:
        statistic, p_value = (
            np.nan,
            np.nan,
        )

    return pd.DataFrame(
        [
            {
                "test": "Mann-Whitney U",
                "comparison": (
                    "wet_vs_dry_city_weather_groups"
                ),
                "wet_groups": len(wet),
                "dry_groups": len(dry),
                "wet_mean_delay_min": (
                    wet.mean()
                    if len(wet)
                    else np.nan
                ),
                "dry_mean_delay_min": (
                    dry.mean()
                    if len(dry)
                    else np.nan
                ),
                "statistic": statistic,
                "p_value": p_value,
            }
        ]
    )


def threshold_sensitivity(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Show class balance for candidate delay thresholds.

    This is used to justify the eventual modelling target instead of choosing
    a five-minute threshold without checking the observed class distribution.
    """
    delay = df[
        "predicted_delay_minutes"
    ].dropna()

    rows = []

    for threshold in [
        1,
        2,
        3,
        4,
        5,
    ]:
        positives = int(
            (delay >= threshold).sum()
        )

        rows.append(
            {
                "threshold_minutes": (
                    threshold
                ),
                "positive_cases": positives,
                "negative_cases": int(
                    len(delay) - positives
                ),
                "positive_share_pct": (
                    100
                    * positives
                    / len(delay)
                    if len(delay)
                    else np.nan
                ),
            }
        )

    result = pd.DataFrame(rows)
    result[
        "positive_share_pct"
    ] = result[
        "positive_share_pct"
    ].round(2)

    return result


def create_statistics_tables(
    df: pd.DataFrame,
    output_dir: Path = TABLE_DIR,
) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    aggregated = (
        aggregate_for_weather_tests(df)
    )

    correlations = (
        spearman_weather_tests(
            aggregated
        )
    )

    group_tests = pd.DataFrame(
        [
            kruskal_group_test(
                df,
                "transport_mode",
            ),
            kruskal_group_test(
                df,
                "city",
            ),
        ]
    )

    if not group_tests.empty:
        for column in [
            "statistic",
            "epsilon_squared",
        ]:
            group_tests[column] = (
                pd.to_numeric(
                    group_tests[column],
                    errors="coerce",
                ).round(6)
            )

    chi_square = pd.DataFrame(
        [
            chi_square_test(
                df,
                "transport_mode",
            ),
            chi_square_test(
                df,
                "city",
            ),
        ]
    )

    if not chi_square.empty:
        for column in [
            "statistic",
            "cramers_v",
            "min_expected_count",
        ]:
            chi_square[column] = (
                pd.to_numeric(
                    chi_square[column],
                    errors="coerce",
                ).round(6)
            )

    wet_dry = wet_dry_test(
        aggregated
    )

    if not wet_dry.empty:
        for column in [
            "wet_mean_delay_min",
            "dry_mean_delay_min",
            "statistic",
        ]:
            wet_dry[column] = (
                pd.to_numeric(
                    wet_dry[column],
                    errors="coerce",
                ).round(6)
            )

    thresholds = (
        threshold_sensitivity(df)
    )

    tables = {
        "stats_weather_correlations": (
            correlations
        ),
        "stats_group_tests": group_tests,
        "stats_chi_square": chi_square,
        "stats_wet_dry": wet_dry,
        "stats_delay_threshold_sensitivity": (
            thresholds
        ),
    }

    for name, table in tables.items():
        table.to_csv(
            output_dir / f"{name}.csv",
            index=False,
        )

    return tables


def main() -> int:
    print("=" * 72)
    print("STATISTICAL ANALYSIS")
    print("=" * 72)

    df = load_dataset()
    tables = create_statistics_tables(
        df
    )

    print(f"Rows: {len(df)}")

    print(
        "\nDelay-threshold sensitivity:"
    )
    print(
        tables[
            "stats_delay_threshold_sensitivity"
        ].to_string(index=False)
    )

    print(
        "\nKruskal-Wallis group tests:"
    )
    print(
        tables[
            "stats_group_tests"
        ].to_string(index=False)
    )

    print("\nChi-square tests:")
    print(
        tables[
            "stats_chi_square"
        ].to_string(index=False)
    )

    print(
        "\nWeather Spearman correlations:"
    )
    print(
        tables[
            "stats_weather_correlations"
        ].to_string(index=False)
    )

    if not tables[
        "stats_wet_dry"
    ].empty:
        print(
            "\nWet vs dry comparison:"
        )
        print(
            tables[
                "stats_wet_dry"
            ].to_string(index=False)
        )

    print(
        "\nInterpret p-values together "
        "with effect sizes, sample sizes "
        "and the observational design."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
