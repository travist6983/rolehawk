"""/scrape end to end against recorded responses: matching, dedupe, isolation of failing
sources, skips, status recording, the watchlist store, the API, and the CLI."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import cast

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from offerbound import cli, keychain
from offerbound.db.models import Company, Job, PortalKind, RiskLevel, SearchTarget
from offerbound.db.models import Portal as PortalRow
from offerbound.keychain import SecretName
from offerbound.portals import scrape as scrape_module
from offerbound.portals.base import NormalizedJob, Portal, PortalContext, RawJob
from offerbound.portals.registry import ATS_IDS, BUILTIN
from offerbound.portals.scrape import NoSearchTargetsError, Scraper, ScrapeSummary
from offerbound.portals.state import CompanyIn, PortalStore
from offerbound.services.runtime import Runtime
from tests.conftest import MemoryKeyring
from tests.portal_web import FakeWeb, fixture_json
from tests.test_api_setup import wait_for_task

pytestmark = pytest.mark.anyio

TARGETS = (
    "Data Analyst",
    "Software Engineer",
    "Account Executive",
    "Legal Counsel",
    "Business Partner",
)


def keyword_feeds(web: FakeWeb) -> FakeWeb:
    """Adzuna and USAJOBS only return their fixture for the matching keyword, like the real
    APIs (an unrelated keyword gets no results)."""
    adzuna, usajobs = fixture_json("adzuna_us.json"), fixture_json("usajobs.json")

    def adzuna_handler(request: httpx2.Request) -> httpx2.Response:
        hit = request.url.params["what"] == "Data Analyst"
        return httpx2.Response(200, json=adzuna if hit else {"count": 0, "results": []})

    def usajobs_handler(request: httpx2.Request) -> httpx2.Response:
        hit = request.url.params["Keyword"] == "Data Analyst"
        return httpx2.Response(200, json=usajobs if hit else {"SearchResult": {}})

    web.route("api.adzuna.com/v1/api/jobs/us/search/1", adzuna_handler)
    web.route("data.usajobs.gov/api/search", usajobs_handler)
    return web


def add_targets(sessions: sessionmaker[Session], *titles: str, country: str = "US") -> None:
    with sessions.begin() as session:
        for title in titles:
            session.add(SearchTarget(title=title, country=country))


def watch(store: PortalStore) -> None:
    for ats, slug, name in [
        ("greenhouse", "airbnb", "Airbnb"),
        ("lever", "palantir", "Palantir"),
        ("ashby", "ramp", "Ramp"),
        ("workable", "workmotion", "WorkMotion"),
    ]:
        store.add_companies(ats, [CompanyIn(slug=slug, name=name)])


def connect_feeds(store: PortalStore) -> None:
    store.set_credentials("adzuna", {"app_id": "id-1", "app_key": "key-1"}, {})
    store.set_credentials("usajobs", {"api_key": "usa-key"}, {"email": "me@example.com"})


class Progress:
    def __init__(self) -> None:
        self.events: list[tuple[float | None, str | None]] = []

    async def __call__(self, fraction: float | None, message: str | None) -> None:
        self.events.append((fraction, message))


@pytest.fixture
def store(sessions: sessionmaker[Session]) -> PortalStore:
    portals = PortalStore(sessions)
    portals.sync_builtin()
    return portals


@pytest.fixture
def web() -> FakeWeb:
    return keyword_feeds(FakeWeb().standard())


def make_scraper(
    sessions: sessionmaker[Session], web: FakeWeb, portals: Sequence[Portal] = BUILTIN
) -> Scraper:
    return Scraper(sessions, lambda: "US", web.client, portals)


def by_portal(summary: ScrapeSummary) -> dict[str, scrape_module.PortalRun]:
    return {run.portal_id: run for run in summary.portals}


# --- the scraper --------------------------------------------------------------------------


async def test_scrape_keeps_matching_jobs_and_dedupes_reruns(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    add_targets(sessions, *TARGETS)
    watch(store)
    connect_feeds(store)
    progress = Progress()

    summary = await make_scraper(sessions, web).run(progress)
    runs = by_portal(summary)

    assert {r.status for r in summary.portals} == {"ok"}
    assert {k: (r.matched, r.new) for k, r in runs.items()} == {
        "greenhouse": (1, 1),  # Associate Legal Counsel, Japan
        "lever": (3, 3),  # Administrative Business Partner x3 (different locations)
        "ashby": (1, 1),  # Software Engineer, Frontend
        "workable": (3, 1),  # one shortcode listed in three countries
        "remoteok": (0, 0),
        "weworkremotely": (0, 0),
        "adzuna": (2, 2),
        "usajobs": (1, 1),
    }
    assert runs["workable"].duplicates == 2
    assert runs["greenhouse"].found == 3
    assert summary.new == 9
    assert summary.queries == list(TARGETS)
    assert progress.events[0] == (0.0, "Searching 8 sources")
    assert progress.events[-1][0] == 1.0

    with sessions() as session:
        rows = list(session.scalars(select(Job)))
    assert len(rows) == 9
    adzuna_job = next(j for j in rows if j.title == "Senior Data Analyst")
    assert (adzuna_job.portal_id, adzuna_job.company) == ("adzuna", "Northwind Analytics")
    assert adzuna_job.scraped_at.tzinfo is not None

    again = await make_scraper(sessions, web).run(Progress())
    assert again.new == 0
    assert again.duplicates == summary.new + summary.duplicates
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 9


async def test_same_job_from_two_sources_is_stored_once(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    add_targets(sessions, "Legal Counsel")
    store.add_companies("greenhouse", [CompanyIn(slug="airbnb", name="Airbnb")])
    web.json(
        "remoteok.com/api",
        [
            {"legal": "terms"},
            {"id": 99, "position": "Associate Legal Counsel, Japan", "company": "Airbnb, Inc.",
             "location": "Tokyo, Japan", "url": "https://remoteok.com/remote-jobs/99"},
        ],
    )  # fmt: skip

    summary = await make_scraper(sessions, web).run(Progress(), ["greenhouse", "remoteok"])

    assert summary.new == 1
    assert summary.duplicates == 1
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


async def test_one_failing_source_never_fails_the_run(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    class Boom:
        id = "boom"
        name = "Boom"
        kind = PortalKind.FEED
        countries: tuple[str, ...] = ("*",)
        risk_level = RiskLevel.LOW
        requires: tuple[str, ...] = ()
        default_enabled = True
        host = "boom.test"
        min_interval_s = 0.1
        docs_url = "https://boom.test"

        async def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
            yield RawJob("1", {})
            raise RuntimeError("parser exploded")

        def normalize(self, raw: RawJob) -> NormalizedJob:
            raise KeyError("title")

    with sessions.begin() as session:
        session.add(
            PortalRow(id="boom", name="Boom", kind=PortalKind.FEED, enabled=True,
                      risk_level=RiskLevel.LOW, config={})
        )  # fmt: skip
    add_targets(sessions, "Software Engineer")
    store.add_companies("ashby", [CompanyIn(slug="ramp", name="Ramp")])
    web.status("remoteok.com/api", 503)
    remoteok = next(p for p in BUILTIN if p.id == "remoteok")
    ashby = next(p for p in BUILTIN if p.id == "ashby")

    summary = await make_scraper(sessions, web, [Boom(), remoteok, ashby]).run(Progress())
    runs = by_portal(summary)

    assert runs["ashby"].status == "ok"
    assert runs["ashby"].new == 1
    assert runs["remoteok"].status == "error"
    assert runs["remoteok"].errors == ["HTTP 503 after 4 attempts"]
    assert runs["boom"].status == "error"
    assert runs["boom"].errors == [
        "skipped a malformed job: 'title'",
        "RuntimeError: parser exploded",
    ]
    with sessions() as session:
        rows = {p.id: p for p in session.scalars(select(PortalRow))}
    assert rows["remoteok"].status == "error"
    assert rows["remoteok"].last_error == "HTTP 503 after 4 attempts"
    assert rows["remoteok"].last_run_at is not None
    assert rows["ashby"].status == "ok"
    assert rows["ashby"].last_error is None


async def test_sources_that_cannot_run_are_skipped_with_a_reason(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    add_targets(sessions, "Data Analyst", country="GB")
    store.set_enabled("remoteok", False)

    summary = await make_scraper(sessions, web).run(Progress())
    runs = by_portal(summary)

    assert runs["remoteok"].detail == "off"
    assert runs["usajobs"].detail == "not available in your search country"
    assert runs["adzuna"].detail == "needs an app ID, an app key"
    assert runs["greenhouse"].detail == "needs companies in the watchlist"
    assert runs["weworkremotely"].status == "ok"
    assert {r.status for k, r in runs.items() if k != "weworkremotely"} == {"skipped"}

    # Asking for a source by name runs it even when it's switched off.
    named = await make_scraper(sessions, web).run(Progress(), ["remoteok"])
    assert [(r.portal_id, r.status) for r in named.portals] == [("remoteok", "ok")]


async def test_no_search_targets_is_a_clear_error(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    with pytest.raises(NoSearchTargetsError) as info:
        await make_scraper(sessions, web).run(Progress())
    assert "job titles" in info.value.user_message
    assert web.requests == []


async def test_company_results_and_errors_are_recorded(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    add_targets(sessions, "Legal Counsel")
    store.add_companies(
        "greenhouse", [CompanyIn(slug="airbnb", name="Airbnb"), CompanyIn(slug="gone")]
    )
    summary = await make_scraper(sessions, web).run(Progress(), ["greenhouse"])
    (run,) = summary.portals
    assert run.status == "ok"
    assert run.errors == ["gone: not found on this ATS"]
    companies = {c.slug: c for c in store.companies("greenhouse")}
    assert companies["airbnb"].last_job_count == 3
    assert companies["airbnb"].last_error is None
    assert companies["gone"].last_error == "not found on this ATS"


async def test_caps_and_timeouts_keep_what_was_found(
    sessions: sessionmaker[Session],
    store: PortalStore,
    web: FakeWeb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_targets(sessions, "Business Partner")
    store.add_companies("lever", [CompanyIn(slug="palantir", name="Palantir")])
    monkeypatch.setattr(scrape_module, "MAX_JOBS_PER_PORTAL", 2)
    capped = await make_scraper(sessions, web).run(Progress(), ["lever"])
    assert capped.portals[0].new == 2
    assert capped.portals[0].errors == ["stopped at 2 matching jobs"]

    class Slow:
        id = "weworkremotely"
        name = "Slow"
        kind = PortalKind.FEED
        countries: tuple[str, ...] = ("*",)
        risk_level = RiskLevel.LOW
        requires: tuple[str, ...] = ()
        default_enabled = True
        host = "slow.test"
        min_interval_s = 0.1
        docs_url = "https://slow.test"

        async def search(self, ctx: PortalContext, since: datetime | None) -> AsyncIterator[RawJob]:
            yield RawJob("s1", {})
            await asyncio.sleep(5)
            yield RawJob("s2", {})  # pragma: no cover - timed out first

        def normalize(self, raw: RawJob) -> NormalizedJob:
            return NormalizedJob(
                external_id=raw.external_id, url="https://slow.test/1", company="Slow Co",
                title="Senior Business Partner",
            )  # fmt: skip

    monkeypatch.setattr(scrape_module, "PORTAL_TIMEOUT_S", 0.05)
    slow = await make_scraper(sessions, web, [Slow()]).run(Progress())
    (run,) = slow.portals
    assert run.status == "ok"
    assert run.new == 1
    assert run.errors == ["timed out after 0.05s; kept what was found"]


async def test_check_company_looks_the_board_up(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    scraper = make_scraper(sessions, web)
    found = await scraper.check_company("workable", "workmotion")
    assert (found.ok, found.jobs, found.company) == (True, 3, "WorkMotion")
    greenhouse = await scraper.check_company("greenhouse", "airbnb")
    assert (greenhouse.jobs, greenhouse.company) == (3, "Airbnb")  # from the jobs themselves
    missing = await scraper.check_company("greenhouse", "nope")
    assert (missing.ok, missing.detail) == (False, "No job board with that name on this ATS.")
    with pytest.raises(ValueError, match="not an ATS"):
        await scraper.check_company("remoteok", "x")


# --- the store ----------------------------------------------------------------------------


def test_sync_builtin_is_idempotent_and_keeps_choices(store: PortalStore) -> None:
    store.set_enabled("remoteok", False)
    store.sync_builtin()
    views = {v.id: v for v in store.views()}
    assert list(views) == [p.id for p in BUILTIN]
    assert views["remoteok"].enabled is False
    assert views["greenhouse"].missing == ["companies in the watchlist"]
    assert views["remoteok"].ready is True
    assert views["remoteok"].companies is None


def test_seed_watchlist_loads_starter_lists_once(store: PortalStore) -> None:
    added = store.seed_watchlist()
    assert added > 100
    assert store.seed_watchlist() == 0
    by_ats = {ats: len(store.companies(ats)) for ats in ATS_IDS}
    assert all(count > 0 for count in by_ats.values())
    assert sum(by_ats.values()) == added
    assert all(c.source == "starter" for c in store.companies())
    views = {v.id: v for v in store.views()}
    assert views["greenhouse"].ready is True
    assert views["greenhouse"].companies == by_ats["greenhouse"]


def test_credentials_go_to_the_keychain_not_the_database(
    store: PortalStore, sessions: sessionmaker[Session], isolated_env: MemoryKeyring
) -> None:
    view = store.set_credentials("adzuna", {"app_id": " id-1 ", "app_key": "key-1"}, {})
    assert view.ready is True
    assert view.missing == []
    assert view.secret_fields == ["app_id", "app_key"]
    assert keychain.get_secret(SecretName.ADZUNA_APP_ID) == "id-1"
    assert "key-1" not in view.model_dump_json()
    with sessions() as session:
        row = session.get(PortalRow, "adzuna")
        assert row is not None
        assert row.config == {}

    usajobs = store.set_credentials("usajobs", {"api_key": "k"}, {"email": " me@example.com "})
    assert usajobs.ready is True
    assert usajobs.config == {"email": "me@example.com"}

    with pytest.raises(ValueError, match="unknown fields: token"):
        store.set_credentials("adzuna", {"token": "x"}, {})
    with pytest.raises(ValueError, match="unknown fields: email"):
        store.set_credentials("adzuna", {}, {"email": "x"})

    cleared = store.clear_credentials("adzuna")
    assert cleared.ready is False
    assert keychain.get_secret(SecretName.ADZUNA_APP_KEY) is None
    assert not any(k[1].startswith("adzuna") for k in isolated_env.store)


def test_watchlist_add_remove_and_restore(store: PortalStore) -> None:
    store.seed_watchlist()
    starter = store.companies("greenhouse")[0]
    (user,) = store.add_companies("greenhouse", [CompanyIn(slug="my-co", name="My Co")])
    assert user.source == "user"
    assert user.enabled is True

    # Adding the same slug again (any case) doesn't duplicate.
    (again,) = store.add_companies("greenhouse", [CompanyIn(slug="MY-CO")])
    assert again.id == user.id

    store.remove_company(user.id)
    assert all(c.slug != "my-co" for c in store.companies("greenhouse"))

    # Starter companies are switched off rather than deleted, so seeding won't revive them.
    store.remove_company(starter.id)
    assert store.seed_watchlist() == 0
    removed = next(c for c in store.companies("greenhouse") if c.id == starter.id)
    assert removed.enabled is False

    # Adding it back turns it on again.
    (restored,) = store.add_companies("greenhouse", [CompanyIn(slug=starter.slug)])
    assert restored.id == starter.id
    assert restored.enabled is True

    with pytest.raises(ValueError, match="not an ATS"):
        store.add_companies("remoteok", [CompanyIn(slug="x")])
    with pytest.raises(KeyError):
        store.remove_company(99999)


def test_company_slugs_must_be_plain_board_names() -> None:
    for bad in ["../etc", "a/b", "a b", "-lead", ""]:
        with pytest.raises(ValueError, match="slug"):
            CompanyIn(slug=bad)
    assert CompanyIn(slug="acme.io_2-x").slug == "acme.io_2-x"


# --- API ----------------------------------------------------------------------------------


@pytest.fixture
def api(client: TestClient, web: FakeWeb) -> tuple[TestClient, Runtime]:
    runtime: Runtime = cast(FastAPI, client.app).state.runtime
    runtime.scraper.http_factory = web.client
    return client, runtime


def test_portals_api_lists_toggles_and_stores_keys(api: tuple[TestClient, Runtime]) -> None:
    client, _ = api
    portals = client.get("/api/portals").json()
    assert [p["id"] for p in portals] == [p.id for p in BUILTIN]
    greenhouse = next(p for p in portals if p["id"] == "greenhouse")
    assert greenhouse["ready"] is True
    assert greenhouse["companies"] > 0

    assert client.patch("/api/portals/remoteok", json={"enabled": False}).json()["enabled"] is False
    assert client.patch("/api/portals/nope", json={"enabled": True}).status_code == 404
    assert client.patch("/api/portals/remoteok", json={"enabled": True, "x": 1}).status_code == 422

    stored = client.put(
        "/api/portals/adzuna/credentials",
        json={"secrets": {"app_id": "id-1", "app_key": "secret-key"}},
    )
    assert stored.status_code == 200
    assert stored.json()["ready"] is True
    assert "secret-key" not in client.get("/api/portals").text
    bad = client.put("/api/portals/adzuna/credentials", json={"secrets": {"nope": "x"}})
    assert bad.status_code == 422
    cleared = client.delete("/api/portals/adzuna/credentials").json()
    assert cleared["ready"] is False


def test_companies_api(api: tuple[TestClient, Runtime]) -> None:
    client, _ = api
    check = client.post("/api/companies/check", json={"ats": "ashby", "slug": "ramp"}).json()
    assert check == {"ok": True, "jobs": 3, "company": None, "detail": None}
    missing = client.post("/api/companies/check", json={"ats": "lever", "slug": "nope"}).json()
    assert missing["ok"] is False
    assert (
        client.post("/api/companies/check", json={"ats": "lever", "slug": "../x"}).status_code
        == 422
    )
    assert (
        client.post("/api/companies/check", json={"ats": "adzuna", "slug": "x"}).status_code == 422
    )

    created = client.post(
        "/api/companies", json={"ats": "ashby", "companies": [{"slug": "acme", "name": "Acme"}]}
    )
    assert created.status_code == 201
    (company,) = created.json()
    assert company["source"] == "user"
    assert any(c["slug"] == "acme" for c in client.get("/api/companies?ats=ashby").json())

    off = client.patch(f"/api/companies/{company['id']}", json={"enabled": False}).json()
    assert off["enabled"] is False
    assert client.delete(f"/api/companies/{company['id']}").status_code == 204
    assert client.delete(f"/api/companies/{company['id']}").status_code == 404
    assert client.patch("/api/companies/99999", json={"enabled": True}).status_code == 404
    bad = client.post("/api/companies", json={"ats": "remoteok", "companies": [{"slug": "x"}]})
    assert bad.status_code == 422


def test_scrape_api_runs_in_the_background(api: tuple[TestClient, Runtime]) -> None:
    client, runtime = api
    assert client.get("/api/scrape/last").json() is None
    failed = wait_for_task(client, client.post("/api/scrape").json()["task_id"])
    assert failed["status"] == "failed"
    assert failed["error"] == NoSearchTargetsError.user_message

    add_targets(runtime.sessions, "Software Engineer")
    with runtime.sessions.begin() as session:  # just one company, so the run is small
        for company in session.scalars(select(Company)):
            company.enabled = company.slug == "ramp"
    started = client.post("/api/scrape", json={"portal_ids": ["ashby"]})
    assert started.status_code == 202
    task = wait_for_task(client, started.json()["task_id"])
    assert task["status"] == "succeeded", task
    result = cast(dict[str, object], task["result"])
    assert result["new"] == 1
    last = client.get("/api/scrape/last").json()
    assert last["new"] == 1
    assert [p["portal_id"] for p in last["portals"]] == ["ashby"]
    portal = next(p for p in client.get("/api/portals").json() if p["id"] == "ashby")
    assert portal["status"] == "ok"
    assert portal["jobs_found"] == 1


def test_sources_api_needs_the_session_token(anon_client: TestClient) -> None:
    assert anon_client.get("/api/portals").status_code == 401
    assert anon_client.post("/api/scrape").status_code == 401
    assert (
        anon_client.post("/api/companies/check", json={"ats": "ashby", "slug": "x"}).status_code
        == 401
    )


def test_cli_scrape_explains_missing_targets(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "scrape", "--json"]) == 1
    output = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert output["status"] == "failed"
    assert output["error"] == NoSearchTargetsError.user_message


# --- commands (what skills and chat call) -------------------------------------------------


def test_watchlist_commands(api: tuple[TestClient, Runtime]) -> None:
    client, _ = api
    sources = client.post("/api/commands/sources", json={"params": {}}).json()["result"]
    assert [s["id"] for s in sources["sources"]] == [p.id for p in BUILTIN]
    assert sources["last_search"] is None

    added = client.post(
        "/api/commands/watchlist-add",
        json={"params": {"ats": "workable", "slugs": ["workmotion", "nope", "workmotion"]}},
    ).json()["result"]
    assert [c["name"] for c in added["added"]] == ["WorkMotion"]
    assert added["not_added"] == [
        {"slug": "nope", "detail": "No job board with that name on this ATS."}
    ]
    watchlist = client.post("/api/commands/watchlist", json={"params": {}}).json()["result"]
    assert any(c["slug"] == "workmotion" for c in watchlist)

    bad = client.post(
        "/api/commands/watchlist-add", json={"params": {"ats": "lever", "slugs": ["../x"]}}
    )
    assert bad.status_code == 422


def test_watchlist_add_is_a_write_command(api: tuple[TestClient, Runtime]) -> None:
    _, runtime = api
    assert runtime.commands.get("watchlist-add").read_only is False
    assert runtime.commands.get("sources").read_only is True
    assert runtime.commands.get("scrape").background is True


async def test_jobs_without_a_web_link_are_dropped(
    sessions: sessionmaker[Session], store: PortalStore, web: FakeWeb
) -> None:
    add_targets(sessions, "Data Analyst")
    web.json(
        "remoteok.com/api",
        [
            {"legal": "terms"},
            {"id": 1, "position": "Data Analyst", "company": "A", "url": "javascript:alert(1)"},
            {"id": 2, "position": "Data Analyst", "company": "B", "url": "https://remoteok.com/2"},
        ],
    )
    summary = await make_scraper(sessions, web).run(Progress(), ["remoteok"])
    assert (summary.portals[0].matched, summary.new) == (1, 1)
    with sessions() as session:
        assert list(session.scalars(select(Job.url))) == ["https://remoteok.com/2"]
