import numpy as np
import pandas as pd
import pytest

from sptdelays.clustering import _cluster_profiles


def test_clustering_handles_missing_features_and_duplicate_profiles():
    frame = pd.DataFrame(
        {"delay": [0.0, 0.0, 5.0, 5.0], "weather": [np.nan] * 4, "constant": [1.0] * 4}
    )
    labels, scores, coordinates, features = _cluster_profiles(frame, list(frame), 42)
    assert features == ["delay"]
    assert scores.k.tolist() == [2]
    assert len(set(labels)) == 2
    assert coordinates.shape == (4, 2)
    assert np.isfinite(coordinates).all()


def test_clustering_rejects_identical_profiles_instead_of_silhouette_error():
    frame = pd.DataFrame({"delay": [0.0] * 4})
    with pytest.raises(ValueError, match="non-constant"):
        _cluster_profiles(frame, ["delay"], 42)
