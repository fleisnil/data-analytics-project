import pandas as pd
import pytest

from sptdelays.utils import add_time_features, normalize_station_id, parse_transport_mode


def test_normalize_station_edge_id():
    assert normalize_station_id("850300012") == "8503000"
    assert normalize_station_id("8503000") == "8503000"
    assert normalize_station_id("008503000") == "8503000"
    assert normalize_station_id(8503000.0) == "8503000"
    assert normalize_station_id("ch:1:sloid:853000:12") == "ch:1:sloid:853000:12"


def test_transport_mode_mapping():
    assert parse_transport_mode("Zug") == "train"
    assert parse_transport_mode("BUS") == "bus"
    assert parse_transport_mode("Tram") == "tram"


@pytest.mark.parametrize("category, expected", [(None, "unknown"), (pd.NA, "unknown"), (float("nan"), "unknown"), ("S9", "train"), ("IR 13", "train"), ("B", "bus"), ("FUN", "cableway")])
def test_nullable_and_numbered_transport_categories(category, expected):
    assert parse_transport_mode(category) == expected


def test_time_features_peak_and_weekend():
    frame = pd.DataFrame({"scheduled_time": ["2026-09-17T06:30:00+00:00", "2026-09-19T12:00:00+00:00"]})
    result = add_time_features(frame)
    assert result.loc[0, "is_peak"] == 1
    assert result.loc[1, "is_weekend"] == 1


def test_dst_fallback_keeps_both_hours_distinct():
    frame = pd.DataFrame({"scheduled_time": ["2026-10-25T00:30:00Z", "2026-10-25T01:30:00Z"]})
    result = add_time_features(frame)
    assert result["scheduled_hour"].tolist() == [2, 2]
    assert result["observation_hour"].tolist() == ["2026-10-25T02:00:00+0200", "2026-10-25T02:00:00+0100"]


def test_peak_periods_match_peak_indicator():
    frame = pd.DataFrame({"scheduled_time": pd.date_range("2026-09-17", periods=24, freq="h", tz="Europe/Zurich")})
    result = add_time_features(frame)
    assert result["day_period"].isin(["morning_peak", "evening_peak"]).astype(int).equals(result["is_peak"])
