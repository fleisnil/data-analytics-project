from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

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
    if len(groups) < 2:
        return {"test": f"ANOVA by {group_col}", "statistic": np.nan, "p_value": np.nan, "effect_size": np.nan}
    statistic, p_value = stats.f_oneway(*groups)
    return {
        "test": f"ANOVA by {group_col}",
        "statistic": statistic,
        "p_value": p_value,
        "effect_size": _eta_squared(groups),
    }


def _chi_square(frame: pd.DataFrame, group_col: str) -> dict:
    table = pd.crosstab(frame[group_col], frame["is_delayed_5"])
    if table.shape[0] < 2 or table.shape[1] < 2:
        return {"test": f"Chi-square delayed>=5 by {group_col}", "statistic": np.nan, "p_value": np.nan, "effect_size": np.nan}
    statistic, p_value, _, _ = stats.chi2_contingency(table)
    n = table.to_numpy().sum()
    denominator = n * max(1, min(table.shape[0] - 1, table.shape[1] - 1))
    cramers_v = math.sqrt(statistic / denominator) if denominator else np.nan
    return {
        "test": f"Chi-square delayed>=5 by {group_col}",
        "statistic": statistic,
        "p_value": p_value,
        "effect_size": cramers_v,
    }


def run_statistical_tests(frame: pd.DataFrame) -> pd.DataFrame:
    results = [_anova(frame, "transport_mode"), _anova(frame, "region")]
    results.extend([_chi_square(frame, "transport_mode"), _chi_square(frame, "region")])
    for weather_col in ["precipitation", "wind_speed_10m", "temperature_2m"]:
        if weather_col not in frame:
            continue
        subset = frame[[weather_col, "delay_minutes"]].dropna()
        if len(subset) >= 3 and subset[weather_col].nunique() > 1:
            statistic, p_value = stats.spearmanr(subset[weather_col], subset["delay_minutes"])
        else:
            statistic, p_value = np.nan, np.nan
        results.append(
            {
                "test": f"Spearman delay vs {weather_col}",
                "statistic": statistic,
                "p_value": p_value,
                "effect_size": statistic,
            }
        )
    output = pd.DataFrame(results)
    output["significant_at_0_05"] = output["p_value"].lt(0.05)
    output.to_csv(PATHS.tables / "statistical_tests.csv", index=False)
    return output

