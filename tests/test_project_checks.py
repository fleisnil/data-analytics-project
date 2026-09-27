"""The VS Code check runner isolates temporary files and preserves failures."""

import runpy
from pathlib import Path
from types import SimpleNamespace


def test_runner_uses_private_pytest_directory_and_runs_ruff(monkeypatch):
    namespace = runpy.run_path(str(Path(__file__).parents[1] / "scripts/run_project_checks.py"))
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[2] == "pytest":
            base = Path(command[command.index("--basetemp") + 1])
            assert base.name == "pytest"
            assert base.parent.name.startswith("sptdelays-checks-")
            assert base.parent.is_dir()
            assert not base.exists()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(namespace["subprocess"], "run", run)
    assert namespace["run_checks"]() == 0
    assert [command[2] for command, _ in calls] == ["pytest", "ruff"]
    assert all(kwargs["cwd"] == Path(__file__).parents[1] for _, kwargs in calls)


def test_runner_stops_and_returns_pytest_failure(monkeypatch):
    namespace = runpy.run_path(str(Path(__file__).parents[1] / "scripts/run_project_checks.py"))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr(namespace["subprocess"], "run", run)
    assert namespace["run_checks"]() == 2
    assert len(calls) == 1
