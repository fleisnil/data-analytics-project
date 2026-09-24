import json
import shutil
import sqlite3
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from sptdelays import database, duckdb_store
from sptdelays.settings import ProjectPaths


@pytest.fixture
def storage_project(tmp_path, monkeypatch):
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    shutil.copytree(Path(__file__).resolve().parents[1] / "sql", tmp_path / "sql")
    monkeypatch.setattr(database, "PATHS", paths)
    monkeypatch.setattr(duckdb_store, "PATHS", paths)
    frame = pd.DataFrame({
        "observation_id": ["one", "two", "three"],
        "station_id": ["001", "001", "002"],
        "station_name": ["A", "A", "B"],
        "region": ["North", "North", "South"],
        "canton": ["ZH", "ZH", "TI"],
        "station_type": ["rail_hub"] * 3,
        "latitude": [47.0, 47.0, 46.0],
        "longitude": [8.0] * 3,
        "observation_hour": ["2026-09-01T10:00:00+0200"] * 3,
        "transport_mode": ["train"] * 3,
        "scheduled_hour": [10] * 3,
        "delay_minutes": [0.0, 10.0, 2.0],
        "is_delayed_5": [0, 1, 0],
        "temperature_2m": [10.0, 10.0, None],
        "precipitation": [0.5, 0.5, None],
    })
    frame.to_csv(paths.processed / "model_data.csv", index=False)
    return paths, frame


def test_sqlite_and_duckdb_preserve_keys_population_and_means(storage_project):
    paths, _ = storage_project
    sqlite_path = database.build_sqlite()
    duckdb_path = duckdb_store.build_duckdb()
    with sqlite3.connect(sqlite_path) as connection:
        assert connection.execute("SELECT station_id FROM stations ORDER BY station_id").fetchall() == [
            ("001",), ("002",)
        ]
        assert connection.execute("SELECT COUNT(*) FROM weather_hourly").fetchone()[0] == 1
        sqlite_rows = connection.execute(
            "SELECT s.region, COUNT(*), AVG(o.delay_minutes) "
            "FROM observations o JOIN stations s ON o.station_id=s.station_id "
            "GROUP BY s.region ORDER BY s.region"
        ).fetchall()
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE observations SET station_id='missing' WHERE observation_id='one'")
    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        duckdb_rows = connection.execute(
            "SELECT region, observations, mean_delay_minutes FROM delay_region_mode ORDER BY region"
        ).fetchall()
    assert sqlite_rows == duckdb_rows == [("North", 2, 5.0), ("South", 1, 2.0)]
    for engine in ["sqlite", "duckdb"]:
        audit = json.loads((paths.tables / f"{engine}_storage_audit.json").read_text())
        assert audit["row_gain_or_loss"] == 0
        assert audit["joined_observations"] == 3
        assert audit["observations_without_weather_values"] == 1


@pytest.mark.parametrize("column, value, message", [
    ("observation_id", "one", "Duplicate observation_id"),
    ("station_name", "Conflicting A", "Conflicting station metadata"),
    ("precipitation", 42, "Conflicting weather values"),
    ("station_id", None, "Missing database key"),
])
def test_invalid_keys_or_conflicting_dimensions_are_rejected(storage_project, column, value, message):
    paths, frame = storage_project
    frame.loc[1, column] = value
    frame.to_csv(paths.processed / "model_data.csv", index=False)
    with pytest.raises(ValueError, match=message):
        database.normalized_tables(paths.processed / "model_data.csv")


@pytest.mark.parametrize("builder, filename, query_file", [
    (database.build_sqlite, "sptdelays.sqlite", "sqlite_analysis.sql"),
    (duckdb_store.build_duckdb, "sptdelays.duckdb", "duckdb_analysis.sql"),
])
def test_query_failure_preserves_existing_database(storage_project, builder, filename, query_file):
    paths, _ = storage_project
    builder()
    before = (paths.database / filename).read_bytes()
    (paths.root / "sql" / query_file).write_text(
        "-- name: broken\nSELECT * FROM missing_table;", encoding="utf-8"
    )
    with pytest.raises(Exception, match="missing_table"):
        builder()
    assert (paths.database / filename).read_bytes() == before
    assert sorted(path.name for path in paths.database.iterdir()) == [filename]
