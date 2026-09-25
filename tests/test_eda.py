import pandas as pd

from sptdelays.eda import _daily_region_coverage


def test_daily_region_table_retains_empty_calendar_and_panel_cells():
    data = pd.DataFrame({
        "service_date": ["2026-09-01", "2026-09-03"],
        "region": ["A", "A"],
        "observation_id": ["a", "b"],
        "station_id": ["1", "1"],
        "transport_mode": ["train", "train"],
        "day_period": ["midday", "midday"],
        "delay_minutes": [2.0, 4.0],
    })
    result = _daily_region_coverage(data, ["A", "B"])
    assert len(result) == 6
    empty = result.set_index(["service_date", "region"]).loc[("2026-09-02", "B")]
    assert empty.station_calls == 0
    assert not empty.has_usable_calls
    assert pd.isna(empty.mean_delay)
