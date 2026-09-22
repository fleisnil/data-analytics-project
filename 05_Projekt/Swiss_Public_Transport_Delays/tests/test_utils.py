import pandas as pd

from sptdelays.utils import add_time_features, normalize_station_id, parse_transport_mode


def test_normalize_station_edge_id():
    assert normalize_station_id("850300012") == "8503000"
    assert normalize_station_id("8503000") == "8503000"


def test_transport_mode_mapping():
    assert parse_transport_mode("Zug") == "train"
    assert parse_transport_mode("BUS") == "bus"
    assert parse_transport_mode("Tram") == "tram"


def test_time_features_peak_and_weekend():
    frame = pd.DataFrame({"scheduled_time": ["2026-09-17T06:30:00+00:00", "2026-09-19T12:00:00+00:00"]})
    result = add_time_features(frame)
    assert result.loc[0, "is_peak"] == 1
    assert result.loc[1, "is_weekend"] == 1

