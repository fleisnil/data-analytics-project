"""Date-block validation and paired uncertainty, independent of model fitting."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pandas as pd


def rolling_date_splits(
    frame: pd.DataFrame, max_splits: int = 3,
) -> Iterator[tuple[pd.DataFrame, pd.DataFrame]]:
    """Expanding training windows; each later observed date is validated at most once.

    Call only with the development partition, never the final holdout. Unequal
    station-call counts make row-based TimeSeriesSplit inappropriate here.
    """
    if max_splits < 1:
        raise ValueError("max_splits must be positive")
    dates = pd.to_datetime(frame["service_date"], format="%Y-%m-%d", errors="coerce").dt.normalize()
    if dates.isna().any():
        raise ValueError("Valid service dates are required for temporal validation")
    unique = np.sort(dates.unique())
    if len(unique) < 4:
        return
    initial = max(2, len(unique) // 2)
    blocks = np.array_split(unique[initial:], min(max_splits, len(unique) - initial))
    # Materialize one fold at a time instead of retaining several dataset copies.
    for block in blocks:
        yield frame.loc[dates < block[0]].copy(), frame.loc[dates.isin(block)].copy()


def paired_day_comparison(
    frame: pd.DataFrame, reference_column: str, *, seed: int = 42,
    repetitions: int = 1000, minimum_days: int = 5,
) -> pd.DataFrame:
    """Whole-date paired bootstrap of RF minus reference MAE/RMSE.

    Negative differences favor RF. These are conditional intervals for the
    fixed fitted models, not prediction intervals or causal effects. Shared
    dependence inside a date is preserved; serial dependence across dates is not.
    """
    if repetitions < 100 or minimum_days < 2:
        raise ValueError("Use at least 100 replicates and at least two dates")
    dates = pd.to_datetime(frame["service_date"], format="%Y-%m-%d", errors="coerce").dt.normalize()
    values = frame[["delay_minutes", "predicted_delay", reference_column]].to_numpy(dtype=float)
    if len(frame) == 0 or dates.isna().any() or not np.isfinite(values).all():
        raise ValueError("Paired comparison requires nonempty, finite predictions and valid dates")
    errors = values[:, 1] - values[:, 0]
    reference_errors = values[:, 2] - values[:, 0]
    totals = pd.DataFrame({
        "date": dates.to_numpy(), "n": 1,
        "absolute": np.abs(errors), "reference_absolute": np.abs(reference_errors),
        "squared": errors ** 2, "reference_squared": reference_errors ** 2,
    }).groupby("date", sort=True).sum()
    n_days = len(totals)
    rows = []
    rng = np.random.default_rng(seed)
    # Sample aggregated whole days: memory stays bounded even for large call datasets.
    samples = np.empty((repetitions, 2)) if n_days >= minimum_days else None
    if samples is not None:
        day_totals = totals.to_numpy()
        for index in range(repetitions):
            total = day_totals[rng.integers(0, n_days, n_days)].sum(axis=0)
            count, absolute, ref_absolute, squared, ref_squared = total
            samples[index] = [(absolute - ref_absolute) / count,
                              np.sqrt(squared / count) - np.sqrt(ref_squared / count)]
    estimates = [np.abs(errors).mean() - np.abs(reference_errors).mean(),
                 np.sqrt(np.mean(errors ** 2)) - np.sqrt(np.mean(reference_errors ** 2))]
    for index, metric in enumerate(["mae", "rmse"]):
        low, high = (np.quantile(samples[:, index], [0.025, 0.975])
                     if samples is not None else (np.nan, np.nan))
        rows.append({
            "reference_prediction": reference_column, "metric": metric,
            "difference_rf_minus_reference": estimates[index], "ci_low": low, "ci_high": high,
            "test_rows": len(frame), "test_dates": n_days,
            "bootstrap_repetitions": repetitions if samples is not None else 0,
            "status": "exploratory_day_bootstrap" if samples is not None else "insufficient_test_dates",
            "minimum_test_dates": minimum_days,
            "interpretation": "Negative favors RF; 95% paired date-bootstrap interval conditional on fitted models. Not a causal or prediction interval; cross-day dependence and training uncertainty are not captured.",
        })
    return pd.DataFrame(rows)
