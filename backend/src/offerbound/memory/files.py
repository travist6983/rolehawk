from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

from offerbound.paths import DataPaths


class MemoryTarget(StrEnum):
    PROFILE = "profile"
    PREFERENCES = "preferences"
    FACTS = "facts"


TEMPLATES: dict[MemoryTarget, str] = {
    MemoryTarget.PROFILE: """\
# Profile

<!-- Your canonical candidate profile. Generated CVs and cover letters may only use facts
written here. Edit freely; Offerbound changes this file only when you accept a proposal. -->

## Summary

## Experience

## Education

## Skills

## Projects

## Certifications

## Achievements
""",
    MemoryTarget.PREFERENCES: """\
# Preferences

## Target titles

## Locations

## Remote

## Salary floor

## Work authorization

## Deal-breakers
""",
    MemoryTarget.FACTS: """\
# Facts

<!-- Durable facts learned in chat, added when you accept them. -->
""",
}


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class MemoryFiles:
    def __init__(self, paths: DataPaths) -> None:
        self._paths = paths

    def path(self, target: MemoryTarget) -> Path:
        return self._paths.memory / f"{target.value}.md"

    def ensure_defaults(self) -> None:
        for target, template in TEMPLATES.items():
            if not self.path(target).exists():
                atomic_write(self.path(target), template)

    def read(self, target: MemoryTarget) -> str:
        path = self.path(target)
        return path.read_text(encoding="utf-8") if path.exists() else TEMPLATES[target]

    def write(self, target: MemoryTarget, text: str) -> None:
        """Only for accepted proposals and the user's own edits."""
        atomic_write(self.path(target), text if text.endswith("\n") else text + "\n")

    # --- session summaries -----------------------------------------------------------

    def session_path(self, day: date) -> Path:
        return self._paths.sessions / f"{day.isoformat()}.md"

    def append_session_summary(self, day: date, heading: str, body: str) -> Path:
        path = self.session_path(day)
        existing = path.read_text(encoding="utf-8") if path.exists() else f"# {day.isoformat()}\n"
        atomic_write(path, f"{existing.rstrip()}\n\n## {heading}\n\n{body.strip()}\n")
        return path

    def latest_session_summary(self) -> str | None:
        files = sorted(self._paths.sessions.glob("????-??-??.md"))
        return files[-1].read_text(encoding="utf-8") if files else None
