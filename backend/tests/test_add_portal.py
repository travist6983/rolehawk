"""/add-portal: detection (ATS, RSS, JSON-LD, JSON), Claude's fallback proposal, the
sandboxed test run (3+ jobs), plugin files that are data (never executed), the network
guard, and custom sources running in /scrape. All against a local fixture site."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import func, select

from offerbound.db.models import Job, Portal, SearchTarget
from offerbound.llm.fake import FakeProvider
from offerbound.llm.types import LLMRequest
from offerbound.portals.custom.definition import (
    FieldMap,
    HtmlDefinition,
    HtmlFields,
    JsonApiDefinition,
    JsonLdDefinition,
    RssDefinition,
    UnsafeUrlError,
    check_url,
    guess_company_in_title,
    site_domain,
    split_company,
)
from offerbound.portals.custom.detect import ats_link, find_job_list
from offerbound.portals.custom.engine import run_definition
from offerbound.portals.custom.generate import AiDraft
from offerbound.portals.custom.sandbox import clean_env, run_in_sandbox
from offerbound.portals.custom.store import parse_plugin, plugin_source
from offerbound.services.runtime import Runtime

pytestmark = pytest.mark.anyio

SITE = Path(__file__).parent / "fixtures" / "custom_site"
DETAIL = (
    '<html><head><script type="application/ld+json">{{"@type": "JobPosting", "title": "{title}", '
    '"hiringOrganization": {{"name": "Fabrikam"}}, "jobLocation": {{"address": '
    '{{"addressLocality": "Austin", "addressCountry": "US"}}}}}}</script></head>'
    "<body></body></html>"
)
TITLES = {"101": "Data Analyst", "102": "Product Analyst", "103": "Analytics Lead"}


@pytest.fixture
def site() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path.startswith("/jobs/") and path.rsplit("/", 1)[-1] in TITLES:
                body = DETAIL.format(title=TITLES[path.rsplit("/", 1)[-1]]).encode()
                return self._send(200, body, "text/html")
            if path == "/redirect-out":
                self.send_response(302)
                self.send_header("Location", "https://example.com/elsewhere")
                self.end_headers()
                return None
            if path == "/slow":
                time.sleep(3)
                return self._send(200, b"<html></html>", "text/html")
            file = SITE / path.strip("/")
            if not file.is_file():
                return self._send(404, b"missing", "text/plain")
            kind = {
                ".json": "application/json",
                ".rss": "application/rss+xml",
            }.get(file.suffix, "text/html")
            return self._send(200, file.read_bytes(), kind)

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def local(runtime: Runtime) -> Runtime:
    runtime.add_portal.allow_private = lambda: True  # the fixture site is on 127.0.0.1
    return runtime


# --- the network guard --------------------------------------------------------------------


def test_sources_stay_on_their_own_public_domain() -> None:
    assert site_domain("careers.example.co") == "example.co"
    assert site_domain("127.0.0.1") == "127.0.0.1"
    check_url("https://jobs.example.com/x", "example.com", allow_private=True)
    with pytest.raises(UnsafeUrlError, match="outside"):
        check_url("https://evil.test/x", "example.com", allow_private=True)
    with pytest.raises(UnsafeUrlError, match="private"):
        check_url("http://127.0.0.1:8765/api/session", "127.0.0.1")
    with pytest.raises(UnsafeUrlError, match="private"):
        check_url("http://localhost/x", "localhost")
    with pytest.raises(UnsafeUrlError, match="not a web URL"):
        check_url("file:///etc/passwd", "etc")
    with pytest.raises(ValueError, match="credentials"):
        RssDefinition(id="x1", name="x", source_url="https://u:p@a.com", feed_url="https://a.com/f")


def test_redirects_off_the_domain_are_refused(site: str) -> None:
    definition = RssDefinition(
        id="redir", name="Redirect", source_url=site, feed_url=f"{site}/redirect-out"
    )
    with pytest.raises(UnsafeUrlError, match="outside"):
        run_definition(definition, allow_private=True)


# --- detection ----------------------------------------------------------------------------


async def test_known_ats_links_go_to_the_watchlist(runtime: Runtime) -> None:
    assert ats_link("https://boards.greenhouse.io/stripe/jobs/1") == ("greenhouse", "stripe")
    found = await runtime.add_portal.inspect("https://jobs.lever.co/plaid")
    assert [(c.kind, c.ats, c.slug) for c in found.candidates] == [("watchlist", "lever", "plaid")]


async def test_detects_rss_jsonld_and_json(runtime: Runtime, site: str) -> None:
    service = local(runtime).add_portal

    rss = await service.inspect(f"{site}/careers-rss.html")
    assert rss.page_title == "Northwind"
    (feed,) = rss.candidates
    assert feed.kind == "rss"
    assert isinstance(feed.definition, RssDefinition)
    assert feed.definition.feed_url == f"{site}/jobs.rss"

    on_page = await service.inspect(f"{site}/careers-jsonld.html")
    assert [c.kind for c in on_page.candidates] == ["jsonld"]
    assert "3 JobPosting" in on_page.candidates[0].detail

    linked = await service.inspect(f"{site}/careers-links.html")
    (candidate,) = linked.candidates
    assert isinstance(candidate.definition, JsonLdDefinition)
    assert candidate.definition.link_pattern is not None
    assert "3 job links" in candidate.detail

    api = await service.inspect(f"{site}/api-jobs.json")
    (json_candidate,) = api.candidates
    assert isinstance(json_candidate.definition, JsonApiDefinition)
    assert json_candidate.definition.items_path == "data.jobs"
    assert json_candidate.definition.fields.url == "absolute_url"
    assert json_candidate.definition.fields.location == "location.name"

    nothing = await service.inspect(f"{site}/careers-plain.html")
    assert nothing.candidates == []
    missing = await service.inspect(f"{site}/nope")
    assert missing.error == f"HTTP 404 from {site}/nope"


def test_company_in_feed_titles() -> None:
    assert split_company("Senior Python Engineer, webbyfox consultancy", "suffix_comma") == (
        "webbyfox consultancy",
        "Senior Python Engineer",
    )
    assert split_company(
        "Engineer \N{EM DASH} Python, React & AI, Camden Kelly", "suffix_comma"
    ) == (
        "Camden Kelly",
        "Engineer \N{EM DASH} Python, React & AI",
    )
    assert split_company("Acme: Data Analyst", "prefix_colon") == ("Acme", "Data Analyst")
    assert split_company("Analyst at Acme", "suffix_at") == ("Acme", "Analyst")
    assert split_company("Data Analyst", "suffix_comma") == (None, "Data Analyst")
    assert split_company("Acme: Analyst", "none") == (None, "Acme: Analyst")

    python_org = ["Backend Engineer, Acme", "Data Engineer, Initech", "SRE, Globex", "QA, Hooli"]
    assert guess_company_in_title(python_org) == "suffix_comma"
    assert guess_company_in_title([f"Acme: {t}" for t in python_org]) == "prefix_colon"
    assert guess_company_in_title(["Data Analyst", "BI Engineer", "Analyst, Reporting"]) == "none"
    assert guess_company_in_title(["Analyst, Acme"]) == "none"  # too few to tell


def test_finds_job_lists_in_json() -> None:
    assert find_job_list({"results": [{"name": "x", "link": "y"}]}) == (
        "results",
        [{"name": "x", "link": "y"}],
    )
    assert find_job_list({"results": [{"count": 1}]}) is None


# --- running definitions ------------------------------------------------------------------


def test_engine_reads_each_kind(site: str) -> None:
    rss, _ = run_definition(
        RssDefinition(
            id="nw",
            name="Northwind",
            source_url=site,
            feed_url=f"{site}/jobs.rss",
            company_in_title="prefix_colon",
        ),
        allow_private=True,
    )
    assert [(j.company, j.title) for j in rss][:2] == [
        ("Northwind", "Data Analyst"),
        ("Northwind", "Senior Data Analyst"),
    ]
    assert rss[0].url == f"{site}/jobs/data-analyst"
    assert rss[0].description == "SQL and Looker."
    assert rss[0].posted_at is not None

    ld, _ = run_definition(
        JsonLdDefinition(
            id="ct", name="Contoso", source_url=site, list_url=f"{site}/careers-jsonld.html"
        ),
        allow_private=True,
    )
    assert [(j.title, j.location, j.remote) for j in ld] == [
        ("Data Analyst", "Denver, CO, US", None),
        ("BI Developer", "Remote", True),
        ("Data Engineer", None, None),
    ]
    assert ld[0].external_id == "C-1"

    linked, errors = run_definition(
        JsonLdDefinition(
            id="fb",
            name="Fabrikam",
            source_url=site,
            list_url=f"{site}/careers-links.html",
            link_pattern=r"/jobs/\d+$",
        ),
        allow_private=True,
    )
    assert errors == []
    assert sorted(j.title for j in linked) == ["Analytics Lead", "Data Analyst", "Product Analyst"]

    api, _ = run_definition(
        JsonApiDefinition(
            id="ex",
            name="Example",
            source_url=site,
            api_url=f"{site}/api-jobs.json",
            items_path="data.jobs",
            fields=FieldMap(title="title", url="absolute_url", id="id", location="location.name"),
        ),
        allow_private=True,
    )
    assert [(j.external_id, j.url) for j in api] == [
        ("7", "https://jobs.example.test/7"),
        ("8", f"{site}/jobs/8"),
        ("9", f"{site}/jobs/9"),
    ]

    html, _ = run_definition(
        HtmlDefinition(
            id="in",
            name="Initech",
            source_url=site,
            list_url=f"{site}/careers-plain.html",
            company="Initech",
            item_selector="div.job-card",
            fields=HtmlFields(title=".job-title", location=".loc"),
        ),
        allow_private=True,
    )
    assert [(j.title, j.location) for j in html] == [
        ("Data Analyst", "Austin, TX"),
        ("Reporting Analyst", "Remote"),
        ("BI Engineer", "Dallas, TX"),
    ]  # the javascript: link was dropped


async def test_sandbox_runs_out_of_process_with_a_timeout(site: str) -> None:
    definition = RssDefinition(id="nw", name="N", source_url=site, feed_url=f"{site}/jobs.rss")
    result = await run_in_sandbox(definition, allow_private=True)
    assert result.ok
    assert len(result.jobs) == 4

    blocked = await run_in_sandbox(definition)  # the default: private addresses refused
    assert not blocked.ok
    assert "private address" in (blocked.error or "")

    slow = HtmlDefinition(id="sl", name="S", source_url=site, list_url=f"{site}/slow",
                          item_selector="li", fields=HtmlFields(title="a"))  # fmt: skip
    stopped = await run_in_sandbox(slow, allow_private=True, timeout_s=1)
    assert stopped.error == "stopped after 1s"


def test_sandbox_environment_has_no_secrets() -> None:
    env = clean_env({"PATH": "/bin", "ANTHROPIC_API_KEY": "sk-x", "OFFERBOUND_HOME": "/h",
                     "SYSTEMROOT": "C:\\Windows", "HOME": "/home/ada"})  # fmt: skip
    assert env == {"PATH": "/bin", "SYSTEMROOT": "C:\\Windows"}


# --- plugin files -------------------------------------------------------------------------


def test_plugin_files_are_data_never_code(tmp_path: Path) -> None:
    definition = RssDefinition(
        id="northwind",
        name='Northwind """quotes"""',
        source_url="https://northwind.example",
        feed_url="https://northwind.example/jobs.rss",
    )
    source = plugin_source(definition)
    assert "This file is data, not code" in source
    assert parse_plugin(source) == definition

    canary = tmp_path / "ran.txt"
    hostile = (
        f"import pathlib\npathlib.Path({str(canary)!r}).write_text('x')\n"
        + source.split("DEFINITION = ", 1)[0]
        + "DEFINITION = "
        + source.split("DEFINITION = ", 1)[1]
    )
    assert parse_plugin(hostile) == definition
    assert not canary.exists()  # parsing never executes anything

    with pytest.raises(ValueError, match="malformed node"):
        parse_plugin("DEFINITION = __import__('os').getcwd()")
    with pytest.raises(ValueError, match="no DEFINITION"):
        parse_plugin("x = 1")


# --- the service: test, add, scrape, remove -----------------------------------------------


async def test_add_needs_three_jobs_and_runs_in_scrape(runtime: Runtime, site: str) -> None:
    service = local(runtime).add_portal
    too_few = JsonLdDefinition(id="tiny", name="Tiny", source_url=site, list_url=f"{site}/two.html")
    result = await service.test(too_few)
    assert (result.ok, result.count) == (False, 2)
    assert result.error == "Found 2 jobs; a source needs at least 3."
    with pytest.raises(ValueError, match="at least 3"):
        await service.add(too_few)

    definition = RssDefinition(id="northwind", name="Northwind", source_url=site,
                               feed_url=f"{site}/jobs.rss")  # fmt: skip
    tested = await service.test(definition)
    assert tested.ok
    assert len(tested.samples) == 4
    # The run noticed titles look like "Northwind: Data Analyst" and settled the pattern.
    assert isinstance(tested.definition, RssDefinition)
    assert tested.definition.company_in_title == "prefix_colon"
    assert (tested.samples[0].company, tested.samples[0].title) == ("Northwind", "Data Analyst")
    assert "'company_in_title': 'prefix_colon'" in tested.plugin_source
    assert "DEFINITION = " in tested.plugin_source
    await service.add(definition)

    assert (runtime.paths.portals / "northwind.py").is_file()
    assert (
        "'company_in_title': 'prefix_colon'" in (runtime.paths.portals / "northwind.py").read_text()
    )
    view = runtime.portals.view("custom-northwind")
    assert (view.custom, view.kind, view.risk_level, view.ready) == (True, "plugin", "low", True)

    with runtime.sessions.begin() as session:
        session.add(SearchTarget(title="Data Analyst", country="US"))

    async def progress(_f: float | None, _m: str | None) -> None:
        return None

    summary = await runtime.scraper.run(progress, ["custom-northwind"])
    (run,) = summary.portals
    assert (run.status, run.found, run.matched, run.new) == ("ok", 4, 2, 2)

    assert service.remove("northwind") is True
    assert not (runtime.paths.portals / "northwind.py").exists()
    with runtime.sessions() as session:
        assert session.get(Portal, "custom-northwind") is None
        assert session.scalar(select(func.count()).select_from(Job)) == 0
    assert service.remove("northwind") is False


async def test_claude_proposes_selectors_when_detection_fails(
    runtime: Runtime, fake: FakeProvider, site: str
) -> None:
    prompts: list[str] = []

    def handler(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        assert schema is AiDraft
        prompts.append(request.messages[-1].text)
        return AiDraft(
            kind="html",
            reason="Jobs are cards in the openings section.",
            api_url=None,
            items_path=None,
            title_path=None,
            url_path=None,
            id_path=None,
            location_path=None,
            company_path=None,
            description_path=None,
            item_selector="div.job-card",
            title_selector=".job-title",
            link_selector=None,
            location_selector=".loc",
            company_selector=None,
        )

    fake.structured_handler = handler
    candidate = await local(runtime).add_portal.draft(f"{site}/careers-plain.html", "Initech")
    assert isinstance(candidate.definition, HtmlDefinition)
    assert candidate.definition.item_selector == "div.job-card"
    assert "<untrusted_content" in prompts[0]
    assert "<script" not in prompts[0]
    assert (await runtime.add_portal.test(candidate.definition)).count == 3


# --- API ----------------------------------------------------------------------------------


def runtime_of(client: TestClient) -> Runtime:
    runtime: Runtime = cast(FastAPI, client.app).state.runtime
    return runtime


def test_add_portal_api(client: TestClient, site: str) -> None:
    local(runtime_of(client))
    inspected = client.post("/api/portals/inspect", json={"url": f"{site}/careers-jsonld.html"})
    (candidate,) = inspected.json()["candidates"]
    definition = candidate["definition"]
    assert definition["kind"] == "jsonld"

    tested = client.post("/api/portals/test", json={"definition": definition}).json()
    assert (tested["ok"], tested["count"]) == (True, 3)
    assert tested["samples"][0]["title"] == "Data Analyst"

    added = client.post("/api/portals/custom", json={"definition": definition})
    assert added.status_code == 201
    assert added.json()["custom"] is True
    assert any(p["id"] == f"custom-{definition['id']}" for p in client.get("/api/portals").json())

    bad = dict(definition, list_url=f"{site}/two.html", id="tiny")
    assert client.post("/api/portals/custom", json={"definition": bad}).status_code == 422
    assert (
        client.post("/api/portals/test", json={"definition": {"kind": "exec"}}).status_code == 422
    )

    assert client.delete(f"/api/portals/custom/{definition['id']}").status_code == 204
    assert client.delete(f"/api/portals/custom/{definition['id']}").status_code == 404


def test_add_portal_commands_stay_out_of_chat(client: TestClient) -> None:
    commands = {c["name"]: c for c in client.get("/api/commands").json()}
    for name in ("portal-inspect", "portal-draft", "portal-test", "portal-add", "portal-remove"):
        assert commands[name]["chat_allowed"] is False


def test_definitions_round_trip_as_json() -> None:
    definition = JsonApiDefinition(
        id="ex",
        name="Ex",
        source_url="https://ex.com",
        api_url="https://ex.com/api?page={page}",
        fields=FieldMap(title="t", url="u"),
        pages=3,
    )
    assert json.loads(definition.model_dump_json())["pages"] == 3
