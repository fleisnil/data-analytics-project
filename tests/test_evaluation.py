import numpy as np
import pandas as pd
import pytest

from sptdelays import modeling
from sptdelays.evaluation import paired_day_comparison, rolling_date_splits


def _study(days=10, calls_per_day=20):
    n = days * calls_per_day
    dates = np.repeat(pd.date_range("2026-09-01", periods=days).strftime("%Y-%m-%d"), calls_per_day)
    return pd.DataFrame({
        "service_date": dates, "region": ["A"] * n, "transport_mode": ["train"] * n,
        "day_period": ["midday"] * n, "delay_minutes": np.arange(n) % 4,
        "scheduled_hour": np.arange(n) % 24, "precipitation": np.arange(n) / n,
    })


def test_date_splits_preserve_whole_dates_even_when_shuffled_and_unequal():
    data = _study()
    data = pd.concat([data, data.iloc[:13]]).sample(frac=1, random_state=4)
    seen = set()
    folds = list(rolling_date_splits(data))
    assert len(folds) == 3
    for train, validation in folds:
        assert train.service_date.max() < validation.service_date.min()
        assert set(train.service_date).isdisjoint(validation.service_date)
        assert seen.isdisjoint(validation.service_date)
        seen.update(validation.service_date)
        for day in validation.service_date.unique():
            assert validation.service_date.eq(day).sum() == data.service_date.eq(day).sum()


def test_one_day_does_not_fake_temporal_validation():
    assert list(rolling_date_splits(_study(days=1, calls_per_day=500))) == []
    data = _study()
    data.loc[0, "service_date"] = "bad"
    with pytest.raises(ValueError, match="Valid service dates"):
        list(rolling_date_splits(data))


def test_rolling_validation_never_receives_final_holdout_and_records_fold_features(monkeypatch):
    data = _study()
    development, holdout = modeling._split(data, 42)
    original = modeling._fit_comparison
    seen = []

    def observe(train, validation, *args):
        assert set(train.service_date).isdisjoint(holdout.service_date)
        assert set(validation.service_date).isdisjoint(holdout.service_date)
        assert train.service_date.max() < validation.service_date.min()
        result = original(train, validation, *args)
        assert result[1]["baseline_delay"] == pytest.approx(train.delay_minutes.mean())
        seen.append(len(train))
        return result

    monkeypatch.setattr(modeling, "_fit_comparison", observe)
    metrics, spec = modeling._rolling_validation(
        development, ["scheduled_hour", "precipitation"], ["region", "transport_mode", "day_period"], 42
    )
    assert spec["status"] == "evaluated"
    assert len(metrics) == 4 * len(seen)
    assert seen == sorted(seen)
    assert all(fold["weather_features"] == ["precipitation"] for fold in spec["folds"])
    assert metrics.validation_last_date.max() < holdout.service_date.min()


def test_weather_ablation_uses_same_rows_but_excludes_all_weather(monkeypatch):
    data = _study()
    train, test = modeling._split(data, 42)
    numeric = ["scheduled_hour", "precipitation"]
    categorical = ["region", "transport_mode", "day_period"]
    seen = []
    original = modeling._make_pipeline

    def observe(numeric, categorical, seed):
        seen.append(list(numeric))
        return original(numeric, categorical, seed)

    monkeypatch.setattr(modeling, "_make_pipeline", observe)
    _, predictions, _, info = modeling._fit_comparison(train, test, numeric, categorical, 42)
    assert seen == [["scheduled_hour", "precipitation"], ["scheduled_hour"]]
    assert "precipitation" not in info["without_weather_features"]
    assert {len(values) for values in predictions.values()} == {len(test)}
    # Changing holdout targets must never change fitted predictions or baselines.
    _, changed, _, _ = modeling._fit_comparison(
        train, test.assign(delay_minutes=99999), numeric, categorical, 42
    )
    for key in predictions:
        np.testing.assert_allclose(predictions[key], changed[key])


def test_all_missing_training_weather_is_not_rescued_by_test_values():
    train, test = modeling._split(_study(), 42)
    train["precipitation"] = np.nan
    _, predictions, _, info = modeling._fit_comparison(
        train, test, ["scheduled_hour", "precipitation"], ["region"], 42
    )
    assert info["weather_ablation_status"] == "no_usable_weather_features"
    assert info["dropped_all_missing_training_features"] == ["precipitation"]
    np.testing.assert_array_equal(predictions["predicted_delay"], predictions["no_weather_delay"])


def _predictions(days=6):
    data = _study(days=days)
    data["predicted_delay"] = data.delay_minutes + 1
    data["reference"] = data.delay_minutes.astype(float) + 2
    return data


def test_paired_day_bootstrap_direction_reproducibility_and_identical_models():
    frame = _predictions()
    result = paired_day_comparison(frame, "reference", repetitions=100)
    assert set(result.status) == {"exploratory_day_bootstrap"}
    assert result.difference_rf_minus_reference.tolist() == pytest.approx([-1, -1])
    assert result.ci_low.tolist() == pytest.approx([-1, -1])
    assert result.ci_high.tolist() == pytest.approx([-1, -1])
    pd.testing.assert_frame_equal(result, paired_day_comparison(frame, "reference", repetitions=100))
    frame["reference"] = frame.predicted_delay
    identical = paired_day_comparison(frame, "reference", repetitions=100)
    assert identical[["difference_rf_minus_reference", "ci_low", "ci_high"]].eq(0).all().all()


def test_bootstrap_matches_explicit_whole_day_resampling_with_unequal_day_counts():
    frame = _predictions()
    frame = pd.concat([frame, frame.iloc[:10]], ignore_index=True)
    frame["predicted_delay"] += np.arange(len(frame)) / 30
    result = paired_day_comparison(frame, "reference", repetitions=100, seed=12)
    rng = np.random.default_rng(12)
    groups = [group for _, group in frame.groupby("service_date", sort=True)]
    differences = []
    for _ in range(100):
        sample = pd.concat([groups[index] for index in rng.integers(0, len(groups), len(groups))])
        error = sample.predicted_delay - sample.delay_minutes
        ref_error = sample.reference - sample.delay_minutes
        differences.append([error.abs().mean() - ref_error.abs().mean(),
                            np.sqrt(np.mean(error ** 2)) - np.sqrt(np.mean(ref_error ** 2))])
    expected = np.quantile(differences, [.025, .975], axis=0)
    np.testing.assert_allclose(result.ci_low, expected[0])
    np.testing.assert_allclose(result.ci_high, expected[1])


def test_many_rows_on_one_day_do_not_justify_confidence_intervals():
    result = paired_day_comparison(_predictions(days=1), "reference", repetitions=100)
    assert result.ci_low.isna().all() and result.ci_high.isna().all()
    assert set(result.status) == {"insufficient_test_dates"}
    assert result.bootstrap_repetitions.eq(0).all()


@pytest.mark.parametrize("invalid", [np.nan, np.inf])
def test_nonfinite_paired_predictions_are_not_silently_dropped(invalid):
    frame = _predictions()
    frame.loc[0, "reference"] = invalid
    with pytest.raises(ValueError, match="finite predictions"):
        paired_day_comparison(frame, "reference")


def test_metrics_report_signed_bias_and_tail_error():
    metrics = modeling._metrics(pd.Series([2.0, 4.0]), np.array([1.0, 2.0]), "test")
    assert metrics["mean_error_pred_minus_actual"] == -1.5
    assert metrics["p90_absolute_error"] == pytest.approx(1.9)
