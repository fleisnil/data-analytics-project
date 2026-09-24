import pandas as pd

from sptdelays.quality import assess_data

SETTINGS = {
    "maximum_plausible_delay_minutes": 180, "delay_threshold_minutes": 5,
    "weather_hourly_variables": ["precipitation"],
}


def sample():
    return pd.DataFrame({
        "observation_id": ["a", "b"], "station_id": ["8500001", "8500002"],
        "scheduled_time": ["2026-09-17T10:10:00Z", "2026-09-17T11:10:00Z"],
        "observation_hour": ["2026-09-17T10:00:00Z", "2026-09-17T11:00:00Z"],
        "service_date": ["2026-09-17"] * 2, "region": ["Zurich", "Zurich"],
        "transport_mode": ["train", "bus"], "day_period": ["midday", "midday"],
        "delay_minutes": [0, 5], "is_delayed_5": [0, 1], "precipitation": [0.0, 0.0],
    })


def test_valid_single_day_data_remain_development():
    result = assess_data(sample(), SETTINGS)
    assert result["errors"] == 0
    assert result["status"] == "development"
    assert result["coverage"]["service_dates"] == 1
    assert result["manual_requirements"]


def test_duplicate_keys_invalid_target_and_wrong_hour_fail():
    frame = sample()
    frame.loc[1, "observation_id"] = "a"
    frame.loc[1, "delay_minutes"] = -1
    frame.loc[1, "observation_hour"] = "2026-09-17T10:00:00Z"
    result = assess_data(frame, SETTINGS)
    failed = {c["check"] for c in result["checks"] if not c["passed"]}
    assert result["status"] == "invalid"
    assert {"unique_observation_keys", "valid_delay_target", "hour_key_matches_schedule"} <= failed


def test_missing_columns_returns_actionable_audit():
    result = assess_data(pd.DataFrame({"other": [1]}), SETTINGS)
    assert result["errors"] == 1
    assert result["checks"][0]["check"] == "required_columns"


def test_joined_rows_with_missing_weather_do_not_count_as_complete():
    frame = sample()
    frame.loc[1, "precipitation"] = float("nan")
    result = assess_data(frame, SETTINGS)
    assert result["coverage"]["complete_weather_share"] == .5
    assert not next(c for c in result["checks"] if c["check"] == "weather_coverage")["passed"]


def test_absent_weather_columns_are_structural_error():
    result = assess_data(sample().drop(columns="precipitation"), SETTINGS)
    assert result["status"] == "invalid"
    assert not next(c for c in result["checks"] if c["check"] == "weather_columns_present")["passed"]


def test_bad_dates_report_error_without_crashing():
    frame = sample()
    frame["service_date"] = "invalid"
    result = assess_data(frame, SETTINGS)
    assert result["status"] == "invalid"
    assert result["coverage"]["first_date"] is None
