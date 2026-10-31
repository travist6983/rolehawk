"""A fake internet for job source tests: routes requests to recorded responses in
tests/fixtures/portals/ and keeps a log of what was asked for. Unrouted URLs return 404."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2

from offerbound.portals.http import PoliteClient

FIXTURES = Path(__file__).parent / "fixtures" / "portals"

Handler = Callable[[httpx2.Request], httpx2.Response]


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> Any:
    return json.loads(fixture_text(name))


async def no_sleep(_seconds: float) -> None:
    return None


class FakeWeb:
    def __init__(self) -> None:
        self.routes: dict[str, Handler] = {}
        self.requests: list[httpx2.Request] = []

    def route(self, host_and_path: str, handler: Handler) -> None:
        self.routes[host_and_path] = handler

    def json(self, host_and_path: str, body: Any, status: int = 200) -> None:
        self.route(host_and_path, lambda _r: httpx2.Response(status, json=body))

    def fixture(self, host_and_path: str, name: str) -> None:
        if name.endswith(".json"):
            self.json(host_and_path, fixture_json(name))
        else:
            text = fixture_text(name)
            self.route(host_and_path, lambda _r: httpx2.Response(200, text=text))

    def status(self, host_and_path: str, status: int) -> None:
        self.route(host_and_path, lambda _r: httpx2.Response(status))

    def standard(self) -> FakeWeb:
        """Every built-in source answering with its recorded fixture."""
        self.fixture("boards-api.greenhouse.io/v1/boards/airbnb/jobs", "greenhouse_airbnb.json")
        self.fixture("api.lever.co/v0/postings/palantir", "lever_palantir.json")
        self.fixture("api.ashbyhq.com/posting-api/job-board/ramp", "ashby_ramp.json")
        self.fixture(
            "apply.workable.com/api/v1/widget/accounts/workmotion", "workable_workmotion.json"
        )
        self.fixture("remoteok.com/api", "remoteok.json")
        self.fixture("weworkremotely.com/remote-jobs.rss", "weworkremotely.rss")
        for page in (1, 2):
            self.fixture(f"api.adzuna.com/v1/api/jobs/us/search/{page}", "adzuna_us.json")
        self.fixture("data.usajobs.gov/api/search", "usajobs.json")
        return self

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        handler = self.routes.get(f"{request.url.host}{request.url.path}")
        return handler(request) if handler else httpx2.Response(404)

    def hits(self, host_and_path: str) -> list[httpx2.Request]:
        return [r for r in self.requests if f"{r.url.host}{r.url.path}" == host_and_path]

    def client(self, **kwargs: Any) -> PoliteClient:
        transport = httpx2.MockTransport(self.handle)
        kwargs.setdefault("sleep", no_sleep)
        kwargs.setdefault("pace_scale", 0.0)
        return PoliteClient(httpx2.AsyncClient(transport=transport), **kwargs)
