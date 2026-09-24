import numpy as np
import pandas as pd

from sptdelays import statistics
from sptdelays.settings import ProjectPaths


def test_constant_anova_and_sparse_chi_square_have_explicit_status():
    frame = pd.DataFrame(
        {"region": ["A", "A", "B", "B"], "delay_minutes": [0.0] * 4, "is_delayed_5": [0, 1, 0, 1]}
    )
    anova = statistics._anova(frame, "region")
    assert anova["status"] == "constant_target"
    assert np.isnan(anova["p_value"])
    chi_square = statistics._chi_square(frame, "region")
    assert chi_square["status"] == "small_expected_counts"
    assert chi_square["minimum_expected_count"] == 1


def test_holm_correction_and_station_hour_correlation(tmp_path, monkeypatch):
    monkeypatch.setattr(statistics, "PATHS", ProjectPaths(tmp_path))
    frame = pd.DataFrame(
        {
            "station_id": ["A"] * 6 + ["B"] * 6,
            "observation_hour": [1, 1, 2, 2, 3, 3] * 2,
            "region": ["north"] * 6 + ["south"] * 6,
            "transport_mode": ["bus"] * 6 + ["train"] * 6,
            "day_period": ["morning"] * 6 + ["evening"] * 6,
            "delay_minutes": [0, 1, 2, 3, 1, 0, 4, 5, 6, 7, 5, 4],
            "is_delayed_5": [0] * 6 + [0, 1, 1, 1, 1, 0],
            "precipitation": [0, 0, 1, 1, 2, 2, 0, 0, 1, 1, 2, 2],
        }
    )
    results = statistics.run_statistical_tests(frame)
    valid = results.dropna(subset=["p_value"])
    assert (valid.p_value_holm >= valid.p_value).all()
    correlation = results.loc[results.test.str.startswith("Spearman")].iloc[0]
    assert correlation["n"] == 6
    assert correlation["unit"] == "station_hour_mean"
    assert (tmp_path / "reports/tables/statistical_tests.csv").exists()
