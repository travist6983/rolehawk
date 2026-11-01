"""FastAPI application factory. Routes stay thin: validate input, call a service, return.

Run with `rolehawk start` (or `uv run poe dev`). For uvicorn directly:
`uvicorn rolehawk.api.app:create_app --factory --host 127.0.0.1`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rolehawk import __version__
from rolehawk.api.routes import (
    applications,
    chat,
    commands,
    documents,
    events,
    followups,
    insights,
    jobs,
    llm,
    memory,
    portals,
    profile,
    setup,
    system,
    tasks,
)
from rolehawk.api.security import SecurityPolicy, SessionGuard
from rolehawk.api.web import find_web_dir, mount_web
from rolehawk.llm import errors as llm_errors
from rolehawk.llm.provider import LLMProvider
from rolehawk.logging_setup import configure_logging, register_secret
from rolehawk.paths import DataPaths
from rolehawk.services.runtime import open_runtime, prepare_data_folder

ENV_TOKEN = "ROLEHAWK_SESSION_TOKEN"  # noqa: S105 - env var name
ENV_DEV_ORIGINS = "ROLEHAWK_DEV_ORIGINS"


def create_app(
    paths: DataPaths | None = None,
    token: str | None = None,
    extra_origins: Iterable[str] | None = None,
    provider: LLMProvider | None = None,
    web_dir: Path | None = None,
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
        runtime = open_runtime(paths, provider=provider)
        app.state.runtime = runtime
        maintenance = asyncio.create_task(runtime.startup_maintenance())
        try:
            yield
        finally:
            maintenance.cancel()
            await runtime.aclose()

    app = FastAPI(title="RoleHawk", version=__version__, lifespan=lifespan)
    app.state.policy = policy
    app.add_middleware(SessionGuard, policy=policy)
    app.add_exception_handler(llm_errors.LLMError, _llm_error_handler)
    for router in (
        system.router,
        tasks.router,
        events.router,
        commands.router,
        llm.router,
        chat.router,
        memory.router,
        profile.router,
        setup.router,
        portals.router,
        jobs.router,
        documents.router,
        applications.router,
        followups.router,
        insights.router,
    ):
        app.include_router(router)
    mount_web(app, web_dir or find_web_dir())
    return app


_LLM_STATUS: list[tuple[type[llm_errors.LLMError], int]] = [
    (llm_errors.LLMAuthError, 400),
    (llm_errors.LLMNotConfiguredError, 409),
    (llm_errors.SpendCapExceededError, 402),
    (llm_errors.LLMBillingError, 402),
    (llm_errors.LLMAccountLimitError, 402),
    (llm_errors.LLMUnavailableError, 503),
    (llm_errors.LLMRefusalError, 422),
]


async def _llm_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    status = next((code for kind, code in _LLM_STATUS if isinstance(exc, kind)), 502)
    message = exc.user_message if isinstance(exc, llm_errors.LLMError) else "AI request failed."
    return JSONResponse({"detail": message, "kind": type(exc).__name__}, status_code=status)
