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
    assert set(subgroups.model) == {"random_forest", "forest_without_weather", "mean_baseline", "group_mean_baseline"}
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
    assert specification["weather_ablation_status"] == "evaluated"
    assert specification["ols_reference_categories"]["C(region)"] == "A"
    assert specification["ols_reference_categories"]["C(transport_mode)"] == "bus"
    assert specification["temporal_validation_status"] == "insufficient_development_data"
    intervals = pd.read_csv(paths.tables / "paired_model_comparisons.csv")
    assert intervals.ci_low.isna().all()
    assert intervals.status.eq("insufficient_test_dates").all()
    assert pd.read_csv(paths.tables / "temporal_validation.csv").empty

    from sptdelays import reporting

    monkeypatch.setattr(reporting, "PATHS", paths)
    (paths.tables / "quality_audit.json").write_text(json.dumps({
        "status": "development", "errors": 0, "warnings": 1,
        "coverage": {"rows": 80, "service_dates": 2, "regions": ["A", "B"], "stations": 8},
        "checks": [{"passed": False, "check": "study_duration", "detail": "Need more dates"}],
    }))
    reporting.write_analysis_summary()
    summary = (paths.root / "reports/analysis_summary.md").read_text(encoding="utf-8")
    assert "No temporal stability claim" in summary
    assert "Need more dates" in summary
    assert "not a percent change in arithmetic mean delay" in summary
    assert "forest_without_weather" in summary
    assert (paths.figures / "08_model_comparison.png").stat().st_size > 1000


def test_multiday_end_to_end_evaluation_keeps_holdout_separate(tmp_path, monkeypatch):
    """Synthetic test data stay in a private temp folder, never in the actual study."""
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    monkeypatch.setattr(modeling, "PATHS", paths)
    monkeypatch.setattr(modeling, "load_settings", lambda: {"random_seed": 42})
    rng = np.random.default_rng(14)
    n = 500
    dates = pd.Series(np.repeat(pd.date_range("2026-09-01", periods=25), 20))
    frame = pd.DataFrame({
        "observation_id": [f"test-{i}" for i in range(n)],
        "station_id": [f"station-{i % 8}" for i in range(n)],
        "service_date": dates.dt.strftime("%Y-%m-%d"),
        "scheduled_time": dates.dt.strftime("%Y-%m-%dT10:00:00Z"),
        "region": ["A", "B"] * (n // 2),
        "transport_mode": ["bus", "bus", "train", "train"] * (n // 4),
        "day_period": ["midday"] * n,
        "is_weekend": dates.dt.dayofweek.ge(5).astype(int),
        "precipitation": rng.uniform(0, 5, n),
        "delay_minutes": rng.exponential(size=n),
    })
    frame.to_csv(paths.processed / "model_data.csv", index=False)
    modeling.run_models()
    specification = json.loads((paths.tables / "model_specification.json").read_text())
    temporal = json.loads((paths.tables / "temporal_validation.json").read_text())
    assert temporal["status"] == "evaluated"
    assert len(temporal["folds"]) == 3
    for fold in temporal["folds"]:
        assert max(fold["train_dates"]) < min(fold["validation_dates"])
        assert max(fold["validation_dates"]) < min(specification["test_dates"])
    assert len(pd.read_csv(paths.tables / "temporal_validation.csv")) == 12
    comparisons = pd.read_csv(paths.tables / "paired_model_comparisons.csv")
    assert comparisons.status.eq("exploratory_day_bootstrap").all()
    assert comparisons.test_dates.eq(5).all()
    assert comparisons.ci_low.notna().all()
    assert comparisons.ci_low.le(comparisons.ci_high).all()
    from sptdelays import reporting

    monkeypatch.setattr(reporting, "PATHS", paths)
    (paths.tables / "quality_audit.json").write_text(json.dumps({
        "status": "development", "errors": 0, "warnings": 1,
        "coverage": {"rows": n, "service_dates": 25, "regions": ["A", "B"], "stations": 8},
        "checks": [{"passed": False, "check": "study_duration", "detail": "25/28 dates"}],
    }))
    reporting.write_analysis_summary()
    summary = (paths.root / "reports/analysis_summary.md").read_text(encoding="utf-8")
    assert "No temporal stability claim" not in summary
    assert "exploratory_day_bootstrap" in summary
    assert "25/28 dates" in summary
