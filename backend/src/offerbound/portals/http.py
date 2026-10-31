"""A polite HTTP client for job sources: per-host pacing, bounded concurrency, retries with
exponential backoff that honor Retry-After, and an identifying User-Agent."""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx2

from offerbound import __version__

log = logging.getLogger(__name__)

USER_AGENT = f"Offerbound/{__version__} (local job search assistant)"
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _retry_after(response: httpx2.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        parsed = email.utils.parsedate_to_datetime(value)
        return max((parsed - datetime.now(UTC)).total_seconds(), 0.0) if parsed else None


class HostPacer:
    """Keeps at least `min_interval_s` between request starts to one host."""

    def __init__(self, min_interval_s: float, concurrency: int) -> None:
        self.min_interval_s = min_interval_s
        self._lock = asyncio.Lock()
        self._next = 0.0
        self._slots = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> None:
        await self._slots.acquire()
        async with self._lock:
            wait = self._next - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._next = max(time.monotonic(), self._next) + self.min_interval_s

    async def __aexit__(self, *_exc: object) -> None:
        self._slots.release()


class PoliteClient:
    def __init__(
        self,
        client: httpx2.AsyncClient | None = None,
        *,
        retries: int = 3,
        backoff_s: float = 1.0,
        max_backoff_s: float = 30.0,
        timeout_s: float = 20.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        pace_scale: float = 1.0,
    ) -> None:
        self._client = client or httpx2.AsyncClient(
            timeout=timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self._owns_client = client is None
        self._pacers: dict[str, HostPacer] = {}
        self.retries = retries
        self.backoff_s = backoff_s
        self.max_backoff_s = max_backoff_s
        self._sleep = sleep
        self._pace_scale = pace_scale  # 0 in tests; recorded responses need no pacing
        self.requests = 0

    def pace(self, host: str, min_interval_s: float, concurrency: int = 4) -> None:
        self._pacers[host] = HostPacer(min_interval_s * self._pace_scale, concurrency)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx2.Response:
        host = httpx2.URL(url).host
        pacer = self._pacers.get(host)
        if pacer is None:
            pacer = self._pacers[host] = HostPacer(0.25 * self._pace_scale, 4)
        for attempt in range(1, self.retries + 2):
            hint: float | None = None
            status: int | None = None
            async with pacer:
                self.requests += 1
                try:
                    response = await self._client.get(url, params=params, headers=headers)
                except httpx2.TransportError as exc:  # connect errors, timeouts
                    error = type(exc).__name__
                else:
                    if response.status_code < 400:
                        return response
                    status = response.status_code
                    error = f"HTTP {status}"
                    if status not in RETRY_STATUSES:
                        raise HttpError(error, status)
                    hint = _retry_after(response)
            if attempt > self.retries:
                raise HttpError(f"{error} after {attempt} attempts", status)
            delay = min(self.backoff_s * 2 ** (attempt - 1), self.max_backoff_s)
            if hint is not None:
                delay = min(max(delay, hint), self.max_backoff_s)
            delay += random.uniform(0, delay / 4)  # noqa: S311 - jitter, not crypto
            log.info("retrying %s in %.1fs (%s)", url, delay, error)
            await self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    async def json(self, url: str, **kwargs: Any) -> Any:
        response = await self.get(url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise HttpError(f"{url} did not return JSON") from exc

    async def text(self, url: str, **kwargs: Any) -> str:
        return (await self.get(url, **kwargs)).text
