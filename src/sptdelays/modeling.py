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


def _metrics(y_true: pd.Series, y_pred: np.ndarray, label: str) -> dict:
    return {
        "group": label,
        "n": len(y_true),
        "rmse": mean_squared_error(y_true, y_pred) ** 0.5,
        "mae": mean_absolute_error(y_true, y_pred),
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
    dropped_empty_features = [col for col in numeric if train[col].isna().all()]
    numeric = [col for col in numeric if col not in dropped_empty_features]
    pipeline = _make_pipeline(numeric, categorical, settings["random_seed"])
    feature_cols = [*numeric, *categorical]
    # Raw minutes align the forest's squared-error objective with RMSE and the mean baseline.
    pipeline.fit(train[feature_cols], train["delay_minutes"])
    prediction = pipeline.predict(test[feature_cols]).clip(min=0)
    baseline = np.repeat(train["delay_minutes"].mean(), len(test))
    group_baseline, group_fallback = _group_mean_baseline(train, test)
    overall_metrics = [_metrics(test["delay_minutes"], prediction, "random_forest_overall")]
    overall_metrics.append(_metrics(test["delay_minutes"], baseline, "mean_baseline"))
    overall_metrics.append(_metrics(test["delay_minutes"], group_baseline, "group_mean_baseline"))
    test = test.assign(
        predicted_delay=prediction,
        baseline_delay=baseline,
        group_baseline_delay=group_baseline,
        group_baseline_fallback=group_fallback,
    )
    subgroup_metrics: list[dict] = []
    for grouping in ["region", "transport_mode", "day_period"]:
        for name, group in test.groupby(grouping):
            for model_name, prediction_col in [
                ("random_forest", "predicted_delay"),
                ("mean_baseline", "baseline_delay"),
                ("group_mean_baseline", "group_baseline_delay"),
            ]:
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
                "dropped_all_missing_training_features": dropped_empty_features,
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
