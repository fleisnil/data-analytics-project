from datetime import date

import numpy as np
import pandas as pd
import pytest

from sptdelays import collect_weather as weather
from sptdelays.settings import ProjectPaths

VARIABLES = ["temperature_2m", "precipitation"]
STATION = pd.Series({"station_id": "8503000", "station_name": "Zurich"})


def _payload(times=None, **columns):
    return {"hourly": {"time": times or ["2026-09-17T10:00"],
                       "temperature_2m": [10.0], "precipitation": [0.0], **columns}}


def _frame(payload=None, source="archive_reanalysis"):
    return weather._hourly_frame(payload or _payload(), STATION, "https://example.invalid",
                                 source, "2026-10-02T10:00:00Z", VARIABLES)


def test_weather_windows_do_not_overlap_or_leave_gaps():
    settings = {"weather_archive_api": "archive", "weather_forecast_api": "forecast"}
    result = weather._weather_windows(date(2026, 9, 25), date(2026, 10, 1), settings,
                                      today=date(2026, 10, 2))
    assert result == [(date(2026, 9, 25), date(2026, 9, 27), "archive", "archive_reanalysis"),
                      (date(2026, 9, 28), date(2026, 10, 1), "forecast", "forecast_recent")]


@pytest.mark.parametrize("times", [["bad"], ["2026-09-17T10:30"],
                                    ["2026-09-17T10:00", "2026-09-17T10:00"]])
def test_weather_rejects_invalid_rounded_or_duplicate_hours(times):
    payload = _payload(times, temperature_2m=[10] * len(times), precipitation=[0] * len(times))
    with pytest.raises(ValueError, match="UTC hour"):
        _frame(payload)


def test_weather_rejects_missing_variables_and_tracks_null_values():
    payload = _payload()
    del payload["hourly"]["precipitation"]
    with pytest.raises(ValueError, match="missing requested variables"):
        _frame(payload)
    result = _frame(_payload(temperature_2m=["invalid"], precipitation=[np.inf]))
    assert result[VARIABLES].isna().all().all()


def test_incomplete_update_preserves_whole_prior_row_and_provenance():
    old = _frame(source="forecast_recent")
    new = _frame(_payload(temperature_2m=[99.0], precipitation=[None]))
    merged, audit = weather._merge_weather_updates(old, new, VARIABLES)
    assert merged.temperature_2m.tolist() == [10.0]
    assert merged.precipitation.tolist() == [0.0]
    assert merged.weather_source.tolist() == ["forecast_recent"]
    assert audit.decision.tolist() == ["retained_more_complete_prior"]
    assert audit.incoming_source.tolist() == ["archive_reanalysis"]
    assert audit.prior_valid_variables.tolist() == [2]
    assert audit.incoming_valid_variables.tolist() == [1]


def test_complete_update_replaces_prior_and_new_hours_are_added():
    old = _frame(source="forecast_recent")
    new = _frame(_payload(temperature_2m=[11.0]))
    second = new.assign(observation_hour="2026-09-17T11:00:00+0000")
    incoming = pd.concat([new, second], ignore_index=True)
    merged, audit = weather._merge_weather_updates(old, incoming, VARIABLES)
    assert merged.temperature_2m.tolist() == [11.0, 11.0]
    assert set(merged.weather_source) == {"archive_reanalysis"}
    assert audit.decision.tolist() == ["updated", "added"]
    first, first_audit = weather._merge_weather_updates(pd.DataFrame(), incoming, VARIABLES)
    assert len(first) == 2
    assert set(first_audit.decision) == {"added"}


def test_legacy_weather_and_duplicate_update_keys():
    old = _frame().drop(columns=["weather_source", "weather_fetched_at"])
    new = _frame(_payload(precipitation=[None]))
    merged, _ = weather._merge_weather_updates(old, new, VARIABLES)
    assert merged.weather_source.tolist() == ["legacy_unspecified"]
    duplicate = pd.concat([new, new.assign(station_id="008503000")])
    with pytest.raises(ValueError, match="duplicate station-hour"):
        weather._merge_weather_updates(old, duplicate, VARIABLES)


def test_failed_csv_write_preserves_existing_file_and_cleans_private_temp(tmp_path, monkeypatch):
    path = tmp_path / "weather.csv"
    path.write_bytes(b"original\n")

    def fail_write(self, target, **kwargs):
        target.write_bytes(b"partial")
        raise OSError("disk write failed")

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail_write)
    with pytest.raises(OSError, match="disk write failed"):
        weather._write_csv_atomic(pd.DataFrame({"x": [1]}), path)
    assert path.read_bytes() == b"original\n"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("partial_success", [False, True])
def test_collection_keeps_better_previous_weather_and_logs_raw_response(
    tmp_path, monkeypatch, partial_success
):
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    pd.DataFrame([{"station_id": "8503000", "station_name": "Zurich", "latitude": 47.3,
                   "longitude": 8.5, "scheduled_time": "2026-09-17T10:00:00Z"}]).to_csv(
                       paths.interim / "transport_prepared.csv", index=False)
    saved = paths.interim / "weather_hourly.csv"
    _frame().to_csv(saved, index=False)
    before = saved.read_bytes()
    monkeypatch.setattr(weather, "PATHS", paths)
    monkeypatch.setattr(weather, "load_settings", lambda: {
        "weather_archive_api": "archive", "weather_forecast_api": "forecast",
        "weather_hourly_variables": VARIABLES, "request_timeout_seconds": 1,
        "request_pause_seconds": 0,
    })
    payload = _payload(precipitation=[None]) if partial_success else {"hourly": {"time": []}}
    monkeypatch.setattr(weather, "get_json", lambda *args, **kwargs: payload)
    if partial_success:
        weather.collect_weather()
        stored = pd.read_csv(saved)
        assert stored.precipitation.tolist() == [0.0]
        audit = pd.read_csv(paths.tables / "weather_update_audit.csv")
        assert audit.decision.tolist() == ["retained_more_complete_prior"]
    else:
        with pytest.raises(RuntimeError, match="No weather observations"):
            weather.collect_weather()
        assert saved.read_bytes() == before
    log = pd.read_csv(paths.interim / "weather_collection_log.csv")
    assert log.status.tolist() == ["ok" if partial_success else "failed"]
    assert (paths.raw / "weather" / log.raw_file.iloc[0]).is_file()
