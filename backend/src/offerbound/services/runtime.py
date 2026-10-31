"""Opens and closes everything a running backend needs. Shared by the API and the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from offerbound.config import Settings, load_settings, write_default_config
from offerbound.db import migrate
from offerbound.db.engine import make_engine, make_session_factory
from offerbound.paths import DataPaths
from offerbound.services.events import EventBus
from offerbound.services.tasks import TaskRunner


@dataclass
class Runtime:
    paths: DataPaths
    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    bus: EventBus
    tasks: TaskRunner
    backup_path: Path | None = None

    async def aclose(self) -> None:
        await self.tasks.shutdown()
        self.engine.dispose()


def prepare_data_folder(paths: DataPaths) -> Settings:
    paths.ensure()
    write_default_config(paths.config_file)
    return load_settings(paths.config_file)


def open_runtime(paths: DataPaths) -> Runtime:
    """Create the data folder, load config, migrate the database, and recover stale tasks.

    Must be called inside a running event loop's thread (the task runner uses asyncio)."""
    settings = prepare_data_folder(paths)
    engine = make_engine(paths.db)
    backup_path = migrate.migrate(paths, engine)
    sessions = make_session_factory(engine)
    bus = EventBus()
    tasks = TaskRunner(sessions, bus)
    tasks.recover_interrupted()
    return Runtime(paths, settings, engine, sessions, bus, tasks, backup_path)
