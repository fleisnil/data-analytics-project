from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .settings import PATHS, load_settings

NUMERIC_FEATURES = [
    "scheduled_hour", "is_weekend", "is_peak", "temperature_2m",
    "precipitation", "wind_speed_10m", "wind_gusts_10m", "snowfall",
]
CATEGORICAL_FEATURES = ["region", "transport_mode", "day_period", "weekday", "operator"]


def _metrics(y_true: pd.Series, y_pred: np.ndarray, label: str) -> dict:
    return {
        "group": label,
        "n": len(y_true),
        "rmse": mean_squared_error(y_true, y_pred) ** 0.5,
        "mae": mean_absolute_error(y_true, y_pred),
        "r2": r2_score(y_true, y_pred) if len(y_true) > 1 else np.nan,
    }


def _split(frame: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(frame["service_date"].dropna().unique())
    if len(dates) >= 3:
        split_index = max(1, int(len(dates) * 0.8))
        train_dates = set(dates[:split_index])
        return frame[frame["service_date"].isin(train_dates)], frame[~frame["service_date"].isin(train_dates)]
    return train_test_split(frame, test_size=0.25, random_state=seed)


def run_models() -> None:
    settings = load_settings()
    data = pd.read_csv(PATHS.processed / "model_data.csv")
    data = data[data["delay_minutes"].notna()].copy()
    if len(data) < 50:
        raise ValueError("At least 50 usable observations are required for the development model.")
    numeric = [col for col in NUMERIC_FEATURES if col in data]
    categorical = [col for col in CATEGORICAL_FEATURES if col in data]
    for col in numeric:
        data[col] = pd.to_numeric(data[col], errors="coerce")
        data[col] = data[col].fillna(data[col].median())
    for col in categorical:
        data[col] = data[col].fillna("missing").astype(str)

    train, test = _split(data, settings["random_seed"])
    transformer = ColumnTransformer(
        [
            ("numeric", "passthrough", numeric),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )
    pipeline = Pipeline(
        [
            ("features", transformer),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=5,
                    random_state=settings["random_seed"],
                    n_jobs=1,
                ),
            ),
        ]
    )
    feature_cols = [*numeric, *categorical]
    pipeline.fit(train[feature_cols], np.log1p(train["delay_minutes"]))
    prediction = np.expm1(pipeline.predict(test[feature_cols])).clip(min=0)
    baseline = np.repeat(train["delay_minutes"].mean(), len(test))
    overall_metrics = [_metrics(test["delay_minutes"], prediction, "random_forest_overall")]
    overall_metrics.append(_metrics(test["delay_minutes"], baseline, "mean_baseline"))
    test = test.assign(predicted_delay=prediction)
    subgroup_metrics: list[dict] = []
    for grouping in ["region", "transport_mode"]:
        for name, group in test.groupby(grouping):
            subgroup_metrics.append(
                _metrics(
                    group["delay_minutes"],
                    group["predicted_delay"].to_numpy(),
                    f"{grouping}:{name}",
                )
            )
    pd.DataFrame(overall_metrics).to_csv(PATHS.tables / "model_metrics.csv", index=False)
    pd.DataFrame(subgroup_metrics).to_csv(PATHS.tables / "subgroup_metrics.csv", index=False)

    importance = permutation_importance(
        pipeline,
        test[feature_cols],
        np.log1p(test["delay_minutes"]),
        n_repeats=5,
        max_samples=min(20_000, len(test)),
        random_state=settings["random_seed"],
        scoring="neg_mean_squared_error",
    )
    pd.DataFrame(
        {"feature": feature_cols, "importance_mean": importance.importances_mean, "importance_sd": importance.importances_std}
    ).sort_values("importance_mean", ascending=False).to_csv(PATHS.tables / "permutation_importance.csv", index=False)
    test[["observation_id", "service_date", "region", "transport_mode", "delay_minutes", "predicted_delay"]].to_csv(
        PATHS.tables / "holdout_predictions.csv", index=False
    )
    joblib.dump(pipeline, PATHS.root / "reports" / "delay_random_forest.joblib")

    ols_data = data.copy()
    ols_data["log_delay"] = np.log1p(ols_data["delay_minutes"])
    weather_terms = [
        col
        for col in ["precipitation", "wind_speed_10m", "temperature_2m"]
        if col in ols_data and ols_data[col].nunique(dropna=True) > 1
    ]
    candidate_terms = [
        "C(region)",
        "C(transport_mode)",
        "C(day_period)",
        *weather_terms,
    ]
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
    interaction_formula = "log_delay ~ " + " + ".join(
        [*base_terms, "C(region):C(transport_mode)"]
    )
    interaction_candidate = smf.ols(interaction_formula, data=ols_data)
    interaction_full_rank = np.linalg.matrix_rank(
        interaction_candidate.exog
    ) == interaction_candidate.exog.shape[1]
    formula = (
        interaction_formula
        if interaction_full_rank
        else "log_delay ~ " + " + ".join(base_terms)
    )
    ols = smf.ols(formula, data=ols_data).fit(cov_type="HC3")
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
    ols_table["approx_percent_change"] = (np.exp(ols_table["coefficient_log_scale"]) - 1) * 100
    ols_table.to_csv(PATHS.tables / "ols_associations.csv", index=False)
    (PATHS.tables / "ols_summary.txt").write_text(ols.summary().as_text(), encoding="utf-8")
    (PATHS.tables / "model_specification.json").write_text(
        json.dumps(
            {
                "formula": formula,
                "train_rows": len(train),
                "test_rows": len(test),
                "split_strategy": "chronological_by_service_date"
                if data["service_date"].nunique() >= 3
                else "development_random_split",
                "region_mode_interaction_included": bool(interaction_full_rank),
                "interaction_fallback_reason": None
                if interaction_full_rank
                else "Observed region-mode cells made the interaction design matrix rank-deficient.",
                "dropped_rank_deficient_terms": dropped_rank_deficient_terms,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Regression models and evaluation tables created.")
