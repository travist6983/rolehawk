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


def _chromium() -> list[Check]:
    """PDF export needs Playwright's headless Chromium; start it once to be sure. Autofill
    opens a visible window, which needs the full browser: a separate install that a
    headless-only setup (`--only-shell`) lacks, so it gets its own check."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    visible = False
    try:
        with sync_playwright() as p:
            visible = Path(p.chromium.executable_path).exists()
            browser = p.chromium.launch(headless=True)
            version = browser.version
            browser.close()
    except PlaywrightError as exc:
        first = str(exc).strip().splitlines()[0][:120]
        fix = browser_hint()
        if sys.platform.startswith("linux") and "Executable doesn't exist" not in first:
            # Installed but won't start: usually system libraries only an admin can add.
            deps = f"sudo {sys.executable} -m playwright install-deps chromium"
            fix += f" (if it still fails: {deps})"
        pdf = Check("chromium", False, f"{first}. Fix: {fix}")
    else:
        pdf = Check("chromium", True, f"Chromium {version} for PDF export")
    if visible:
        autofill = Check("autofill_browser", True, "full Chromium for autofill")
    else:
        detail = f"full Chromium isn't installed, so autofill can't run. Fix: {browser_hint()}"
        autofill = Check("autofill_browser", False, detail)
    return [pdf, autofill]


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

    checks.extend(_chromium())

    if paths.root.exists():
        free_gb = shutil.disk_usage(paths.root).free / 1e9
        checks.append(Check("disk_free", free_gb > 1, f"{free_gb:.1f} GB"))
    return checks


def as_dicts(checks: list[Check]) -> list[dict[str, object]]:
    return [asdict(check) for check in checks]
