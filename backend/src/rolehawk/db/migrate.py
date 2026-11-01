"""Schema migrations. The data folder is zipped before any upgrade of an existing database."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from rolehawk.paths import DataPaths
from rolehawk.services import backup

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def needs_upgrade(engine: Engine) -> bool:
    return current_revision(engine) != head_revision()


def upgrade(engine: Engine, revision: str = "head") -> None:
    config = _config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def downgrade(engine: Engine, revision: str) -> None:
    config = _config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, revision)


def revision(engine: Engine, message: str) -> None:
    """Autogenerate a new migration from model changes (developer tool)."""
    config = _config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.revision(config, message=message, autogenerate=True)


def migrate(paths: DataPaths, engine: Engine) -> Path | None:
    """Bring the database to head. Returns the backup path if one was made."""
    if not needs_upgrade(engine):
        return None
    backup_path = None
    if current_revision(engine) is not None:
        backup_path = backup.create_backup(paths, reason="pre-migrate")
    upgrade(engine)
    return backup_path
