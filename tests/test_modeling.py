import numpy as np
import pandas as pd
import pytest

from sptdelays import modeling
from sptdelays.modeling import (
    _group_mean_baseline,
    _holdout_coverage,
    _make_pipeline,
    _metrics,
    _split,
)
from sptdelays.settings import ProjectPaths


def test_chronological_split_keeps_whole_dates_and_times_together():
    frame = pd.DataFrame(
        {
            "service_date": ["2026-09-01"] * 6 + ["2026-09-02"] * 2,
            "scheduled_time": pd.date_range("2026-09-01", periods=8, freq="h", tz="UTC"),
        }
    )
    train, test = _split(frame, 42)
    assert set(train.service_date).isdisjoint(test.service_date)
    assert train.service_date.max() < test.service_date.min()
    one_day = frame.iloc[:6].copy()
    one_day["scheduled_time"] = ["2026-09-01T10:00Z"] * 3 + ["2026-09-01T11:00Z"] * 3
    train, test = _split(one_day, 42)
    assert train.scheduled_time.max() < test.scheduled_time.min()
    assert len(train) + len(test) == 6


def test_split_does_not_fall_back_to_random_when_time_is_invalid():
    frame = pd.DataFrame({"service_date": ["2026-09-01"] * 3, "scheduled_time": ["bad"] * 3})
    with pytest.raises(ValueError, match="distinct valid"):
        _split(frame, 42)


def test_pipeline_imputation_is_fitted_on_training_data_only():
    train = pd.DataFrame({"weather": [1.0, 3.0, np.nan], "mode": ["train"] * 3})
    test = pd.DataFrame({"weather": [np.nan, 1000.0], "mode": ["bus", "train"]})
    model = _make_pipeline(["weather"], ["mode"], 42)
    model.fit(train, [0.0, 1.0, 2.0])
    imputer = model.named_steps["features"].named_transformers_["numeric"]
    assert imputer.statistics_[0] == 2.0
    assert len(model.predict(test)) == 2
    assert imputer.statistics_[0] == 2.0


def test_constant_target_r_squared_is_not_reported_as_perfect():
    result = _metrics(pd.Series([0, 0, 0]), np.zeros(3), "constant")
    assert result["rmse"] == 0
    assert np.isnan(result["r2"])


def test_holdout_coverage_reports_categories_unseen_during_training():
    train = pd.DataFrame({"region": ["A", "A", "B"]})
    test = pd.DataFrame({"region": ["A", "C", "C"]})
    row = _holdout_coverage(train, test, ["region"]).iloc[0]
    assert row.unseen_test_categories == 1
    assert row.unseen_test_values == "C"
    assert row.affected_test_rows == 2
    assert row.affected_test_fraction == pytest.approx(2 / 3)


def test_group_baseline_uses_training_means_and_falls_back_for_sparse_groups():
    train = pd.DataFrame({
        "region": ["A"] * 10 + ["B"] * 2,
        "transport_mode": ["bus"] * 12,
        "day_period": ["midday"] * 12,
        "delay_minutes": [2.0] * 10 + [8.0] * 2,
    })
    test = pd.DataFrame({
        "region": ["A", "B", "C"],
        "transport_mode": ["bus"] * 3,
        "day_period": ["midday"] * 3,
        "delay_minutes": [100.0] * 3,
    })
    predicted, fallback = _group_mean_baseline(train, test)
    assert predicted.tolist() == pytest.approx([2.0, 3.0, 3.0])
    assert fallback.tolist() == [False, True, True]


import json

import joblib


def test_model_run_exports_auditable_baselines_and_correct_log_interpretation(
    tmp_path, monkeypatch
):
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    monkeypatch.setattr(modeling, "PATHS", paths)
    monkeypatch.setattr(modeling, "load_settings", lambda: {"random_seed": 42})
    rng = np.random.default_rng(42)
    frame = pd.DataFrame(
        {
            "observation_id": [f"obs-{i}" for i in range(80)],
            "station_id": [f"station-{i % 8}" for i in range(80)],
            "service_date": ["2026-09-01"] * 60 + ["2026-09-02"] * 20,
            "scheduled_time": ["2026-09-01T10:00Z"] * 60 + ["2026-09-02T10:00Z"] * 20,
            "region": ["A", "B"] * 40,
            "transport_mode": ["bus", "bus", "train", "train"] * 20,
            "day_period": ["midday"] * 80,
            "is_weekend": [0] * 80,
            "precipitation": np.r_[np.arange(60, dtype=float), np.repeat(1000.0, 20)],
            "delay_minutes": rng.exponential(size=80),
        }
    )
    frame.loc[0, "precipitation"] = np.nan
    frame.to_csv(paths.processed / "model_data.csv", index=False)
    modeling.run_models()
    fitted = joblib.load(paths.root / "reports/delay_random_forest.joblib")
    medians = fitted.named_steps["features"].named_transformers_["numeric"].statistics_
    assert medians[1] == 30.0  # median of training precipitation 1..59, not holdout 1000s
    subgroups = pd.read_csv(paths.tables / "subgroup_metrics.csv")
    assert set(subgroups.model) == {"random_forest", "mean_baseline", "group_mean_baseline"}
    assert subgroups.group.str.startswith("day_period:").any()
    coefficients = pd.read_csv(paths.tables / "ols_associations.csv")
    assert "approx_percent_change" not in coefficients
    assert np.allclose(
        coefficients.ratio_delay_plus_one, np.exp(coefficients.coefficient_log_scale)
    )
    specification = json.loads((paths.tables / "model_specification.json").read_text())
    assert specification["ols_rows_excluded_missing_weather"] == 1
    assert specification["split_strategy"] == "chronological_by_service_date"
    assert (paths.tables / "holdout_coverage.csv").exists()
    assert specification["group_mean_baseline"]["minimum_training_rows_per_group"] == 10
