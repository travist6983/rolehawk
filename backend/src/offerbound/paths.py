"""Resolve and lay out the user's data folder (docs/SPEC.md "Data model and memory")."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_HOME = "OFFERBOUND_HOME"
FOLDER_NAME = "Offerbound"
DB_FILENAME = "offerbound.db"


def resolve_data_root(
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the data folder: $OFFERBOUND_HOME, else ~/Offerbound (Windows: %USERPROFILE%)."""
    env = os.environ if env is None else env
    override = env.get(ENV_HOME, "").strip()
    if override:
        return Path(override).expanduser()
    platform = sys.platform if platform is None else platform
    if platform == "win32" and env.get("USERPROFILE"):
        return Path(env["USERPROFILE"]) / FOLDER_NAME
    return (home if home is not None else Path.home()) / FOLDER_NAME


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @classmethod
    def default(cls) -> DataPaths:
        return cls(resolve_data_root())

    @property
    def db(self) -> Path:
        return self.root / DB_FILENAME

    @property
    def config_file(self) -> Path:
        return self.root / "config.toml"

    @property
    def memory(self) -> Path:
        return self.root / "memory"

    @property
    def sessions(self) -> Path:
        return self.memory / "sessions"

    @property
    def documents(self) -> Path:
        return self.root / "documents"

    @property
    def source_documents(self) -> Path:
        return self.documents / "source"

    @property
    def generated_documents(self) -> Path:
        return self.documents / "generated"

    @property
    def agent_runs(self) -> Path:
        return self.documents / "agent-runs"

    @property
    def templates(self) -> Path:
        return self.root / "templates"

    @property
    def portals(self) -> Path:
        return self.root / "portals"

    @property
    def recipes(self) -> Path:
        return self.portals / "recipes"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    def directories(self) -> list[Path]:
        return [
            self.root,
            self.memory,
            self.sessions,
            self.source_documents,
            self.generated_documents,
            self.agent_runs,
            self.templates,
            self.recipes,
            self.reports,
            self.backups,
        ]

    def ensure(self) -> None:
        """Create the folder layout. Idempotent; never touches existing files."""
        for directory in self.directories():
            directory.mkdir(parents=True, exist_ok=True)
