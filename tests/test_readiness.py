import json
import sys

import pytest

from sptdelays import cli, pipeline, readiness
from sptdelays.readiness import inspect_readiness, require_pipeline_inputs
from sptdelays.settings import ProjectPaths


def _inputs(tmp_path, source="live"):
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    paths.config.mkdir()
    (paths.config / "study.json").write_text("{}")
    (paths.config / "stations.csv").write_text("station_id\n8503000\n")
    (paths.interim / "weather_hourly.csv").write_text("station_id\n8503000\n")
    if source == "live":
        path = paths.interim / "live_observations.csv"
    else:
        path = paths.raw / "actuals_v2" / "2026-09-17_selected_stations.csv"
        path.parent.mkdir()
    path.write_text("station_id\n8503000\n")
    return paths, path


def test_fresh_checkout_reports_all_missing_inputs_without_writing(tmp_path):
    paths = ProjectPaths(tmp_path)
    result = inspect_readiness(paths)
    assert not result["ready"]
    assert all(not check["ready"] for check in result["checks"])
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(FileNotFoundError, match="collect-live"):
        require_pipeline_inputs(paths, "live")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("source", ["live", "actuals"])
def test_readiness_checks_selected_source_and_nonempty_inputs(tmp_path, source):
    paths, transport = _inputs(tmp_path, source)
    assert inspect_readiness(paths, source)["ready"]
    assert require_pipeline_inputs(paths, source) == [transport]
    other = "actuals" if source == "live" else "live"
    assert not inspect_readiness(paths, other)["ready"]
    transport.write_bytes(b"")
    assert not inspect_readiness(paths, source)["ready"]


def test_broken_resolved_panel_not_hidden_by_config_fallback(tmp_path):
    paths, _ = _inputs(tmp_path)
    (paths.interim / "stations_resolved.csv").write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="stations_resolved"):
        require_pipeline_inputs(paths, "live")


def test_pipeline_preflight_preserves_previous_manifest(tmp_path, monkeypatch):
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    manifest = paths.tables / "run_manifest.json"
    manifest.write_text(json.dumps({"status": "completed", "previous": True}))
    before = manifest.read_bytes()
    monkeypatch.setattr(pipeline, "PATHS", paths)
    with pytest.raises(FileNotFoundError, match="Analysis cannot start"):
        pipeline.run_pipeline()
    assert manifest.read_bytes() == before


def test_doctor_missing_inputs_exit_code_and_next_steps(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "PATHS", ProjectPaths(tmp_path))
    monkeypatch.setattr(sys, "argv", ["sptdelays", "doctor"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "[MISSING] Transport inputs" in output
    assert "Next:" in output
    assert list(tmp_path.iterdir()) == []


def test_pipeline_cli_missing_inputs_is_concise(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "PATHS", ProjectPaths(tmp_path))
    monkeypatch.setattr(sys, "argv", ["sptdelays", "pipeline"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    message = capsys.readouterr().err
    assert "Analysis cannot start yet" in message
    assert "Traceback" not in message
