"""FastAPI application factory. Routes stay thin: validate input, call a service, return.

Run with `offerbound start` (or `uv run poe dev`). For uvicorn directly:
`uvicorn offerbound.api.app:create_app --factory --host 127.0.0.1`.
"""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from offerbound import __version__
from offerbound.api.routes import events, system, tasks
from offerbound.api.security import SecurityPolicy, SessionGuard
from offerbound.logging_setup import configure_logging, register_secret
from offerbound.paths import DataPaths
from offerbound.services.runtime import open_runtime, prepare_data_folder

ENV_TOKEN = "OFFERBOUND_SESSION_TOKEN"  # noqa: S105 - env var name
ENV_DEV_ORIGINS = "OFFERBOUND_DEV_ORIGINS"


def create_app(
    paths: DataPaths | None = None,
    token: str | None = None,
    extra_origins: Iterable[str] | None = None,
) -> FastAPI:
    if not logging.getLogger().handlers:
        configure_logging()
    paths = paths or DataPaths.default()
    settings = prepare_data_folder(paths)
    token = token or os.environ.get(ENV_TOKEN) or secrets.token_urlsafe(32)
    register_secret(token)  # the launch URL carries it; keep it out of access logs
    if extra_origins is None:
        extra_origins = [o for o in os.environ.get(ENV_DEV_ORIGINS, "").split(",") if o]
    policy = SecurityPolicy.local(token, settings.server.port, extra_origins)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = open_runtime(paths)
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.aclose()

    app = FastAPI(title="Offerbound AI", version=__version__, lifespan=lifespan)
    app.state.policy = policy
    app.add_middleware(SessionGuard, policy=policy)
    app.include_router(system.router)
    app.include_router(tasks.router)
    app.include_router(events.router)
    return app
