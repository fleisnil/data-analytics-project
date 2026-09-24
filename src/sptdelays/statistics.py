from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from .settings import PATHS


def _eta_squared(groups: list[np.ndarray]) -> float:
    values = np.concatenate(groups)
    grand_mean = values.mean()
    between = sum(len(group) * (group.mean() - grand_mean) ** 2 for group in groups)
    total = ((values - grand_mean) ** 2).sum()
    return float(between / total) if total else 0.0


def _anova(frame: pd.DataFrame, group_col: str) -> dict:
    groups = [
        group["delay_minutes"].dropna().to_numpy()
        for _, group in frame.groupby(group_col, observed=True)
        if len(group["delay_minutes"].dropna()) >= 2
    ]
    statistic, p_value = np.nan, np.nan
    status = "insufficient_groups"
    if len(groups) >= 2:
        if np.unique(np.concatenate(groups)).size < 2:
            status = "constant_target"
        elif all(np.var(group) == 0 for group in groups):
            status = "no_within_group_variance"
        else:
            statistic, p_value = stats.f_oneway(*groups)
            status = "exploratory"
    return {
        "test": f"ANOVA by {group_col}",
        "statistic": statistic,
        "p_value": p_value,
        "effect_size": _eta_squared(groups) if groups else np.nan,
        "effect_size_name": "eta_squared",
        "n": sum(map(len, groups)),
        "status": status,
        "unit": "station_call",
        "assumption_note": "Classical ANOVA assumes independent residuals and equal group variances; skew and repeated station calls make this exploratory.",
    }


def _chi_square(frame: pd.DataFrame, group_col: str) -> dict:
    table = pd.crosstab(frame[group_col], frame["is_delayed_5"])
    if table.shape[0] < 2 or table.shape[1] < 2:
        return {
            "test": f"Chi-square delayed>=5 by {group_col}",
            "statistic": np.nan,
            "p_value": np.nan,
            "effect_size": np.nan,
            "status": "insufficient_categories",
            "effect_size_name": "cramers_v",
            "n": int(table.to_numpy().sum()),
            "unit": "station_call",
        }
    # Pearson statistic without Yates correction also supplies Cramer's V consistently.
    statistic, p_value, _, expected = stats.chi2_contingency(table, correction=False)
    n = table.to_numpy().sum()
    denominator = n * max(1, min(table.shape[0] - 1, table.shape[1] - 1))
    cramers_v = math.sqrt(statistic / denominator) if denominator else np.nan
    return {
        "test": f"Chi-square delayed>=5 by {group_col}",
        "statistic": statistic,
        "p_value": p_value,
        "effect_size": cramers_v,
        "effect_size_name": "cramers_v",
        "n": int(n),
        "minimum_expected_count": float(expected.min()),
        "expected_cells_below_5_share": float((expected < 5).mean()),
        "status": "small_expected_counts" if (expected < 5).any() else "exploratory",
        "unit": "station_call",
        "assumption_note": "Approximate p-value; small expected cell counts and dependent station calls limit inference.",
    }


def run_statistical_tests(frame: pd.DataFrame) -> pd.DataFrame:
    PATHS.ensure()
    group_columns = [col for col in ["transport_mode", "region", "day_period"] if col in frame]
    results = [_anova(frame, col) for col in group_columns]
    results.extend([_chi_square(frame, col) for col in group_columns])
    for weather_col in ["precipitation", "wind_speed_10m", "temperature_2m"]:
        if weather_col not in frame:
            continue
        # The same station-hour weather value is repeated for many station calls.
        # Average the target first so a busy station-hour does not count as many weather samples.
        if {"station_id", "observation_hour"}.issubset(frame.columns):
            subset = (
                frame.groupby(["station_id", "observation_hour"])[[weather_col, "delay_minutes"]]
                .mean()
                .dropna()
            )
            unit = "station_hour_mean"
        else:
            subset = frame[[weather_col, "delay_minutes"]].dropna()
            unit = "station_call"
        if (
            len(subset) >= 3
            and subset[weather_col].nunique() > 1
            and subset["delay_minutes"].nunique() > 1
        ):
            statistic, p_value = stats.spearmanr(subset[weather_col], subset["delay_minutes"])
            status = "exploratory"
        else:
            statistic, p_value = np.nan, np.nan
            status = "insufficient_or_constant_data"
        results.append(
            {
                "test": f"Spearman delay vs {weather_col}",
                "statistic": statistic,
                "p_value": p_value,
                "effect_size": statistic,
                "effect_size_name": "spearman_rho",
                "n": len(subset),
                "unit": unit,
                "status": status,
                "assumption_note": "Station-hour averaging reduces weather pseudoreplication; remaining serial/spatial dependence is not removed.",
            }
        )
    output = pd.DataFrame(results)
    output["p_value_holm"] = np.nan
    finite = np.isfinite(output["p_value"])
    if finite.any():
        output.loc[finite, "p_value_holm"] = multipletests(
            output.loc[finite, "p_value"], method="holm"
        )[1]
    # Missing/undefined tests are not silently described as non-significant.
    output["significant_at_0_05"] = output["p_value_holm"].lt(0.05).astype("boolean")
    output.loc[~finite, "significant_at_0_05"] = pd.NA
    output["multiple_testing"] = "Holm correction over finite p-values in this table"
    output["inference"] = (
        "Exploratory associations, not causal effects; correction does not fix dependence or invalid test assumptions."
    )
    output.to_csv(PATHS.tables / "statistical_tests.csv", index=False)
    return output
