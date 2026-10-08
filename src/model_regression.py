#!/usr/bin/env python3
"""
Regression modelling for predicted public-transport delay.

Models:
- median baseline
- linear regression
- random forest regression

The split is chronological rather than random. When batch_id is available,
entire collection batches are kept together so the test set represents later
data rather than a random sample of the same collection moments.

Important leakage rule:
The target is predicted_delay_minutes. Estimated departure, the derived
five-minute target and other direct/near-direct target fields are not used as
predictors.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    OneHotEncoder,
    StandardScaler,
)


DATASET_PATH = Path("data/processed/analysis_dataset.csv")
TABLE_DIR = Path("results/tables")
FIGURE_DIR = Path("results/figures")
MODEL_DIR = Path("results/model")

TARGET_COLUMN = "predicted_delay_minutes"
TIME_COLUMN = "collection_timestamp"
TRAIN_FRACTION = 0.80
RANDOM_STATE = 42

CATEGORICAL_CANDIDATES = [
    "city",
    "transport_mode",
    "station_type",
    "product_category",
    "weekday",
]

NUMERIC_CANDIDATES = [
    "hour",
    "weekend",
    "temperature_c",
    "precipitation_mm_10min",
    "relative_humidity_pct",
    "wind_speed_kmh_10min",
    "wind_gust_kmh",
    "station_pressure_hpa",
]

EXCLUDED_FEATURES = {
    "predicted_delay_minutes": (
        "Target variable."
    ),
    "estimated_departure": (
        "Direct source of the target; using it would be target leakage."
    ),
    "is_predicted_delayed_5min": (
        "Derived directly from the regression target."
    ),
    "has_realtime": (
        "Target availability indicator rather than an explanatory factor."
    ),
    "minutes_until_departure": (
        "Used to define the 5-15 minute observation window; excluded from "
        "the explanatory feature set."
    ),
    "collection_timestamp": (
        "Used for chronological splitting, not as a predictor."
    ),
    "scheduled_departure": (
        "Raw timestamp is represented by hour/weekday instead."
    ),
    "journey_ref": (
        "High-cardinality journey identifier; excluded to avoid memorisation."
    ),
    "batch_id": (
        "Collection-run identifier; used only to keep batches together in "
        "the time split."
    ),
    "line": (
        "High-cardinality service identifier; excluded from the core model."
    ),
    "public_code": (
        "Service identifier; excluded from the core model."
    ),
    "train_number": (
        "Service identifier; excluded from the core model."
    ),
    "weather_time_gap_minutes": (
        "Join-quality diagnostic rather than a substantive predictor."
    ),
}


def load_dataset(
    path: Path = DATASET_PATH,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Analysis dataset not found: {path}. "
            "Run sync_collection_data.py and build_dataset.py first."
        )

    return pd.read_csv(path)


def prepare_dataset(
    df: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    list[str],
    list[str],
]:
    """Normalize model columns and choose the available core features."""
    if TARGET_COLUMN not in df.columns:
        raise ValueError(
            f"Dataset is missing target column: {TARGET_COLUMN}"
        )
    if TIME_COLUMN not in df.columns:
        raise ValueError(
            f"Dataset is missing time column: {TIME_COLUMN}"
        )

    out = df.copy()

    out[TIME_COLUMN] = pd.to_datetime(
        out[TIME_COLUMN],
        utc=True,
        errors="coerce",
    )
    out[TARGET_COLUMN] = pd.to_numeric(
        out[TARGET_COLUMN],
        errors="coerce",
    )

    if "weekend" in out.columns:
        if out["weekend"].dtype == object:
            out["weekend"] = (
                out["weekend"]
                .astype(str)
                .str.strip()
                .str.lower()
                .map(
                    {
                        "true": 1,
                        "false": 0,
                        "1": 1,
                        "0": 0,
                    }
                )
            )
        else:
            out["weekend"] = pd.to_numeric(
                out["weekend"],
                errors="coerce",
            )

    for column in NUMERIC_CANDIDATES:
        if column in out.columns:
            out[column] = pd.to_numeric(
                out[column],
                errors="coerce",
            )

    out = out.dropna(
        subset=[
            TIME_COLUMN,
            TARGET_COLUMN,
        ]
    ).copy()

    categorical = [
        column
        for column in CATEGORICAL_CANDIDATES
        if column in out.columns
    ]
    numeric = [
        column
        for column in NUMERIC_CANDIDATES
        if column in out.columns
    ]

    if not categorical and not numeric:
        raise ValueError(
            "No configured model features are available in the dataset."
        )

    return out, categorical, numeric


def temporal_split(
    df: pd.DataFrame,
    train_fraction: float = TRAIN_FRACTION,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    str,
]:
    """
    Create a chronological train/test split.

    Prefer whole batch_id groups when available so observations from one
    collection run cannot be divided between train and test.
    """
    if not 0 < train_fraction < 1:
        raise ValueError(
            "train_fraction must be between 0 and 1."
        )

    if (
        "batch_id" in df.columns
        and df["batch_id"].notna().sum() > 1
    ):
        batch_times = (
            df.dropna(subset=["batch_id"])
            .groupby("batch_id")[TIME_COLUMN]
            .min()
            .sort_values()
        )

        if len(batch_times) >= 2:
            split_index = int(
                np.floor(
                    len(batch_times)
                    * train_fraction
                )
            )
            split_index = max(
                1,
                min(
                    len(batch_times) - 1,
                    split_index,
                ),
            )

            train_batches = set(
                batch_times.index[
                    :split_index
                ]
            )

            train = df[
                df["batch_id"].isin(
                    train_batches
                )
            ].copy()
            test = df[
                ~df["batch_id"].isin(
                    train_batches
                )
            ].copy()

            if (
                len(train) > 0
                and len(test) > 0
            ):
                return (
                    train.sort_values(
                        TIME_COLUMN
                    ),
                    test.sort_values(
                        TIME_COLUMN
                    ),
                    "batch_id",
                )

    ordered = df.sort_values(
        TIME_COLUMN
    ).copy()
    unique_times = (
        ordered[TIME_COLUMN]
        .dropna()
        .drop_duplicates()
        .sort_values()
    )

    if len(unique_times) < 2:
        raise ValueError(
            "At least two distinct collection times are required "
            "for a chronological split."
        )

    split_index = int(
        np.floor(
            len(unique_times)
            * train_fraction
        )
    )
    split_index = max(
        1,
        min(
            len(unique_times) - 1,
            split_index,
        ),
    )

    cutoff = unique_times.iloc[
        split_index
    ]

    train = ordered[
        ordered[TIME_COLUMN] < cutoff
    ].copy()
    test = ordered[
        ordered[TIME_COLUMN] >= cutoff
    ].copy()

    if (
        len(train) == 0
        or len(test) == 0
    ):
        raise ValueError(
            "Chronological split produced an empty train or test set."
        )

    return (
        train,
        test,
        "timestamp",
    )


def make_preprocessor(
    categorical: list[str],
    numeric: list[str],
    *,
    scale_numeric: bool,
) -> ColumnTransformer:
    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="most_frequent"
                ),
            ),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
            ),
        ]
    )

    numeric_steps = [
        (
            "imputer",
            SimpleImputer(
                strategy="median"
            ),
        ),
    ]

    if scale_numeric:
        numeric_steps.append(
            (
                "scaler",
                StandardScaler(),
            )
        )

    return ColumnTransformer(
        transformers=[
            (
                "categorical",
                categorical_pipeline,
                categorical,
            ),
            (
                "numeric",
                Pipeline(
                    steps=numeric_steps
                ),
                numeric,
            ),
        ],
        remainder="drop",
    )


def build_models(
    categorical: list[str],
    numeric: list[str],
    *,
    random_forest_estimators: int = 400,
) -> dict[str, object]:
    linear = Pipeline(
        steps=[
            (
                "preprocessor",
                make_preprocessor(
                    categorical,
                    numeric,
                    scale_numeric=True,
                ),
            ),
            (
                "model",
                LinearRegression(),
            ),
        ]
    )

    random_forest = Pipeline(
        steps=[
            (
                "preprocessor",
                make_preprocessor(
                    categorical,
                    numeric,
                    scale_numeric=False,
                ),
            ),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=(
                        random_forest_estimators
                    ),
                    min_samples_leaf=5,
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    return {
        "median_baseline": DummyRegressor(
            strategy="median"
        ),
        "linear_regression": linear,
        "random_forest": random_forest,
    }


def regression_metrics(
    y_true: pd.Series,
    y_pred: np.ndarray,
) -> dict[str, float]:
    return {
        "mae": mean_absolute_error(
            y_true,
            y_pred,
        ),
        "rmse": float(
            np.sqrt(
                mean_squared_error(
                    y_true,
                    y_pred,
                )
            )
        ),
        "r2": r2_score(
            y_true,
            y_pred,
        ),
    }


def build_split_summary(
    train: pd.DataFrame,
    test: pd.DataFrame,
    split_method: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "split": "train",
                "split_method": split_method,
                "rows": len(train),
                "time_min": train[
                    TIME_COLUMN
                ].min(),
                "time_max": train[
                    TIME_COLUMN
                ].max(),
                "target_mean": train[
                    TARGET_COLUMN
                ].mean(),
                "target_median": train[
                    TARGET_COLUMN
                ].median(),
            },
            {
                "split": "test",
                "split_method": split_method,
                "rows": len(test),
                "time_min": test[
                    TIME_COLUMN
                ].min(),
                "time_max": test[
                    TIME_COLUMN
                ].max(),
                "target_mean": test[
                    TARGET_COLUMN
                ].mean(),
                "target_median": test[
                    TARGET_COLUMN
                ].median(),
            },
        ]
    )


def build_feature_manifest(
    df: pd.DataFrame,
    categorical: list[str],
    numeric: list[str],
) -> pd.DataFrame:
    rows = []

    for column in categorical:
        rows.append(
            {
                "feature": column,
                "type": "categorical",
                "used": True,
                "reason": (
                    "Core operational/temporal feature."
                ),
            }
        )

    for column in numeric:
        rows.append(
            {
                "feature": column,
                "type": "numeric",
                "used": True,
                "reason": (
                    "Core temporal/weather feature."
                ),
            }
        )

    for column, reason in (
        EXCLUDED_FEATURES.items()
    ):
        if column in df.columns:
            rows.append(
                {
                    "feature": column,
                    "type": "excluded",
                    "used": False,
                    "reason": reason,
                }
            )

    return pd.DataFrame(rows)


def grouped_metrics(
    predictions: pd.DataFrame,
    group_column: str,
    model_names: list[str],
) -> pd.DataFrame:
    rows = []

    for group_value, group in (
        predictions.groupby(
            group_column,
            observed=True,
        )
    ):
        for model_name in model_names:
            pred_column = (
                f"pred_{model_name}"
            )

            metrics = regression_metrics(
                group["actual_delay"],
                group[pred_column].to_numpy(),
            )

            rows.append(
                {
                    group_column: group_value,
                    "model": model_name,
                    "observations": len(group),
                    **metrics,
                }
            )

    result = pd.DataFrame(rows)

    if not result.empty:
        result[
            ["mae", "rmse", "r2"]
        ] = result[
            ["mae", "rmse", "r2"]
        ].round(4)

    return result


def permutation_importance_table(
    model: Pipeline,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    feature_columns: list[str],
) -> pd.DataFrame:
    result = permutation_importance(
        model,
        x_test,
        y_test,
        scoring="neg_mean_absolute_error",
        n_repeats=10,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    table = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance_mae_increase": (
                result.importances_mean
            ),
            "importance_std": (
                result.importances_std
            ),
        }
    ).sort_values(
        "importance_mae_increase",
        ascending=False,
    )

    table[
        [
            "importance_mae_increase",
            "importance_std",
        ]
    ] = table[
        [
            "importance_mae_increase",
            "importance_std",
        ]
    ].round(5)

    return table.reset_index(
        drop=True
    )


def save_figures(
    metrics_table: pd.DataFrame,
    predictions: pd.DataFrame,
    importance: pd.DataFrame,
    figure_dir: Path = FIGURE_DIR,
) -> None:
    figure_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    plt.figure(
        figsize=(8, 5)
    )
    metrics_table.set_index(
        "model"
    )["mae"].plot(
        kind="bar"
    )
    plt.ylabel(
        "MAE (minutes)"
    )
    plt.xlabel("Model")
    plt.title(
        "Regression model comparison on chronological test set"
    )
    plt.xticks(
        rotation=20,
        ha="right",
    )
    plt.tight_layout()
    plt.savefig(
        figure_dir
        / "12_regression_model_mae.png",
        dpi=180,
        bbox_inches="tight",
    )
    plt.close()

    actual = predictions[
        "actual_delay"
    ]
    predicted = predictions[
        "pred_random_forest"
    ]

    plt.figure(
        figsize=(7, 6)
    )
    plt.scatter(
        actual,
        predicted,
        alpha=0.55,
    )
    low = float(
        min(
            actual.min(),
            predicted.min(),
        )
    )
    high = float(
        max(
            actual.max(),
            predicted.max(),
        )
    )
    plt.plot(
        [low, high],
        [low, high],
        linestyle="--",
    )
    plt.xlabel(
        "Observed predicted delay (minutes)"
    )
    plt.ylabel(
        "Random-forest prediction (minutes)"
    )
    plt.title(
        "Random forest: predicted vs observed delay"
    )
    plt.tight_layout()
    plt.savefig(
        figure_dir
        / "13_random_forest_predicted_vs_observed.png",
        dpi=180,
        bbox_inches="tight",
    )
    plt.close()

    residuals = (
        actual - predicted
    )

    plt.figure(
        figsize=(8, 5)
    )
    plt.hist(
        residuals,
        bins=40,
    )
    plt.axvline(
        0,
        linestyle="--",
    )
    plt.xlabel(
        "Residual = observed - predicted (minutes)"
    )
    plt.ylabel(
        "Test observations"
    )
    plt.title(
        "Random-forest residual distribution"
    )
    plt.tight_layout()
    plt.savefig(
        figure_dir
        / "14_random_forest_residuals.png",
        dpi=180,
        bbox_inches="tight",
    )
    plt.close()

    top = (
        importance.head(15)
        .sort_values(
            "importance_mae_increase",
            ascending=True,
        )
    )

    plt.figure(
        figsize=(9, 6)
    )
    plt.barh(
        top["feature"],
        top[
            "importance_mae_increase"
        ],
    )
    plt.xlabel(
        "Increase in MAE after permutation"
    )
    plt.ylabel("Feature")
    plt.title(
        "Random-forest permutation importance"
    )
    plt.tight_layout()
    plt.savefig(
        figure_dir
        / "15_random_forest_permutation_importance.png",
        dpi=180,
        bbox_inches="tight",
    )
    plt.close()


def run_regression_analysis(
    df: pd.DataFrame,
    *,
    table_dir: Path = TABLE_DIR,
    figure_dir: Path = FIGURE_DIR,
    model_dir: Path = MODEL_DIR,
    random_forest_estimators: int = 400,
) -> dict[str, pd.DataFrame]:
    clean, categorical, numeric = (
        prepare_dataset(df)
    )
    feature_columns = (
        categorical + numeric
    )

    train, test, split_method = (
        temporal_split(clean)
    )

    x_train = train[
        feature_columns
    ].copy()
    y_train = train[
        TARGET_COLUMN
    ].copy()
    x_test = test[
        feature_columns
    ].copy()
    y_test = test[
        TARGET_COLUMN
    ].copy()

    models = build_models(
        categorical,
        numeric,
        random_forest_estimators=(
            random_forest_estimators
        ),
    )

    predictions = test[
        [
            column
            for column in [
                TIME_COLUMN,
                "batch_id",
                "city",
                "transport_mode",
            ]
            if column in test.columns
        ]
    ].copy()
    predictions[
        "actual_delay"
    ] = y_test.to_numpy()

    metrics_rows = []

    for model_name, model in (
        models.items()
    ):
        if model_name == (
            "median_baseline"
        ):
            x_train_fit = np.zeros(
                (len(x_train), 1)
            )
            x_test_fit = np.zeros(
                (len(x_test), 1)
            )
        else:
            x_train_fit = x_train
            x_test_fit = x_test

        model.fit(
            x_train_fit,
            y_train,
        )
        y_pred = model.predict(
            x_test_fit
        )

        predictions[
            f"pred_{model_name}"
        ] = y_pred

        metrics_rows.append(
            {
                "model": model_name,
                "train_rows": len(train),
                "test_rows": len(test),
                **regression_metrics(
                    y_test,
                    y_pred,
                ),
            }
        )

    metrics_table = pd.DataFrame(
        metrics_rows
    )

    metrics_table[
        ["mae", "rmse", "r2"]
    ] = metrics_table[
        ["mae", "rmse", "r2"]
    ].round(4)

    importance = (
        permutation_importance_table(
            models["random_forest"],
            x_test,
            y_test,
            feature_columns,
        )
    )

    split_summary = (
        build_split_summary(
            train,
            test,
            split_method,
        )
    )
    feature_manifest = (
        build_feature_manifest(
            clean,
            categorical,
            numeric,
        )
    )

    model_names = list(
        models.keys()
    )

    if "city" in predictions.columns:
        by_city = grouped_metrics(
            predictions,
            "city",
            model_names,
        )
    else:
        by_city = pd.DataFrame()

    if (
        "transport_mode"
        in predictions.columns
    ):
        by_mode = grouped_metrics(
            predictions,
            "transport_mode",
            model_names,
        )
    else:
        by_mode = pd.DataFrame()

    table_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    model_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs = {
        "model_regression_metrics": (
            metrics_table
        ),
        "model_split_summary": (
            split_summary
        ),
        "model_feature_manifest": (
            feature_manifest
        ),
        "model_random_forest_permutation_importance": (
            importance
        ),
        "model_metrics_by_city": (
            by_city
        ),
        "model_metrics_by_mode": (
            by_mode
        ),
    }

    for name, table in (
        outputs.items()
    ):
        table.to_csv(
            table_dir / f"{name}.csv",
            index=False,
        )

    predictions.to_csv(
        model_dir
        / "regression_test_predictions.csv",
        index=False,
    )

    joblib.dump(
        models["linear_regression"],
        model_dir
        / "linear_regression.joblib",
    )
    joblib.dump(
        models["random_forest"],
        model_dir
        / "random_forest_regression.joblib",
    )

    save_figures(
        metrics_table,
        predictions,
        importance,
        figure_dir,
    )

    return outputs


def main() -> int:
    print("=" * 72)
    print("REGRESSION MODELLING")
    print("=" * 72)

    df = load_dataset()

    outputs = (
        run_regression_analysis(
            df
        )
    )

    print(
        "\nChronological split:"
    )
    print(
        outputs[
            "model_split_summary"
        ].to_string(
            index=False
        )
    )

    print(
        "\nModel metrics:"
    )
    print(
        outputs[
            "model_regression_metrics"
        ].to_string(
            index=False
        )
    )

    print(
        "\nRandom-forest permutation importance:"
    )
    print(
        outputs[
            "model_random_forest_permutation_importance"
        ]
        .head(15)
        .to_string(
            index=False
        )
    )

    print(
        "\nLeakage protection:"
    )
    print(
        "Estimated departure, the derived classification target, "
        "journey identifiers and other direct/near-direct target fields "
        "are excluded from the predictor set."
    )

    print(
        "\nSaved model tables to results/tables/, "
        "figures to results/figures/ and fitted pipelines "
        "to results/model/."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
