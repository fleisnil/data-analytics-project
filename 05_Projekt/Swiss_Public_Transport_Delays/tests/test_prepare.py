import pandas as pd

from sptdelays.utils import add_time_features, stable_id


def test_stable_id_is_reproducible():
    assert stable_id(["a", 1, None]) == stable_id(["a", 1, None])
    assert stable_id(["a", 1, None]) != stable_id(["a", 2, None])


def test_observation_hour_is_created():
    frame = pd.DataFrame({"scheduled_time": ["2026-09-17T13:34:00+02:00"]})
    result = add_time_features(frame)
    assert result.loc[0, "observation_hour"].startswith("2026-09-17T13:00:00")

