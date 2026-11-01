"""Where an installed copy lives. Each release gets its own folder, and a pointer file names
the one the launcher runs:

    ~/.rolehawk/            (%USERPROFILE%\\.rolehawk on Windows; ROLEHAWK_APP_HOME overrides)
      current                 the version to run, e.g. 0.2.0
      versions/0.2.0/         the release ZIP: VERSION, backend/ (+ .venv), frontend/dist, data/
      browsers/               Playwright's Chromium, shared by every version
      downloads/              release ZIPs while updating

An update never overwrites the running version (Windows can't replace files in use); it
installs next to it and moves the pointer. A source checkout has none of this. User data is
elsewhere (~/RoleHawk, see paths.py) and survives reinstalls."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

ENV_APP_HOME = "ROLEHAWK_APP_HOME"
ENV_BROWSERS = "PLAYWRIGHT_BROWSERS_PATH"
VERSION_PATTERN = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")


RELEASE_MARKER = ".release-sha256"


def parse_version(text: str) -> tuple[int, int, int]:
    """Release versions are plain X.Y.Z (they become folder names)."""
    if not VERSION_PATTERN.match(text):
        raise ValueError(f"not a release version: {text!r}")
    major, minor, patch = (int(part) for part in text.split("."))
    return major, minor, patch


@dataclass(frozen=True)
class InstallLayout:
    home: Path

    @classmethod
    def default(cls) -> InstallLayout:
        override = os.environ.get(ENV_APP_HOME)
        return cls(Path(override).expanduser() if override else Path.home() / ".rolehawk")

    @property
    def versions(self) -> Path:
        return self.home / "versions"

    @property
    def browsers(self) -> Path:
        return self.home / "browsers"

    @property
    def downloads(self) -> Path:
        return self.home / "downloads"

    @property
    def current_file(self) -> Path:
        return self.home / "current"

    def current_version(self) -> str | None:
        try:
            text = self.current_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        return text if VERSION_PATTERN.match(text) else None

    def set_current(self, version: str) -> None:
        """Atomic, and without a trailing newline (cmd.exe's `set /p` reads it as is)."""
        parse_version(version)
        partial = self.current_file.with_name("current.partial")
        partial.write_text(version, encoding="utf-8")
        partial.replace(self.current_file)

    def app_dir(self, version: str) -> Path:
        return self.versions / version

    def executable(self, version: str) -> Path:
        venv = self.app_dir(version) / "backend" / ".venv"
        if os.name == "nt":
            return venv / "Scripts" / "rolehawk.exe"
        return venv / "bin" / "rolehawk"

    def release_marker(self, version: str) -> Path:
        """The release ZIP's SHA-256, written once a version is fully installed. The install
        scripts compare it with the published checksum to skip downloading a release that is
        already installed."""
        return self.app_dir(version) / RELEASE_MARKER


def running_from(module_file: str | None = None) -> tuple[InstallLayout, str] | None:
    """(layout, version) when this code runs from an installed release, else None.

    The package is installed editable from <home>/versions/<version>/backend/src/rolehawk."""
    here = Path(module_file or __file__).resolve()
    # install/layout.py -> rolehawk -> src -> backend -> <version> -> versions -> <home>
    app, versions = here.parents[4], here.parents[5]
    if versions.name != "versions" or not (app / "VERSION").is_file():
        return None
    return InstallLayout(versions.parent), app.name


def configure_browsers() -> None:
    """Point Playwright at the shared browsers folder when running an installed release."""
    found = running_from()
    if found and ENV_BROWSERS not in os.environ:
        os.environ[ENV_BROWSERS] = str(found[0].browsers)


def browser_hint() -> str:
    """The command that installs (or repairs) Chromium, for messages and `doctor`."""
    if running_from():
        return "rolehawk install-browser"
    return "uv run playwright install chromium"
