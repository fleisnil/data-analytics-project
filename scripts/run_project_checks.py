"""Run local code checks without sharing pytest's user-wide temporary directory."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def run_checks() -> int:
    root = Path(__file__).resolve().parents[1]
    # pytest may clear --basetemp; give it only a new child of our private directory.
    with tempfile.TemporaryDirectory(prefix="sptdelays-checks-") as temporary:
        commands = [
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "--basetemp", str(Path(temporary) / "pytest")],
            [sys.executable, "-m", "ruff", "check", "--no-cache", "src", "tests", "scripts"],
        ]
        for command in commands:
            print(f"\nRunning {command[2]} ...", flush=True)
            result = subprocess.run(command, cwd=root, check=False)
            if result.returncode:
                return result.returncode
    print("\nProject checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_checks())
