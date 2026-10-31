from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from offerbound.api.app import create_app
from offerbound.db import migrate
from offerbound.db.engine import make_engine, make_session_factory
from offerbound.llm.fake import FakeProvider
from offerbound.llm.types import LLMRequest
from offerbound.paths import DataPaths
from offerbound.services.runtime import Runtime, open_runtime

TEST_TOKEN = "test-session-token"  # noqa: S105
BASE_URL = "http://127.0.0.1:8765"


class MemoryKeyring(KeyringBackend):
    """In-process keyring so tests never touch the real OS keychain (and CI needs none)."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]  # keyring's __init__ is untyped
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError(username)
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[MemoryKeyring]:
    import os

    for name in list(os.environ):
        if name.startswith("OFFERBOUND_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("OFFERBOUND_HOME", str(tmp_path / "Offerbound"))
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    data = DataPaths(tmp_path / "Offerbound")
    data.ensure()
    return data


@pytest.fixture
def engine(paths: DataPaths) -> Iterator[Engine]:
    eng = make_engine(paths.db)
    migrate.upgrade(eng)
    yield eng
    eng.dispose()  # release file handles so Windows can delete tmp_path


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return make_session_factory(engine)


@pytest.fixture
def fake() -> FakeProvider:
    """Scripted Claude. Fact extraction and summaries return nothing unless a test queues
    structured replies."""
    from offerbound.memory.extraction import ExtractedProposals
    from offerbound.memory.sessions import SessionSummary

    def default(_request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        if schema is ExtractedProposals:
            return ExtractedProposals(proposals=[])
        if schema is SessionSummary:
            return SessionSummary(bullets=["Talked about the job search."], open_threads=[])
        raise AssertionError(f"no default structured reply for {schema}")

    return FakeProvider(structured_handler=default)


@pytest.fixture
def client(paths: DataPaths, fake: FakeProvider) -> Iterator[TestClient]:
    app = create_app(paths=paths, token=TEST_TOKEN, extra_origins=(), provider=fake)
    with TestClient(app, base_url=BASE_URL, headers={"X-Offerbound-Token": TEST_TOKEN}) as c:
        yield c


@pytest.fixture
def anon_client(paths: DataPaths, fake: FakeProvider) -> Iterator[TestClient]:
    app = create_app(paths=paths, token=TEST_TOKEN, extra_origins=(), provider=fake)
    with TestClient(app, base_url=BASE_URL) as c:
        yield c


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def runtime(paths: DataPaths, fake: FakeProvider) -> AsyncIterator[Runtime]:
    rt = open_runtime(paths, provider=fake)
    yield rt
    await rt.aclose()
