"""`rolehawk update`: install the newest release next to the running one, then switch.

Order matters. The pointer moves only after the new version is fully set up and the
database is migrated, so a failure at any step leaves the old version working (and a
backup of the data folder from before anything changed)."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx2

from rolehawk.install.layout import InstallLayout, parse_version
from rolehawk.install.release import ReleaseInfo, download, extract, fetch_info

Runner = Callable[[Sequence[str], Path], None]


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateCheck:
    current: str | None
    latest: str
    available: bool


def say(message: str) -> None:
    print(message, flush=True)  # before the subprocess output that follows it


def run_checked(command: Sequence[str], cwd: Path) -> None:
    subprocess.run(list(command), cwd=cwd, check=True)  # noqa: S603 - fixed argv, no shell


def find_uv() -> str | None:
    """uv on PATH, or where its installer puts it (the PATH change may not be live yet)."""
    if found := shutil.which("uv"):
        return found
    name = "uv.exe" if os.name == "nt" else "uv"
    folders = [os.environ.get("XDG_BIN_HOME"), Path.home() / ".local" / "bin"]
    for folder in folders:
        if folder and (Path(folder) / name).is_file():
            return str(Path(folder) / name)
    return None


class Updater:
    def __init__(
        self,
        layout: InstallLayout,
        client: httpx2.Client,
        base_url: str,
        *,
        uv: str | None,
        backup: Callable[[], Path],
        app_running: Callable[[], bool],
        running_version: str | None = None,
        run: Runner = run_checked,
        say: Callable[[str], None] = say,
    ) -> None:
        self.layout = layout
        self.client = client
        self.base_url = base_url
        self.uv = uv
        self.backup = backup
        self.app_running = app_running
        self.running_version = running_version
        self.run = run
        self.say = say

    def check(self) -> tuple[UpdateCheck, ReleaseInfo]:
        info = fetch_info(self.client, self.base_url)
        current = self.layout.current_version()
        newer = current is None or parse_version(info.version) > parse_version(current)
        return UpdateCheck(current=current, latest=info.version, available=newer), info

    def update(self) -> str | None:
        """The version installed, or None when already up to date."""
        status, info = self.check()
        if not status.available:
            return None
        if self.uv is None:
            raise UpdateError("uv isn't installed. Run the install line from the README again.")
        if self.app_running():
            raise UpdateError(
                "RoleHawk is running. Close it (Ctrl+C in its window), then update again."
            )
        version = info.version
        app = self.layout.app_dir(version)
        if version == self.running_version:  # pointer edited by hand; never touch running files
            raise UpdateError(f"Version {version} is the one running; nothing to replace.")

        self.say(f"Downloading RoleHawk {version}...")
        zip_path = download(self.client, self.base_url, info, self.layout.downloads)
        staging = self.layout.versions / f".{version}.partial"
        shutil.rmtree(staging, ignore_errors=True)
        extract(zip_path, staging, version)
        if app.exists():  # a failed earlier attempt
            shutil.rmtree(app)
        staging.rename(app)

        self.say("Installing dependencies (Python 3.12 and packages)...")
        backend = app / "backend"
        self.run([self.uv, "sync", "--quiet", "--frozen", "--no-dev", "--python", "3.12"], backend)
        exe = str(self.layout.executable(version))
        self.say("Checking the browser used for PDFs and autofill...")
        self.run([exe, "install-browser"], backend)

        saved = self.backup()
        self.say(f"Backed up your data to {saved}")
        self.say("Updating the database...")
        self.run([exe, "db", "upgrade"], backend)

        previous = self.layout.current_version()
        self.layout.set_current(version)
        self._prune(keep={version, previous, self.running_version})
        zip_path.unlink(missing_ok=True)
        return version

    def _prune(self, keep: set[str | None]) -> None:
        """Remove older versions (Windows may still hold a file open; that's fine)."""
        for folder in self.layout.versions.iterdir():
            if folder.is_dir() and folder.name not in keep:
                shutil.rmtree(folder, ignore_errors=True)
