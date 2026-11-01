"""`rolehawk install-skills`: copy the shipped Claude Code skills into the user's personal
skills folder (~/.claude/skills, or $CLAUDE_CONFIG_DIR/skills), so Claude Code users get
/setup, /rank, /apply and the rest in their own session. Each skill is a SKILL.md that calls
`rolehawk run ... --json`; nothing executable is copied."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

RELEASED = ("v1.0",)  # skills for later releases stay out until their commands ship
_HEADING = re.compile(r"^# /[\w-]+ \((v\d+\.\d+)\)", re.MULTILINE)
_NAME = re.compile(r"^name: (rolehawk-[a-z0-9-]+)$", re.MULTILINE)


def bundled_skills_dir() -> Path:
    """skills/ next to backend/, in a release and in a source checkout alike."""
    # install/skills.py -> rolehawk -> src -> backend -> app root
    return Path(__file__).resolve().parents[4] / "skills"


def claude_skills_dir() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "skills"


def released_skills(source: Path) -> list[tuple[str, Path]]:
    """(skill name, SKILL.md) for each skill whose command has shipped."""
    found = []
    for path in sorted(source.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        heading, name = _HEADING.search(text), _NAME.search(text)
        if heading and name and heading.group(1) in RELEASED:
            found.append((name.group(1), path))
    return found


def install_skills(source: Path, dest: Path) -> list[Path]:
    """Copy (or refresh) each released skill to dest/<name>/SKILL.md. Leaves other skills alone."""
    installed = []
    for name, path in released_skills(source):
        folder = dest / name
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, folder / "SKILL.md")
        installed.append(folder)
    return installed
