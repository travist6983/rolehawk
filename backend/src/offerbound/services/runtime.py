"""Opens and closes everything a running backend needs. Shared by the API and the CLI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from offerbound.apply.autofill import Autofiller
from offerbound.apply.service import ApplyService
from offerbound.commands.apply import register_apply
from offerbound.commands.builtin import register_builtin
from offerbound.commands.documents import register_documents
from offerbound.commands.insights import register_insights
from offerbound.commands.rank import register_rank
from offerbound.commands.registry import CommandRegistry
from offerbound.commands.scrape import register_scrape
from offerbound.commands.setup import register_setup
from offerbound.config import Settings, load_settings, write_default_config
from offerbound.db import migrate
from offerbound.db.engine import make_engine, make_session_factory
from offerbound.fit.ranker import Ranker
from offerbound.insights.board import BoardService
from offerbound.insights.service import ReportService
from offerbound.insights.stats import InsightsService
from offerbound.jobs.store import JobStore
from offerbound.llm.errors import LLMError
from offerbound.llm.holder import ProviderHolder
from offerbound.llm.meter import SpendMeter
from offerbound.llm.provider import LLMProvider
from offerbound.llm.service import LLMService
from offerbound.memory.files import MemoryFiles
from offerbound.memory.proposals import MemoryService
from offerbound.memory.sessions import SessionMaintenance
from offerbound.paths import DataPaths
from offerbound.portals.scrape import Scraper
from offerbound.portals.state import PortalStore
from offerbound.profile.service import ProfileService
from offerbound.profile.setup import SetupService
from offerbound.rendering.service import DocumentService
from offerbound.services.app_state import AppStateStore
from offerbound.services.events import EventBus
from offerbound.services.reset import ResetService
from offerbound.services.tasks import TaskRunner

if TYPE_CHECKING:
    from offerbound.chat.service import ChatService

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    paths: DataPaths
    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    bus: EventBus
    tasks: TaskRunner
    providers: ProviderHolder
    llm: LLMService
    memory: MemoryService
    session_maintenance: SessionMaintenance
    commands: CommandRegistry
    state: AppStateStore
    profiles: ProfileService
    setup: SetupService
    portals: PortalStore
    scraper: Scraper
    jobs: JobStore
    ranker: Ranker
    documents: DocumentService
    applications: ApplyService
    autofill: Autofiller
    board: BoardService
    insights: InsightsService
    reports: ReportService
    reset: ResetService
    backup_path: Path | None = None
    _chat: ChatService | None = field(default=None, init=False, repr=False)

    @property
    def chat(self) -> ChatService:
        if self._chat is None:
            from offerbound.chat.service import ChatService

            self._chat = ChatService(self)
        return self._chat

    def reload_settings(self) -> Settings:
        self.settings = load_settings(self.paths.config_file)
        return self.settings

    async def startup_maintenance(self) -> None:
        """Purge expired chat and summarize sessions that went quiet. Never raises."""
        try:
            self.session_maintenance.purge(self.settings.chat.retention_days)
            if self.llm.configured:
                await self.session_maintenance.summarize_stale()
        except LLMError as exc:
            log.info("startup maintenance skipped: %s", exc)
        except Exception:
            log.exception("startup maintenance failed")

    async def aclose(self) -> None:
        await self.tasks.shutdown()
        await self.documents.aclose()
        await self.autofill.aclose()
        self.engine.dispose()


def prepare_data_folder(paths: DataPaths) -> Settings:
    paths.ensure()
    write_default_config(paths.config_file)
    MemoryFiles(paths).ensure_defaults()
    return load_settings(paths.config_file)


def open_runtime(paths: DataPaths, provider: LLMProvider | None = None) -> Runtime:
    """Create the data folder, load config, migrate the database, and recover stale tasks.

    `provider` overrides the keychain-backed Anthropic provider (tests, offline dev). Must be
    called from the thread that runs the event loop (the task runner uses asyncio)."""
    settings = prepare_data_folder(paths)
    engine = make_engine(paths.db)
    backup_path = migrate.migrate(paths, engine)
    sessions = make_session_factory(engine)
    bus = EventBus()
    tasks = TaskRunner(sessions, bus)
    tasks.recover_interrupted()

    holder = ProviderHolder(provider)
    files = MemoryFiles(paths)
    commands = CommandRegistry()
    register_builtin(commands)
    register_setup(commands)
    register_scrape(commands)
    register_rank(commands)
    register_documents(commands)
    register_apply(commands)
    register_insights(commands)

    runtime_ref: list[Runtime] = []
    llm = LLMService(holder.get, lambda: runtime_ref[0].settings.llm, SpendMeter(sessions))
    state = AppStateStore(sessions)
    profiles = ProfileService(files, sessions, lambda: runtime_ref[0].settings)
    portals = PortalStore(sessions)
    portals.sync_builtin()
    portals.seed_watchlist()
    memory = MemoryService(files, sessions, on_change=profiles.on_memory_changed)
    jobs = JobStore(sessions)
    ranker = Ranker(sessions, llm, memory, profiles.load_preferences)
    board = BoardService(
        sessions, lambda app_id: paths.generated_documents / str(app_id) / "application.json"
    )
    insights = InsightsService(sessions, lambda: runtime_ref[0].settings.llm.monthly_cap_usd)
    documents = DocumentService(
        paths,
        lambda: runtime_ref[0].settings,
        lambda: runtime_ref[0].reload_settings(),
        profiles.load_profile,
    )
    runtime = Runtime(
        paths=paths,
        settings=settings,
        engine=engine,
        sessions=sessions,
        bus=bus,
        tasks=tasks,
        providers=holder,
        llm=llm,
        memory=memory,
        session_maintenance=SessionMaintenance(llm, files, sessions),
        commands=commands,
        state=state,
        profiles=profiles,
        setup=SetupService(paths, sessions, profiles, state, llm),
        portals=portals,
        scraper=Scraper(sessions, lambda: runtime_ref[0].settings.search.country),
        jobs=jobs,
        ranker=ranker,
        documents=documents,
        applications=ApplyService(
            paths,
            sessions,
            lambda: runtime_ref[0].settings,
            llm,
            memory,
            profiles.load_profile,
            ranker,
            jobs,
            documents,
        ),
        autofill=Autofiller(headless=False),
        board=board,
        insights=insights,
        reports=ReportService(paths, board, insights, lambda: profiles.load_profile().contact.name),
        reset=ResetService(paths, sessions, files, portals),
        backup_path=backup_path,
    )
    runtime_ref.append(runtime)
    return runtime
