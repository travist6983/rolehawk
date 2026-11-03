"""Job sources: each portal's search + normalize against recorded responses, the polite HTTP
client, text helpers, and title matching. No live network calls."""

from __future__ import annotations

import asyncio
import dataclasses
import itertools
import time
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest

from rolehawk.portals.ats import Ashby, Greenhouse, Lever, SmartRecruiters, Workable
from rolehawk.portals.base import (
    CompanyRef,
    NormalizedJob,
    Portal,
    PortalContext,
    PortalError,
    SearchQuery,
)
from rolehawk.portals.feeds import Adzuna, RemoteOK, USAJobs, WeWorkRemotely
from rolehawk.portals.http import USER_AGENT, HostPacer, HttpError, PoliteClient
from rolehawk.portals.matching import job_matches, title_matches, tokens
from rolehawk.portals.registry import ATS_IDS, BUILTIN, get_portal
from rolehawk.portals.text import (
    fix_mojibake,
    html_to_text,
    job_hash,
    looks_remote,
    parse_datetime,
    salary_range,
)
from tests.portal_web import FakeWeb

pytestmark = pytest.mark.anyio

QUERIES = (SearchQuery(title="Data Analyst", country="US"),)


async def collect(
    portal: Portal, web: FakeWeb, **changes: Any
) -> tuple[list[NormalizedJob], PortalContext]:
    http = web.client()
    ctx = dataclasses.replace(PortalContext(http=http, queries=QUERIES), **changes)
    try:
        jobs = [portal.normalize(raw) async for raw in portal.search(ctx, None)]
    finally:
        await http.aclose()
    return jobs, ctx


# --- registry -----------------------------------------------------------------------------


def test_registry_has_unique_ids_and_ats_need_watchlist() -> None:
    ids = [p.id for p in BUILTIN]
    assert len(ids) == len(set(ids))
    assert {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"} == ATS_IDS
    assert get_portal("remoteok").name == "Remote OK"
    with pytest.raises(KeyError):
        get_portal("nope")
    for portal in BUILTIN:
        assert portal.docs_url.startswith("https://")
        assert portal.min_interval_s > 0


# --- ATS portals --------------------------------------------------------------------------


async def test_greenhouse_normalizes_recorded_board() -> None:
    web = FakeWeb().standard()
    jobs, _ = await collect(Greenhouse(), web, companies=[CompanyRef("airbnb", "Airbnb")])
    assert [j.external_id for j in jobs] == ["8306554", "7789554", "8231416"]
    first = jobs[0]
    assert first.title == "AirCover Specialist, Claims Experience"
    assert first.company == "Airbnb"
    assert first.location == "Canada"
    assert first.url.startswith("https://")
    assert first.posted_at is not None
    assert first.posted_at.tzinfo is not None
    assert "<" not in first.description
    assert len(first.description) > 100
    assert web.requests[0].url.params["content"] == "true"


async def test_lever_normalizes_and_falls_back_to_eu_host() -> None:
    web = FakeWeb()
    web.fixture("api.eu.lever.co/v0/postings/palantir", "lever_palantir.json")
    jobs, _ = await collect(Lever(), web, companies=[CompanyRef("palantir", "Palantir")])
    assert len(jobs) == 3
    assert [r.url.host for r in web.requests] == ["api.lever.co", "api.eu.lever.co"]
    job = jobs[1]
    assert job.title == "Administrative Business Partner - ShipOS"
    assert job.company == "Palantir"
    assert job.location == "Washington, D.C."
    assert job.url.startswith("https://jobs.lever.co/")
    assert job.description
    assert "<" not in job.description


async def test_ashby_keeps_compensation_and_hybrid_is_not_remote() -> None:
    web = FakeWeb().standard()
    jobs, _ = await collect(Ashby(), web, companies=[CompanyRef("ramp", "Ramp")])
    by_title = {j.title: j for j in jobs}
    frontend = by_title["Software Engineer, Frontend"]
    assert frontend.salary_text == "$143.2K - $284K"
    assert frontend.location == "New York, NY (HQ)"
    assert frontend.remote is None  # hybrid
    assert "Security Engineer, Cloud" in by_title  # leading space stripped
    assert web.requests[0].url.params["includeCompensation"] == "true"


async def test_ashby_skips_unlisted_and_uses_job_url_without_id() -> None:
    web = FakeWeb()
    web.json(
        "api.ashbyhq.com/posting-api/job-board/acme",
        {
            "jobs": [
                {"title": "Hidden", "jobUrl": "https://jobs.ashbyhq.com/acme/1", "isListed": False},
                {"title": "Data Analyst", "jobUrl": "https://jobs.ashbyhq.com/acme/2",
                 "workplaceType": "Remote", "location": "Anywhere"},
            ]
        },
    )  # fmt: skip
    jobs, _ = await collect(Ashby(), web, companies=[CompanyRef("acme", "Acme")])
    assert [(j.external_id, j.remote) for j in jobs] == [("https://jobs.ashbyhq.com/acme/2", True)]


async def test_workable_uses_account_name_and_telecommuting() -> None:
    web = FakeWeb().standard()
    jobs, _ = await collect(Workable(), web, companies=[CompanyRef("workmotion", "workmotion")])
    assert len(jobs) == 3
    assert {j.company for j in jobs} == {"WorkMotion"}
    assert all(j.remote is True for j in jobs)
    assert jobs[0].location
    assert jobs[0].location.endswith("Spain")


async def test_ats_company_failures_are_reported_not_fatal() -> None:
    web = FakeWeb().standard()
    web.json("boards-api.greenhouse.io/v1/boards/broken/jobs", {"jobs": [{"title": "no id"}]})
    web.status("boards-api.greenhouse.io/v1/boards/down/jobs", 403)
    errors: dict[str, str] = {}
    counts: dict[str, int] = {}
    jobs, _ = await collect(
        Greenhouse(),
        web,
        companies=[
            CompanyRef("airbnb", "Airbnb"),
            CompanyRef("gone", "Gone"),
            CompanyRef("broken", "Broken"),
            CompanyRef("down", "Down"),
        ],
        report_company_error=lambda c, e: errors.__setitem__(c.slug, e),
        report_company_count=lambda c, n: counts.__setitem__(c.slug, n),
    )
    assert len(jobs) == 3
    assert counts == {"airbnb": 3}
    assert errors["gone"] == "not found on this ATS"
    assert errors["broken"].startswith("unexpected response")
    assert errors["down"] == "HTTP 403"


async def test_smartrecruiters_lists_per_country_and_reads_only_matching_postings() -> None:
    base = "api.smartrecruiters.com/v1/companies/BoschGroup/postings"
    web = FakeWeb()
    web.fixture(base, "smartrecruiters_list.json")
    for pid in ("744000159434190", "744000159430569"):
        web.fixture(f"{base}/{pid}", f"smartrecruiters_{pid}.json")
    jobs, _ = await collect(
        SmartRecruiters(), web, companies=[CompanyRef("BoschGroup", "BoschGroup")]
    )
    assert [j.title for j in jobs] == ["Lead Data Analyst", "Data Analyst, Manufacturing"]
    assert [r.url.params["country"] for r in web.hits(base)] == ["us"]
    assert not web.hits(f"{base}/744000159420605")  # its title matches no target: not read
    first = jobs[0]
    assert first.company == "Bosch Group"
    assert first.remote is True
    assert first.url.startswith("https://jobs.smartrecruiters.com/BoschGroup/744000159434190")
    assert first.description.startswith("Job Description")
    assert "At Bosch, we care" not in first.description  # the company blurb is left out
    assert jobs[1].location == "Farmington Hills, MI, United States"


async def test_smartrecruiters_board_check_is_one_request() -> None:
    web = FakeWeb()
    web.fixture(
        "api.smartrecruiters.com/v1/companies/BoschGroup/postings", "smartrecruiters_list.json"
    )
    http = web.client()
    ctx = PortalContext(http=http, queries=())
    jobs = await SmartRecruiters().fetch_company(ctx, CompanyRef("BoschGroup", "BoschGroup"))
    await http.aclose()
    assert len(jobs) == 3
    assert len(web.requests) == 1
    assert SmartRecruiters().normalize(jobs[0]).company == "Bosch Group"


# --- feeds --------------------------------------------------------------------------------


async def test_remoteok_skips_legal_notice_and_links_back() -> None:
    web = FakeWeb().standard()
    jobs, _ = await collect(RemoteOK(), web)
    assert [j.external_id for j in jobs] == ["1137607", "1137606", "1137604"]
    assert all(j.remote is True and "remoteok.com" in j.url.lower() for j in jobs)
    assert jobs[1].location == "Remote"  # empty location in the feed
    assert jobs[2].title == "Online Client Support & Travel Booking We Will Train You"


async def test_remoteok_repairs_text_sent_as_latin_1() -> None:
    # Remote OK sends some postings as UTF-8 bytes read as Latin-1.
    company = b"Sotheby\xe2\x80\x99s"
    text = b"<p>$85,000\xe2\x80\x93$100,000 \xc2\xb7 caf\xc3\xa9</p>"
    web = FakeWeb()
    posting = {
        "id": 9,
        "position": "Front End Developer",
        "company": company.decode("latin-1"),
        "location": "",
        "description": text.decode("latin-1"),
    }
    web.json("remoteok.com/api", [{"legal": "..."}, posting])
    (job,), _ = await collect(RemoteOK(), web)
    assert job.company == company.decode("utf-8")
    assert f"<p>{job.description}</p>" == text.decode("utf-8")
    cut_short = b"\xe2\x80".decode("latin-1")  # not a whole UTF-8 character: kept
    word = b"na\xc3\xafve"
    assert fix_mojibake(f"{word.decode('latin-1')} {cut_short}") == f"{word.decode()} {cut_short}"


async def test_weworkremotely_splits_company_from_title() -> None:
    web = FakeWeb().standard()
    jobs, _ = await collect(WeWorkRemotely(), web)
    assert next((j.company, j.title) for j in jobs) == ("Databricks", "Deployment Strategist")
    assert jobs[0].external_id == "databricks-deployment-strategist"
    assert all(j.remote is True and j.posted_at is not None for j in jobs)


async def test_weworkremotely_refuses_feeds_with_a_dtd() -> None:
    web = FakeWeb()
    evil = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "boom">]><rss><channel/></rss>'
    web.route("weworkremotely.com/remote-jobs.rss", lambda _r: httpx2.Response(200, text=evil))
    with pytest.raises(PortalError, match="DTD"):
        await collect(WeWorkRemotely(), web)


async def test_adzuna_sends_keys_and_marks_estimates() -> None:
    web = FakeWeb().standard()
    secrets = {"adzuna_app_id": "id-1", "adzuna_app_key": "key-1"}
    jobs, _ = await collect(Adzuna(), web, secrets=secrets)
    params = web.requests[0].url.params
    assert (params["app_id"], params["app_key"], params["what"]) == (
        "id-1",
        "key-1",
        "Data Analyst",
    )
    assert len(web.requests) == 1  # fewer than a full page, so no second page
    first, second = jobs
    assert first.title == "Senior Data Analyst"  # <strong> highlighting removed
    assert first.company == "Northwind Analytics"
    assert first.salary_text == "95,000-120,000"
    assert second.salary_text == "70,321 (Adzuna estimate)"
    assert second.remote is True


async def test_adzuna_searches_a_commute_around_the_target_and_remote_jobs() -> None:
    web = FakeWeb().standard()
    secrets = {"adzuna_app_id": "id-1", "adzuna_app_key": "key-1"}
    near = SearchQuery("Data Analyst", locations=("Sterling Heights, Michigan",), country="US")
    await collect(Adzuna(), web, secrets=secrets, queries=[near])
    searches = [dict(r.url.params) for r in web.requests]
    assert [(p["what"], p.get("where"), p.get("distance")) for p in searches] == [
        ("Data Analyst", "Sterling Heights, Michigan", "40"),
        ("Data Analyst remote", None, None),
    ]
    web.requests.clear()
    remote = dataclasses.replace(near, remote_only=True)
    await collect(Adzuna(), web, secrets=secrets, queries=[remote])
    assert [r.url.params.get("where") for r in web.requests] == [None]


async def test_adzuna_skips_unsupported_countries_and_explains_bad_keys() -> None:
    web = FakeWeb()
    web.status("api.adzuna.com/v1/api/jobs/us/search/1", 401)
    secrets = {"adzuna_app_id": "id", "adzuna_app_key": "wrong"}
    with pytest.raises(PortalError, match="rejected"):
        await collect(Adzuna(), web, secrets=secrets)

    http = web.client()
    ctx = PortalContext(
        http=http, queries=[SearchQuery("Data Analyst", country="JP")], secrets=secrets
    )
    assert [raw async for raw in Adzuna().search(ctx, None)] == []
    await http.aclose()


async def test_usajobs_sends_required_headers() -> None:
    web = FakeWeb().standard()
    jobs, _ = await collect(
        USAJobs(), web, secrets={"usajobs_api_key": "k"}, config={"email": "me@example.com"}
    )
    request = web.requests[0]
    assert request.headers["Authorization-Key"] == "k"
    assert request.headers["User-Agent"] == "me@example.com"
    assert request.url.params["Keyword"] == "Data Analyst"
    (job,) = jobs
    assert job.title == "Data Analyst"
    assert job.company == "Bureau of Labor Statistics"
    assert job.salary_text == "USD 86,962-113,047 per year"
    assert job.remote is None
    assert job.posted_at == datetime(2026, 10, 27, tzinfo=UTC)
    assert job.description.startswith("Analyze employment statistics")


# --- polite HTTP client -------------------------------------------------------------------


async def test_client_retries_with_backoff_and_honors_retry_after() -> None:
    calls = 0

    def flaky(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(503)
        if calls == 2:
            return httpx2.Response(429, headers={"Retry-After": "7"})
        return httpx2.Response(200, json={"ok": True})

    web = FakeWeb()
    web.route("example.test/x", flaky)
    delays: list[float] = []

    async def record(seconds: float) -> None:
        delays.append(seconds)

    http = web.client(sleep=record, backoff_s=1.0)
    assert await http.json("https://example.test/x") == {"ok": True}
    assert calls == 3
    assert 1.0 <= delays[0] <= 1.25  # first backoff plus jitter
    assert 7.0 <= delays[1] <= 8.75  # Retry-After wins over the 2s backoff
    await http.aclose()


async def test_client_gives_up_and_does_not_retry_client_errors() -> None:
    web = FakeWeb()
    web.status("example.test/down", 502)
    http = web.client(retries=2)
    with pytest.raises(HttpError) as info:
        await http.get("https://example.test/down")
    assert info.value.status == 502
    assert "after 3 attempts" in str(info.value)
    assert len(web.hits("example.test/down")) == 3

    with pytest.raises(HttpError) as missing:
        await http.get("https://example.test/missing")
    assert missing.value.status == 404
    assert len(web.hits("example.test/missing")) == 1

    web.route("example.test/html", lambda _r: httpx2.Response(200, text="<html>"))
    with pytest.raises(HttpError, match="did not return JSON"):
        await http.json("https://example.test/html")
    await http.aclose()


async def test_client_retries_transport_errors() -> None:
    attempts = 0

    def drop(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx2.ConnectError("refused", request=request)
        return httpx2.Response(200, text="fine")

    web = FakeWeb()
    web.route("example.test/flaky", drop)
    http = web.client()
    assert await http.text("https://example.test/flaky") == "fine"
    await http.aclose()


async def test_default_client_identifies_itself() -> None:
    http = PoliteClient()
    assert USER_AGENT.startswith("RoleHawk/")
    assert http._client.headers["User-Agent"] == USER_AGENT
    await http.aclose()


async def test_host_pacer_spaces_requests_and_bounds_concurrency() -> None:
    pacer = HostPacer(min_interval_s=0.05, concurrency=2)
    starts: list[float] = []
    active = peak = 0

    async def request() -> None:
        nonlocal active, peak
        async with pacer:
            starts.append(time.monotonic())
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(request() for _ in range(4)))
    gaps = [b - a for a, b in itertools.pairwise(starts)]
    assert all(gap >= 0.045 for gap in gaps)
    assert peak <= 2


# --- text helpers -------------------------------------------------------------------------


def test_html_to_text_handles_lists_scripts_and_double_encoding() -> None:
    markup = "<p>About&nbsp;us</p><ul><li>SQL</li><li>Python</li></ul><script>x()</script>"
    assert html_to_text(markup) == "About us\n\n- SQL\n- Python"
    assert html_to_text("&lt;p&gt;Hi &amp;amp; bye&lt;/p&gt;") == "Hi & bye"
    assert html_to_text(None) == ""


def test_salary_and_dates_and_remote() -> None:
    assert salary_range(50000, 70000, "usd", "year") == "USD 50,000-70,000 per year"
    assert salary_range(0, None) is None
    assert salary_range("abc", 10) == "10"
    assert parse_datetime(1_700_000_000) == parse_datetime(1_700_000_000_000)
    assert parse_datetime("Fri, 31 Oct 2026 10:00:00 +0000") == datetime(
        2026, 10, 31, 10, tzinfo=UTC
    )
    assert parse_datetime("2026-10-31") == datetime(2026, 10, 31, tzinfo=UTC)
    assert parse_datetime("not a date") is None
    assert looks_remote("Remote - US") is True
    assert looks_remote("Berlin") is None


def test_job_hash_ignores_case_punctuation_and_company_suffixes() -> None:
    a = job_hash("Acme, Inc.", "Data Analyst", "Austin, TX")
    b = job_hash("acme", "data analyst ", "austin tx")
    assert a == b
    assert a != job_hash("Acme", "Data Analyst", "Dallas, TX")


# --- matching -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Data Analyst", True),
        ("Data Analyst II, Marketing", True),
        ("Analyst, Data Platform", True),
        ("Data Engineer", False),
        ("Front End Developer", True),
        ("Frontend Engineer (React)", True),
        ("Backend Engineer", False),
    ],
)
def test_title_matches_ignores_level_words(title: str, expected: bool) -> None:
    queries = [SearchQuery("Data Analyst"), SearchQuery("Frontend Engineer")]
    assert title_matches(title, queries) is expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # A bare "Developer" means developers, not every kind of engineer.
        ("Senior Java Developer - Security", True),
        ("Salesforce Developer", True),
        ("Controls Engineer: Power Generation", False),
        ("Senior Data Engineer, Ads", False),
        ("Senior Security Engineer", False),
        ("Senior Software Engineer, Data", False),
        # "Developer" has to be the job, not what the job is about.
        ("Developer Advocate", False),
        ("Product Manager, Developer Experience", False),
        ("Developer Engagement Lead", False),
        ("Copywriter, Developer", False),
        ("Software Engineer, Developer API", False),
        # Other trades that share the word.
        ("Technical Curriculum Developer - AI Agents - Remote", False),
        ("Instructional Content Developer", False),
        # The field has to belong to the role, not to a different job in the same title.
        ("Senior Full-Stack BI Architect / Fabric Data Engineer", False),
        ("Tech Lead/Senior Developer", True),
        ("Senior / Staff Fullstack Engineer", True),
        ("Senior Software Engineer, Backend/Fullstack (Advisor)", True),
        ("Senior Software Engineer, UI Tooling (Full Stack iOS)", True),
        # Spelling, word order, and trailing details still match.
        ("Front-End Engineer", True),
        ("Software Engineer, Frontend (React)", True),
        ("Staff Frontend Engineer | Canada | Remote", True),
        ("Senior Full-Stack Software Engineer, Growth", True),
        ("Frontend Engineer DACH", True),
        ("Frontend Engineer Contract", True),
        ("Frontend Platform Advocate", False),
    ],
)
def test_title_matches_the_role_not_just_the_words(title: str, expected: bool) -> None:
    queries = [
        SearchQuery("Senior Developer"),
        SearchQuery("Senior Frontend Developer"),
        SearchQuery("Senior Full Stack Engineer"),
    ]
    assert title_matches(title, queries) is expected


def test_a_target_that_names_the_trade_still_matches_it() -> None:
    assert title_matches("Curriculum Developer", [SearchQuery("Curriculum Developer")])


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Bengaluru, India", False),
        ("Toronto, ON, CA", False),
        ("Remote - Poland", False),
        ("San Francisco, CA", True),
        ("Remote, Canada; Remote, United States", True),
        ("Anywhere in the World", True),
        ("Remote", True),  # unknown never filters
        (None, True),
    ],
)
def test_jobs_only_in_other_countries_do_not_match(location: str | None, expected: bool) -> None:
    queries = [SearchQuery("Frontend Engineer")]
    assert job_matches("Frontend Engineer", location, queries) is expected


def test_each_target_keeps_its_own_country() -> None:
    queries = [SearchQuery("Frontend Engineer"), SearchQuery("Data Analyst", country="CA")]
    assert job_matches("Data Analyst", "Toronto, Canada", queries)
    assert not job_matches("Frontend Engineer", "Toronto, Canada", queries)


def test_a_target_of_only_level_words_matches_nothing() -> None:
    assert not title_matches("Lead Engineer", [SearchQuery("Lead")])


def test_keywords_widen_matching() -> None:
    query = SearchQuery("Data Analyst", keywords=("Business Intelligence",))
    assert title_matches("Business Intelligence Developer", [query])
    assert tokens("Senior Software Developers") == {"software", "engineer"}
