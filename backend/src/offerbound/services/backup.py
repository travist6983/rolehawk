"""Zipped backups of the data folder, taken before migrations and /reset."""

from __future__ import annotations

import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from offerbound.paths import DataPaths

KEEP = 10
_SKIP_SUFFIXES = ("-wal", "-shm", "-journal")


def _snapshot_db(db_path: Path, dest: Path) -> None:
    """Consistent copy of a live WAL database via SQLite's online backup API."""
    source = sqlite3.connect(db_path)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _unique_path(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.zip"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}.zip"
        counter += 1
    return candidate


def create_backup(paths: DataPaths, reason: str) -> Path:
    paths.backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%fZ")  # sortable, unique
    dest = _unique_path(paths.backups, f"offerbound-{stamp}-{reason}")
    partial = dest.with_suffix(".zip.partial")

    with (
        tempfile.TemporaryDirectory() as tmp,
        zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive,
    ):
        if paths.db.exists():
            snapshot = Path(tmp) / paths.db.name
            _snapshot_db(paths.db, snapshot)
            archive.write(snapshot, paths.db.name)
        for file in sorted(paths.root.rglob("*")):
            if not file.is_file() or file.is_relative_to(paths.backups):
                continue
            if file == paths.db or file.name.endswith(_SKIP_SUFFIXES):
                continue
            if file.name.startswith(paths.db.name):
                continue
            archive.write(file, file.relative_to(paths.root).as_posix())
    partial.replace(dest)
    prune(paths)
    return dest


def list_backups(paths: DataPaths) -> list[Path]:
    if not paths.backups.exists():
        return []
    """Oldest first. Names start with a UTC timestamp, so name order is creation order."""
    return sorted(paths.backups.glob("offerbound-*.zip"), key=lambda p: p.name)


def prune(paths: DataPaths, keep: int = KEEP) -> None:
    backups = list_backups(paths)
    for old in backups[: max(len(backups) - keep, 0)]:
        old.unlink()
