"""Diagnostics report for `rolehawk doctor`. Safe to paste into a GitHub issue: no secrets,
no profile data, only versions, paths, and pass/fail checks."""

from __future__ import annotations

import platform
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import keyring
import keyring.errors

from rolehawk import __version__
from rolehawk.config import load_settings
from rolehawk.db import migrate
from rolehawk.db.engine import make_engine
from rolehawk.install.layout import browser_hint, running_from
from rolehawk.paths import DataPaths


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _fts5_available() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()
    return True


def _chromium() -> Check:
    """PDF export needs Playwright's Chromium; start it once to be sure."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            version = browser.version
            browser.close()
            visible = Path(p.chromium.executable_path).exists()
    except PlaywrightError as exc:
        first = str(exc).strip().splitlines()[0][:120]
        fix = browser_hint()
        if sys.platform.startswith("linux") and "Executable doesn't exist" not in first:
            # Installed but won't start: usually system libraries only an admin can add.
            deps = f"sudo {sys.executable} -m playwright install-deps chromium"
            fix += f" (if it still fails: {deps})"
        return Check("chromium", False, f"{first}. Fix: {fix}")
    if not visible:
        return Check(
            "chromium",
            True,
            f"Chromium {version} for PDF export; autofill needs the full browser: {browser_hint()}",
        )
    return Check("chromium", True, f"Chromium {version} (PDF export and autofill)")


def run_checks(paths: DataPaths) -> list[Check]:
    installed = running_from()
    checks = [
        Check("rolehawk", True, __version__),
        Check(
            "install",
            True,
            f"release {installed[1]} in {installed[0].home}" if installed else "source checkout",
        ),
        Check("python", sys.version_info[:2] == (3, 12), platform.python_version()),
        Check("platform", True, f"{platform.system()} {platform.release()} {platform.machine()}"),
        Check("sqlite", True, sqlite3.sqlite_version),
        Check("sqlite_fts5", _fts5_available(), "FTS5 extension"),
        Check("data_folder", paths.root.is_dir(), str(paths.root)),
    ]
    try:
        load_settings(paths.config_file)
        checks.append(Check("config", True, str(paths.config_file)))
    except Exception as exc:
        checks.append(Check("config", False, f"{type(exc).__name__}: {exc}"))

    if paths.db.exists():
        engine = make_engine(paths.db)
        try:
            current, head = migrate.current_revision(engine), migrate.head_revision()
            checks.append(Check("database", current == head, f"revision {current} (head {head})"))
        finally:
            engine.dispose()
    else:
        checks.append(Check("database", True, "not created yet (created on first start)"))

    try:
        backend = keyring.get_keyring()
        usable = backend.priority > 0  # the fail/null backends have priority 0 or below
        checks.append(Check("keychain", usable, type(backend).__name__))
    except keyring.errors.KeyringError as exc:
        checks.append(Check("keychain", False, str(exc)))

    checks.append(_chromium())

    if paths.root.exists():
        free_gb = shutil.disk_usage(paths.root).free / 1e9
        checks.append(Check("disk_free", free_gb > 1, f"{free_gb:.1f} GB"))
    return checks


def as_dicts(checks: list[Check]) -> list[dict[str, object]]:
    return [asdict(check) for check in checks]
