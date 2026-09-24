import pandas as pd

from sptdelays import collect_live
from sptdelays.settings import ProjectPaths


def test_collection_preserves_legacy_csv_and_writes_independent_snapshots(tmp_path, monkeypatch):
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    legacy = paths.interim / "live_observations.csv"
    legacy.write_bytes(b"observation_id\nlegacy\n")
    pd.DataFrame([{
        "observed_at_utc": "2026-09-17T10:00:00Z", "raw_file": "old.json",
        "cumulative_snapshot_rows": 0,
    }]).to_csv(paths.interim / "collection_log.csv", index=False)
    station = pd.DataFrame([{
        "station_id": "8503000", "station_name": "Zurich HB", "region": "Zurich",
        "canton": "ZH", "station_type": "rail_hub",
    }])
    payload = {"stationboard": [{
        "name": "IC 1", "to": "Bern", "operator": "SBB", "category": "IC",
        "number": "1", "stop": {
            "departure": "2030-01-01T10:00:00+01:00",
            "prognosis": {"departure": "2030-01-01T10:05:00+01:00"},
            "station": {"id": "8503000", "name": "Zurich HB"},
        },
    }]}
    monkeypatch.setattr(collect_live, "PATHS", paths)
    monkeypatch.setattr(collect_live, "load_station_panel", lambda: station)
    monkeypatch.setattr(collect_live, "load_settings", lambda: {
        "transport_api": "https://example.invalid", "live_stationboard_limit": 1,
        "request_timeout_seconds": 1, "request_pause_seconds": 0,
    })
    monkeypatch.setattr(collect_live, "get_json", lambda *args, **kwargs: payload)
    monkeypatch.setattr(collect_live.time, "sleep", lambda _: None)

    assert len(collect_live.collect_live()) == 1
    assert len(collect_live.collect_live()) == 1
    assert legacy.read_bytes() == b"observation_id\nlegacy\n"
    parts = list((paths.interim / "live_snapshots").glob("stationboards_*.csv"))
    assert len(parts) == 2
    assert len(list((paths.raw / "transport_live").glob("stationboards_*.json"))) == 2
    log = pd.read_csv(paths.interim / "collection_log.csv")
    assert log["cumulative_snapshot_rows"].tolist() == [0, 2, 3]
    assert set(log["normalized_file"].dropna()) == {part.name for part in parts}
