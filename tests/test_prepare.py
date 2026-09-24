import pandas as pd
import pytest

from sptdelays import prepare
from sptdelays.settings import ProjectPaths
from sptdelays.utils import add_time_features, stable_id


def test_stable_id_is_reproducible():
    assert stable_id(["a", 1, None]) == stable_id(["a", 1, None])
    assert stable_id(["a", 1, None]) != stable_id(["a", 2, None])
    assert stable_id(["a|b", "c"]) != stable_id(["a", "b|c"])
    assert stable_id([None]) == stable_id([pd.NA]) == stable_id([float("nan")])


def test_observation_hour_is_created():
    frame = pd.DataFrame({"scheduled_time": ["2026-09-17T13:34:00+02:00"]})
    result = add_time_features(frame)
    assert result.loc[0, "observation_hour"].startswith("2026-09-17T13:00:00")


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    settings = {"delay_threshold_minutes": 5, "maximum_plausible_delay_minutes": 180, "weather_hourly_variables": ["temperature_2m", "precipitation"]}
    station = pd.DataFrame([{"station_id": "8503000", "station_name": "Zürich HB", "region": "Zürich", "canton": "ZH", "station_type": "rail_hub", "latitude": 47.38, "longitude": 8.54}])
    monkeypatch.setattr(prepare, "PATHS", paths)
    monkeypatch.setattr(prepare, "load_settings", lambda: settings)
    monkeypatch.setattr(prepare, "load_station_panel", lambda: station.copy())
    return paths


def _live_row(**changes):
    return {"data_source": "transport_opendata_live", "station_id": "8503000", "station_name": "Zürich HB", "journey_id": "001", "operator": "SBB", "category_raw": "S9", "line": "9", "destination": "Uster", "scheduled_time": "2026-09-17T14:00:00+0200", "reported_time": "2026-09-17T14:05:00+0200", "observed_at": "2026-09-17T11:59:00Z", "delay_minutes_signed": 5, **changes}


def test_latest_snapshot_not_file_order_and_direction_part_of_key(isolated_data):
    rows = [_live_row(delay_minutes_signed=9), _live_row(observed_at="2026-09-17T11:50:00Z", delay_minutes_signed=2), _live_row(destination="Schaffhausen", delay_minutes_signed=0)]
    pd.DataFrame(rows).to_csv(isolated_data.interim / "live_observations.csv", index=False)
    result = prepare.prepare_transport()
    assert len(result) == 2
    assert result.loc[result["destination"].eq("Uster"), "delay_minutes"].item() == 9
    assert result["journey_id"].unique().tolist() == ["001"]
    assert result["cancelled"].isna().all()
    audit = pd.read_csv(isolated_data.tables / "preparation_audit.csv").set_index("integration_step")["row_count"]
    assert audit["duplicate_rows_removed"] == 1
    assert audit["station_join_row_gain_or_loss"] == 0


def test_prepare_combines_legacy_and_immutable_snapshot_parts(isolated_data):
    pd.DataFrame([_live_row(delay_minutes_signed=2)]).to_csv(
        isolated_data.interim / "live_observations.csv", index=False
    )
    parts = isolated_data.interim / "live_snapshots"
    parts.mkdir()
    pd.DataFrame([_live_row(observed_at="2026-09-17T12:05:00Z", delay_minutes_signed=8)]).to_csv(
        parts / "stationboards_new.csv", index=False
    )
    result = prepare.prepare_transport()
    assert len(result) == 1
    assert result["delay_minutes"].iloc[0] == 8
    audit = pd.read_csv(isolated_data.tables / "preparation_audit.csv").set_index("integration_step")["row_count"]
    assert audit["raw_rows"] == 2
    assert audit["duplicate_rows_removed"] == 1


def test_missing_latest_delay_is_not_on_time_or_stale_prior_delay(isolated_data):
    rows = [_live_row(delay_minutes_signed=None), _live_row(observed_at="2026-09-17T11:50:00Z", delay_minutes_signed=2), _live_row(journey_id="002", delay_minutes_signed=0), _live_row(journey_id="003", delay_minutes_signed=-999), _live_row(journey_id="004", delay_minutes_signed=float("inf"))]
    pd.DataFrame(rows).to_csv(isolated_data.interim / "live_observations.csv", index=False)
    result = prepare.prepare_transport()
    assert result["journey_id"].tolist() == ["002"]
    assert result["is_delayed_5"].tolist() == [0]
    audit = pd.read_csv(isolated_data.tables / "preparation_audit.csv").set_index("integration_step")["row_count"]
    assert audit["excluded_missing_delay"] == 1
    assert audit["excluded_implausible_signed_delay"] == 1
    assert audit["excluded_nonfinite_delay"] == 1
    losses = audit.filter(like="excluded_").sum() + audit["duplicate_rows_removed"]
    assert losses == audit["rows_lost_total"] == audit["raw_rows"] - audit["prepared_rows"]


def _write_join_inputs(paths):
    transport = pd.DataFrame({"observation_id": ["a", "b", "c"], "station_id": ["8503000"] * 3, "observation_hour": ["2026-10-25T02:00:00+0200", "2026-10-25T02:00:00+0100", "2026-10-25T03:00:00+0100"], "region": ["Zürich"] * 3, "transport_mode": ["train"] * 3})
    weather = pd.DataFrame({"station_id": ["008503000"] * 2, "observation_hour": ["2026-10-25T00:00:00Z", "2026-10-25T01:00:00Z"], "temperature_2m": [8, 9], "precipitation": [0, None]})
    transport.to_csv(paths.interim / "transport_prepared.csv", index=False)
    weather.to_csv(paths.interim / "weather_hourly.csv", index=False)
    return weather


def test_weather_join_utc_dst_missingness_and_preserved_rows(isolated_data):
    _write_join_inputs(isolated_data)
    result = prepare.integrate_weather()
    assert len(result) == 3
    assert result["temperature_2m"].iloc[:2].tolist() == [8, 9]
    assert result["weather_matched"].tolist() == [True, True, False]
    assert result["weather_complete"].tolist() == [True, False, False]
    audit = pd.read_csv(isolated_data.tables / "integration_audit.csv").set_index("metric")["value"]
    assert audit["row_gain_or_loss"] == 0
    assert audit["weather_matched_but_incomplete"] == 1
    assert audit["weather_unmatched"] == 1


def test_conflicting_weather_duplicates_cannot_multiply_transport_rows(isolated_data):
    weather = _write_join_inputs(isolated_data)
    conflicting = weather.iloc[[0]].assign(temperature_2m=12)
    pd.concat([weather, conflicting]).to_csv(isolated_data.interim / "weather_hourly.csv", index=False)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        prepare.integrate_weather()


def test_actuals_ambiguous_and_nonexistent_wall_times_are_not_guessed():
    parsed = prepare._parse_local(pd.Series(["25.10.2026 02:30:00", "29.03.2026 02:30:00", "17.09.2026 14:30:00"]))
    assert parsed.isna().tolist() == [True, True, False]
