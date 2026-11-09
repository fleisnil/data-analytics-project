"""Chronological evaluation utilities for the OJP forecast-delay dataset."""

from __future__ import annotations

import numpy as np
import pandas as pd

TIME = "collection_timestamp"
DAY = "collection_date"
TARGET = "predicted_delay_minutes"
GROUPS = ["city", "transport_mode", "day_period"]


def with_time_groups(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    local = data[TIME].dt.tz_convert("Europe/Zurich")
    data[DAY] = local.dt.strftime("%Y-%m-%d")
    if "hour" in data:
        hour = data["hour"]
    else:
        hour = local.dt.hour
    data["day_period"] = np.select(
        [hour.between(6, 8), hour.between(9, 15), hour.between(16, 18)],
        ["morning_peak", "daytime", "evening_peak"],
        default="off_peak",
    )
    data.loc[hour.isna(), "day_period"] = "missing"
    return data


def _batch_ranges(data: pd.DataFrame) -> pd.DataFrame:
    if "batch_id" not in data:
        return pd.DataFrame(columns=["min", "max"])
    return data.groupby("batch_id", dropna=True)[TIME].agg(["min", "max"])


def _valid_boundaries(candidates, batches: pd.DataFrame) -> list:
    if batches.empty:
        return list(candidates)
    return [
        cutoff for cutoff in candidates
        if not ((batches["min"] < cutoff) & (batches["max"] >= cutoff)).any()
    ]


def date_boundaries(data: pd.DataFrame) -> list:
    first_by_day = data.groupby(DAY, sort=True)[TIME].min().iloc[1:]
    return _valid_boundaries(first_by_day, _batch_ranges(data))


def chronological_holdout(data: pd.DataFrame, fraction: float):
    if not 0 < fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1.")
    data = with_time_groups(data).sort_values(TIME, kind="stable")
    batches = _batch_ranges(data)
    if boundaries := date_boundaries(data):
        method = "collection_date"
    elif boundaries := _valid_boundaries(
        sorted(batches["min"].drop_duplicates())[1:], batches
    ):
        method = "batch_id"
    else:
        times = data[TIME].drop_duplicates().iloc[1:]
        boundaries = _valid_boundaries(times, batches)
        method = "timestamp"
    if not boundaries:
        raise ValueError("No strictly chronological split without dividing an OJP batch.")
    index = max(0, min(len(boundaries) - 1, int((len(boundaries) + 1) * fraction) - 1))
    cutoff = boundaries[index]
    return data[data[TIME] < cutoff].copy(), data[data[TIME] >= cutoff].copy(), method


def expanding_folds(development: pd.DataFrame, max_folds: int = 3):
    """Split development data only; every fold refits preprocessing and estimators."""
    if development[DAY].nunique() < 4:
        return []
    boundaries = date_boundaries(development)
    start_index = max(1, len(boundaries) // 2)
    tail = boundaries[start_index:]
    if not tail:
        return []
    positions = np.linspace(0, len(tail), min(max_folds, len(tail)) + 1, dtype=int)
    folds = []
    for start, end in zip(positions[:-1], positions[1:]):
        cutoff = tail[start]
        train = development[development[TIME] < cutoff]
        validation = development[development[TIME] >= cutoff]
        if end < len(tail):
            validation = validation[validation[TIME] < tail[end]]
        if len(train) >= 50 and not validation.empty:
            folds.append((train, validation))
    return folds


def group_median(train: pd.DataFrame, test: pd.DataFrame, min_group_size: int = 10):
    keys = [column for column in GROUPS if column in train and column in test]
    fallback = float(train[TARGET].median())
    if not keys:
        return np.full(len(test), fallback), np.ones(len(test), dtype=bool)
    stats = train.groupby(keys, dropna=True)[TARGET].agg(["size", "median"])
    reliable = stats.loc[stats["size"] >= min_group_size, "median"]
    # A merge preserves left order and also handles the single-group-key case.
    values = test[keys].merge(reliable.rename("_group_median"), how="left",
                             left_on=keys, right_index=True, validate="many_to_one")["_group_median"]
    return values.fillna(fallback).to_numpy(), values.isna().to_numpy()


def coverage_table(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for feature in [*GROUPS, "station_id", "station_type", "product_category"]:
        if feature not in test:
            continue
        training = train[feature].fillna("<missing>").astype(str).value_counts()
        for value, count in test[feature].fillna("<missing>").astype(str).value_counts().items():
            rows.append({"feature": feature, "value": value,
                         "train_rows": int(training.get(value, 0)), "test_rows": int(count),
                         "unseen_in_training": value not in training})
    return pd.DataFrame(rows, columns=[
        "feature", "value", "train_rows", "test_rows", "unseen_in_training",
    ])


def paired_day_comparison(predictions: pd.DataFrame, model: str, reference: str,
                          *, repetitions: int = 2000, seed: int = 42) -> list[dict]:
    """Pair predictions per row; resample whole dates, not individual OJP calls."""
    frame = predictions[[DAY, "actual_delay", f"pred_{model}", f"pred_{reference}"]].dropna()
    if frame.empty:
        return []
    err_model = frame[f"pred_{model}"] - frame["actual_delay"]
    err_reference = frame[f"pred_{reference}"] - frame["actual_delay"]
    blocks = pd.DataFrame({
        "date": frame[DAY], "n": 1, "abs_model": err_model.abs(),
        "abs_reference": err_reference.abs(), "sq_model": err_model**2,
        "sq_reference": err_reference**2,
    }).groupby("date").sum()
    values = blocks.to_numpy()
    totals = values.sum(axis=0)
    point = ((totals[1] - totals[2]) / totals[0],
             np.sqrt(totals[3] / totals[0]) - np.sqrt(totals[4] / totals[0]))
    intervals = [(np.nan, np.nan), (np.nan, np.nan)]
    if len(blocks) >= 5:
        sampled = np.random.default_rng(seed).integers(0, len(blocks), (repetitions, len(blocks)))
        draws = values[sampled].sum(axis=1)
        mae = (draws[:, 1] - draws[:, 2]) / draws[:, 0]
        rmse = np.sqrt(draws[:, 3] / draws[:, 0]) - np.sqrt(draws[:, 4] / draws[:, 0])
        intervals = [np.quantile(samples, [0.025, 0.975]) for samples in (mae, rmse)]
    return [
        {"model": model, "reference": reference, "metric": metric, "difference": difference,
         "ci_low": low, "ci_high": high, "test_dates": len(blocks), "observations": len(frame),
         "status": "evaluated" if len(blocks) >= 5 else "insufficient_test_dates"}
        for metric, difference, (low, high) in zip(("mae", "rmse"), point, intervals)
    ]
