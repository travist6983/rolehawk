import sqlite3
import zipfile
from pathlib import Path

from sqlalchemy import Engine

from rolehawk.paths import DataPaths
from rolehawk.services import backup


def test_backup_contains_consistent_db_and_files(paths: DataPaths, engine: Engine) -> None:
    (paths.memory / "profile.md").write_text("# Ada", encoding="utf-8")
    dest = backup.create_backup(paths, reason="test")

    assert dest.parent == paths.backups
    with zipfile.ZipFile(dest) as archive:
        names = set(archive.namelist())
        assert "rolehawk.db" in names
        assert "memory/profile.md" in names
        assert not any(name.startswith("backups/") for name in names)
        assert not any(name.endswith(("-wal", "-shm")) for name in names)
        db_bytes = archive.read("rolehawk.db")

    restored = paths.root.parent / "restored.db"
    restored.write_bytes(db_bytes)
    connection = sqlite3.connect(restored)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    finally:
        connection.close()
    assert "jobs" in tables


def test_backup_without_database(paths: DataPaths) -> None:
    with zipfile.ZipFile(backup.create_backup(paths, reason="empty")) as archive:
        assert "rolehawk.db" not in archive.namelist()


def test_unique_names_and_pruning(paths: DataPaths) -> None:
    created = [backup.create_backup(paths, reason="n") for _ in range(backup.KEEP + 3)]
    assert len(set(created)) == len(created)
    remaining = backup.list_backups(paths)
    assert len(remaining) == backup.KEEP
    assert not list(Path(paths.backups).glob("*.partial"))
