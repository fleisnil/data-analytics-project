from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path = PROJECT_ROOT

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def interim(self) -> Path:
        return self.root / "data" / "interim"

    @property
    def processed(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def database(self) -> Path:
        return self.root / "database"

    @property
    def figures(self) -> Path:
        return self.root / "reports" / "figures"

    @property
    def tables(self) -> Path:
        return self.root / "reports" / "tables"

    def ensure(self) -> None:
        for path in (
            self.raw,
            self.interim,
            self.processed,
            self.database,
            self.figures,
            self.tables,
        ):
            path.mkdir(parents=True, exist_ok=True)


PATHS = ProjectPaths()


def load_settings() -> dict:
    with (PATHS.config / "study.json").open(encoding="utf-8") as handle:
        return json.load(handle)

