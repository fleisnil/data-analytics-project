from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .evaluation import paired_day_comparison, rolling_date_splits
from .settings import PATHS, load_settings

NUMERIC_FEATURES = [
    "scheduled_hour",
    "is_weekend",
    "is_peak",
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_gusts_10m",
    "snowfall",
]
CATEGORICAL_FEATURES = ["region", "transport_mode", "day_period", "weekday", "operator"]
GROUP_BASELINE_COLUMNS = ["region", "transport_mode", "day_period"]
GROUP_BASELINE_MIN_ROWS = 10
WEATHER_FEATURES = {"temperature_2m", "precipitation", "wind_speed_10m",
                    "wind_gusts_10m", "snowfall"}
PREDICTION_COLUMNS = {
    "random_forest": "predicted_delay",
    "forest_without_weather": "no_weather_delay",
    "mean_baseline": "baseline_delay",
    "group_mean_baseline": "group_baseline_delay",
}


def _metrics(y_true: pd.Series, y_pred: np.ndarray, label: str) -> dict:
    return {
        "group": label,
        "n": len(y_true),
        "rmse": mean_squared_error(y_true, y_pred) ** 0.5,
        "mae": mean_absolute_error(y_true, y_pred),
        "mean_error_pred_minus_actual": float(np.mean(y_pred - y_true.to_numpy())),
        "p90_absolute_error": float(np.quantile(np.abs(y_pred - y_true.to_numpy()), .9)),
        # R-squared is undefined for a constant target, even with multiple rows.
        "r2": r2_score(y_true, y_pred) if len(y_true) > 1 and y_true.nunique() > 1 else np.nan,
    }


def _split(frame: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out later whole dates (or whole timestamps for a one-day demo)."""
    del seed  # Kept for compatibility; chronological partitioning is deterministic.
    dates = pd.to_datetime(frame["service_date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("A valid service_date is required for chronological evaluation.")
    if dates.nunique() >= 2:
        split_values = dates
    else:
        split_values = pd.to_datetime(
            frame["scheduled_time"], utc=True, format="mixed", errors="coerce"
        )
    unique_values = sorted(split_values.dropna().unique())
    if split_values.isna().any() or len(unique_values) < 2:
        raise ValueError("At least two distinct valid scheduled times are required for a holdout.")
    split_index = max(1, min(len(unique_values) - 1, int(len(unique_values) * 0.8)))
    earlier = split_values < unique_values[split_index]
    return frame.loc[earlier].copy(), frame.loc[~earlier].copy()


def _make_pipeline(numeric: list[str], categorical: list[str], seed: int) -> Pipeline:
    """Learn medians and categories from training rows only."""
    transformer = ColumnTransformer(
        [
            ("numeric", SimpleImputer(strategy="median", keep_empty_features=True), numeric),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )
    return Pipeline(
        [
            ("features", transformer),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=5,
                    random_state=seed,
                    n_jobs=1,
                ),
            ),
        ]
    )


def _holdout_coverage(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Expose categories the fitted encoder has never encountered."""
    rows = []
    for column in columns:
        known = set(train[column].astype(str))
        unseen = ~test[column].astype(str).isin(known)
        rows.append(
            {
                "feature": column,
                "train_categories": len(known),
                "test_categories": test[column].nunique(),
                "unseen_test_categories": int(test.loc[unseen, column].nunique()),
                "unseen_test_values": ", ".join(sorted(test.loc[unseen, column].astype(str).unique())),
                "affected_test_rows": int(unseen.sum()),
                "test_rows": len(test),
                "affected_test_fraction": float(unseen.mean()),
            }
        )
    return pd.DataFrame(rows)


def _group_mean_baseline(
    train: pd.DataFrame, test: pd.DataFrame, *, min_rows: int = GROUP_BASELINE_MIN_ROWS
) -> tuple[np.ndarray, np.ndarray]:
    """Use only sufficiently supported training groups; otherwise use the training mean."""
    group_means = train.groupby(GROUP_BASELINE_COLUMNS)["delay_minutes"].agg(["mean", "size"])
    supported = group_means.loc[group_means["size"].ge(min_rows), "mean"]
    test_groups = pd.MultiIndex.from_frame(test[GROUP_BASELINE_COLUMNS])
    predictions = supported.reindex(test_groups).to_numpy(dtype=float)
    fallback = ~np.isfinite(predictions)
    predictions[fallback] = train["delay_minutes"].mean()
    return predictions, fallback


def _fit_comparison(train, test, numeric, categorical, seed):
    """Identical train/test rows and RF settings; only weather inputs differ."""
    dropped = [col for col in numeric if train[col].isna().all()]
    numeric = [col for col in numeric if col not in dropped]
    features = [*numeric, *categorical]
    model = _make_pipeline(numeric, categorical, seed)
    model.fit(train[features], train["delay_minutes"])
    prediction = model.predict(test[features]).clip(min=0)
    no_weather_numeric = [col for col in numeric if col not in WEATHER_FEATURES]
    ablation_features = [*no_weather_numeric, *categorical]
    if no_weather_numeric == numeric:
        no_weather_prediction = prediction.copy()
        ablation_status = "no_usable_weather_features"
    else:
        ablation = _make_pipeline(no_weather_numeric, categorical, seed)
        ablation.fit(train[ablation_features], train["delay_minutes"])
        no_weather_prediction = ablation.predict(test[ablation_features]).clip(min=0)
        ablation_status = "evaluated"
    group_baseline, fallback = _group_mean_baseline(train, test)
    predictions = {
        "predicted_delay": prediction,
        "no_weather_delay": no_weather_prediction,
        "baseline_delay": np.repeat(train["delay_minutes"].mean(), len(test)),
        "group_baseline_delay": group_baseline,
    }
    return model, predictions, fallback, {
        "numeric_features": numeric, "features": features,
        "dropped_all_missing_training_features": dropped,
        "weather_ablation_status": ablation_status,
        "weather_features": [col for col in numeric if col in WEATHER_FEATURES],
        "without_weather_features": ablation_features,
    }


def _rolling_validation(development, numeric, categorical, seed):
    splits = rolling_date_splits(development)
    rows, folds = [], []
    for number, (train, validation) in enumerate(splits, 1):
        fold = {"fold": number, "train_rows": len(train), "validation_rows": len(validation),
                "train_dates": sorted(train.service_date.unique().tolist()),
                "validation_dates": sorted(validation.service_date.unique().tolist())}
        if len(train) < 50:
            fold["status"] = "insufficient_training_rows"
            folds.append(fold)
            continue
        _, predictions, _, feature_info = _fit_comparison(
            train, validation, numeric, categorical, seed
        )
        fold.update(status="evaluated", **feature_info)
        folds.append(fold)
        for name, column in PREDICTION_COLUMNS.items():
            metrics = _metrics(validation.delay_minutes, predictions[column], name)
            rows.append({**metrics, "fold": number, "train_rows": len(train),
                         "train_last_date": max(fold["train_dates"]),
                         "validation_first_date": min(fold["validation_dates"]),
                         "validation_last_date": max(fold["validation_dates"]),
                         "validation_dates": len(fold["validation_dates"])})
    columns = ["group", "n", "rmse", "mae", "r2", "mean_error_pred_minus_actual",
               "p90_absolute_error", "fold", "train_rows", "train_last_date",
               "validation_first_date", "validation_last_date", "validation_dates"]
    return pd.DataFrame(rows, columns=columns), {
        "status": "evaluated" if rows else "insufficient_development_data",
        "development_dates": int(development.service_date.nunique()), "folds": folds,
        "policy": "Up to three expanding windows within development dates only; first half (at least two dates) trains initially; at least four development dates and 50 training rows required. Final holdout excluded. No hyperparameter tuning.",
        "caveat": "Observed-date blocks can have unequal durations and call counts; inspect each fold. Shared stations/journeys and temporal dependence remain. A one-day run cannot demonstrate temporal stability.",
    }


def run_models() -> None:
    PATHS.ensure()
    settings = load_settings()
    data = pd.read_csv(PATHS.processed / "model_data.csv")
    data["delay_minutes"] = pd.to_numeric(data["delay_minutes"], errors="coerce")
    data = data[np.isfinite(data["delay_minutes"]) & data["delay_minutes"].ge(0)].copy()
    if data["observation_id"].duplicated().any():
        raise ValueError("Duplicate observation IDs found; rerun preparation before modeling.")
    if len(data) < 50:
        raise ValueError("At least 50 usable observations are required for the development model.")
    numeric = [col for col in NUMERIC_FEATURES if col in data]
    categorical = [col for col in CATEGORICAL_FEATURES if col in data]
    for col in numeric:
        data[col] = pd.to_numeric(data[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    for col in categorical:
        data[col] = data[col].fillna("missing").astype(str)

    train, test = _split(data, settings["random_seed"])
    coverage_columns = [*categorical, *(["station_id"] if "station_id" in data else [])]
    holdout_coverage = _holdout_coverage(train, test, coverage_columns)
    holdout_coverage.to_csv(PATHS.tables / "holdout_coverage.csv", index=False)
    rolling_metrics, rolling_spec = _rolling_validation(
        train, numeric, categorical, settings["random_seed"]
    )
    rolling_metrics.to_csv(PATHS.tables / "temporal_validation.csv", index=False)
    (PATHS.tables / "temporal_validation.json").write_text(
        json.dumps(rolling_spec, indent=2), encoding="utf-8"
    )
    pipeline, predictions, group_fallback, feature_info = _fit_comparison(
        train, test, numeric, categorical, settings["random_seed"]
    )
    feature_cols = feature_info["features"]
    test = test.assign(**predictions, group_baseline_fallback=group_fallback)
    overall_metrics = [
        _metrics(test.delay_minutes, predictions[column],
                 "random_forest_overall" if name == "random_forest" else name)
        for name, column in PREDICTION_COLUMNS.items()
    ]
    subgroup_metrics: list[dict] = []
    for grouping in ["region", "transport_mode", "day_period"]:
        for name, group in test.groupby(grouping):
            for model_name, prediction_col in PREDICTION_COLUMNS.items():
                metrics = _metrics(
                    group["delay_minutes"],
                    group[prediction_col].to_numpy(),
                    f"{grouping}:{name}",
                )
                metrics["model"] = model_name
                metrics["small_sample"] = len(group) < 30
                subgroup_metrics.append(metrics)
    pd.DataFrame(overall_metrics).to_csv(PATHS.tables / "model_metrics.csv", index=False)
    pd.DataFrame(subgroup_metrics).to_csv(PATHS.tables / "subgroup_metrics.csv", index=False)
    comparisons = pd.concat([
        paired_day_comparison(test, column, seed=settings["random_seed"])
        for column in ["baseline_delay", "group_baseline_delay", "no_weather_delay"]
    ], ignore_index=True)
    if feature_info["weather_ablation_status"] != "evaluated":
        not_applicable = comparisons.reference_prediction.eq("no_weather_delay")
        comparisons.loc[not_applicable, "status"] = "no_usable_weather_features"
        comparisons.loc[not_applicable, ["ci_low", "ci_high"]] = np.nan
        comparisons.loc[not_applicable, "bootstrap_repetitions"] = 0
    comparisons.to_csv(PATHS.tables / "paired_model_comparisons.csv", index=False)

    importance = permutation_importance(
        pipeline,
        test[feature_cols],
        test["delay_minutes"],
        n_repeats=5,
        max_samples=min(20_000, len(test)),
        random_state=settings["random_seed"],
        scoring="neg_mean_squared_error",
    )
    pd.DataFrame(
        {
            "feature": feature_cols,
            "importance_mean": importance.importances_mean,
            "importance_sd": importance.importances_std,
        }
    ).sort_values("importance_mean", ascending=False).to_csv(
        PATHS.tables / "permutation_importance.csv", index=False
    )
    test[
        [
            "observation_id",
            "service_date",
            "scheduled_time",
            "region",
            "transport_mode",
            "day_period",
            "delay_minutes",
            "predicted_delay",
            "no_weather_delay",
            "baseline_delay",
            "group_baseline_delay",
            "group_baseline_fallback",
        ]
    ].to_csv(PATHS.tables / "holdout_predictions.csv", index=False)
    joblib.dump(pipeline, PATHS.root / "reports" / "delay_random_forest.joblib")

    ols_data = data.copy()
    ols_data["log_delay"] = np.log1p(ols_data["delay_minutes"])
    weather_terms = [
        col
        for col in ["precipitation", "wind_speed_10m", "temperature_2m"]
        if col in ols_data and ols_data[col].nunique(dropna=True) > 1
    ]
    # Explanatory OLS uses documented complete cases, not single imputation with false precision.
    ols_data = ols_data.dropna(subset=weather_terms).copy()
    if len(ols_data) < 20:
        raise ValueError("Fewer than 20 complete weather cases remain for explanatory OLS.")
    candidate_terms = [
        f"C({col})"
        for col in ["region", "transport_mode", "day_period"]
        if ols_data[col].nunique() > 1
    ] + weather_terms
    if ols_data["is_weekend"].nunique(dropna=True) > 1:
        candidate_terms.append("is_weekend")
    base_terms: list[str] = []
    dropped_rank_deficient_terms: list[str] = []
    for term in candidate_terms:
        trial_formula = "log_delay ~ " + " + ".join([*base_terms, term])
        trial_model = smf.ols(trial_formula, data=ols_data)
        if np.linalg.matrix_rank(trial_model.exog) == trial_model.exog.shape[1]:
            base_terms.append(term)
        else:
            dropped_rank_deficient_terms.append(term)
    base_formula = "log_delay ~ " + (" + ".join(base_terms) or "1")
    interaction_formula = base_formula + " + C(region):C(transport_mode)"
    interaction_candidate = smf.ols(interaction_formula, data=ols_data)
    interaction_full_rank = (
        ols_data["region"].nunique() > 1
        and ols_data["transport_mode"].nunique() > 1
        and np.linalg.matrix_rank(interaction_candidate.exog) == interaction_candidate.exog.shape[1]
        and len(ols_data) > interaction_candidate.exog.shape[1] + 5
    )
    formula = interaction_formula if interaction_full_rank else base_formula
    station_groups = ols_data["station_id"].fillna("missing").astype(str)
    n_clusters = station_groups.nunique()
    # Repeated calls at the same station are not independent observations.
    ols_model = smf.ols(formula, data=ols_data)
    if n_clusters >= 2:
        ols = ols_model.fit(cov_type="cluster", cov_kwds={"groups": station_groups}, use_t=True)
        covariance_type = "station_clustered"
    else:
        ols = ols_model.fit(cov_type="HC3")
        covariance_type = "HC3_single_station_fallback"
    # statsmodels versions expose the Patsy design under different attribute names.
    design = getattr(ols.model.data, "model_spec", None)
    if design is None:
        design = ols.model.data.design_info
    ols_table = pd.DataFrame(
        {
            "term": ols.params.index,
            "coefficient_log_scale": ols.params.values,
            "robust_se": ols.bse.values,
            "p_value": ols.pvalues.values,
            "ci_low": ols.conf_int()[0].values,
            "ci_high": ols.conf_int()[1].values,
        }
    )
    ols_table["ratio_delay_plus_one"] = np.exp(ols_table["coefficient_log_scale"])
    ols_table["ratio_ci_low"] = np.exp(ols_table["ci_low"])
    ols_table["ratio_ci_high"] = np.exp(ols_table["ci_high"])
    ols_table["percent_change_delay_plus_one"] = np.expm1(ols_table["coefficient_log_scale"]) * 100
    ols_table["interpretation"] = (
        "Change in fitted geometric mean of delay+1; not percent change in mean delay or a causal effect."
    )
    ols_table.to_csv(PATHS.tables / "ols_associations.csv", index=False)
    (PATHS.tables / "ols_summary.txt").write_text(ols.summary().as_text(), encoding="utf-8")
    (PATHS.tables / "model_specification.json").write_text(
        json.dumps(
            {
                "formula": formula,
                "train_rows": len(train),
                "test_rows": len(test),
                "split_strategy": "chronological_by_service_date"
                if data["service_date"].nunique() >= 2
                else "development_chronological_within_day",
                "train_dates": sorted(train["service_date"].unique().tolist()),
                "test_dates": sorted(test["service_date"].unique().tolist()),
                "preprocessing": "Medians and categories fitted on training rows only.",
                **feature_info,
                "temporal_validation_status": rolling_spec["status"],
                "weather_ablation_note": "Same rows, RF settings and seed, with all listed weather features removed. Differences reflect predictive information conditional on other features, not causal weather effects. Weather can also proxy location/date. Concurrent/reanalysed weather is not a real-time forecast input.",
                "uncertainty_note": "paired_model_comparisons.csv uses whole-date paired bootstrap intervals only with at least five test dates. This minimum is a safeguard, not a guarantee of reliable inference.",
                "predictive_target": "delay_minutes (no logarithmic back-transformation)",
                "permutation_importance_unit": "increase in holdout MSE (minutes squared)",
                "holdout_use": "Evaluation and descriptive importance only; not used for tuning.",
                "holdout_unseen_category_rows": {
                    row.feature: int(row.affected_test_rows)
                    for row in holdout_coverage.itertuples(index=False)
                },
                "holdout_coverage_note": "See holdout_coverage.csv. Unseen one-hot categories are ignored by the fitted encoder; station_id is diagnostic only, not a model feature.",
                "group_mean_baseline": {
                    "training_only_fields": GROUP_BASELINE_COLUMNS,
                    "minimum_training_rows_per_group": GROUP_BASELINE_MIN_ROWS,
                    "fallback": "overall training mean",
                    "fallback_test_rows": int(group_fallback.sum()),
                },
                "evaluation_caveat": "One-day results are development only. Weather is concurrent/reanalysed, not a deployable forecast. Shared journeys and stations can remain dependent.",
                "ols_rows": len(ols_data),
                "ols_reference_categories": {
                    factor.name(): str(info.categories[0])
                    for factor, info in design.factor_infos.items()
                    if info.type == "categorical"
                },
                "ols_rows_excluded_missing_weather": len(data) - len(ols_data),
                "ols_covariance_type": covariance_type,
                "ols_station_clusters": int(n_clusters),
                "ols_inference_caveat": "Exploratory, not causal. Station clustering does not handle all cross-station or shared-day dependence; fewer than 30 clusters makes p-values and confidence intervals fragile.",
                "ols_r_squared_log_scale": float(ols.rsquared),
                "ols_adjusted_r_squared_log_scale": float(ols.rsquared_adj),
                "region_mode_interaction_included": bool(interaction_full_rank),
                "interaction_fallback_reason": None
                if interaction_full_rank
                else "Interaction lacks distinct groups, full rank, or residual degrees of freedom.",
                "dropped_rank_deficient_terms": dropped_rank_deficient_terms,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Regression models and evaluation tables created.")
