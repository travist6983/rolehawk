"""Diagnostics report for `offerbound doctor`. Safe to paste into a GitHub issue: no secrets,
no profile data, only versions, paths, and pass/fail checks."""

from __future__ import annotations

import platform
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass

import keyring
import keyring.errors

from offerbound import __version__
from offerbound.config import load_settings
from offerbound.db import migrate
from offerbound.db.engine import make_engine
from offerbound.paths import DataPaths


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


def run_checks(paths: DataPaths) -> list[Check]:
    checks = [
        Check("offerbound", True, __version__),
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

    if paths.root.exists():
        free_gb = shutil.disk_usage(paths.root).free / 1e9
        checks.append(Check("disk_free", free_gb > 1, f"{free_gb:.1f} GB"))
    return checks


def as_dicts(checks: list[Check]) -> list[dict[str, object]]:
    return [asdict(check) for check in checks]
