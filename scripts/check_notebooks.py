"""Validate the four submission notebooks against the saved project data."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Execute all code cells without saving outputs")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    notebooks = sorted((root / "notebooks").glob("*.ipynb"))
    if len(notebooks) != 4:
        raise ValueError(f"Expected four submission notebooks, found {len(notebooks)}.")
    for path in notebooks:
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        if args.execute:
            print(f"Executing {path.name}...", flush=True)
            NotebookClient(
                notebook, timeout=300, kernel_name="python3",
                resources={"metadata": {"path": str(root)}},
            ).execute()
        print(f"OK: {path.name}", flush=True)


if __name__ == "__main__":
    main()
