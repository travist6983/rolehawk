"""Runs a custom source definition: fetch (inside the source's domain only, never private
addresses), parse RSS / JSON-LD / JSON / HTML, and return normalized jobs."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx2
from bs4 import BeautifulSoup, Tag

from rolehawk.portals.base import NormalizedJob
from rolehawk.portals.custom.definition import (
    HtmlDefinition,
    JsonApiDefinition,
    JsonLdDefinition,
    RssDefinition,
    UnsafeUrlError,
    check_url,
    split_company,
)
from rolehawk.portals.feeds import _safe_xml
from rolehawk.portals.http import USER_AGENT
from rolehawk.portals.integrity import clean_posting
from rolehawk.portals.text import html_to_text, looks_remote, parse_date, parse_datetime

Definition = RssDefinition | JsonLdDefinition | JsonApiDefinition | HtmlDefinition

MAX_REDIRECTS = 5
MAX_BYTES = 5_000_000
MAX_ROBOTS_BYTES = 500_000  # RFC 9309 asks crawlers to read at least 500 KiB
MAX_JOBS = 500


class EngineError(RuntimeError):
    pass


class RobotsBlockedError(EngineError):
    """The site's robots.txt asks tools like this one not to read the page."""


class Fetcher:
    """GET with every hop checked: same domain, public address, robots.txt, size cap, no
    cookies kept."""

    def __init__(self, domain: str, *, allow_private: bool = False, timeout_s: float = 20) -> None:
        self.domain = domain
        self.allow_private = allow_private
        self.client = httpx2.Client(
            timeout=timeout_s, follow_redirects=False, headers={"User-Agent": USER_AGENT}
        )
        self._robots: dict[str, RobotFileParser] = {}

    def _allowed(self, url: str) -> bool:
        """robots.txt per RFC 9309: a missing file (4xx) allows everything; a server error or
        no answer means stay away. Read once per origin, through the same hop checks."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rules = self._robots.get(origin)
        if rules is None:
            rules = RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            check_url(robots_url, self.domain, allow_private=self.allow_private)
            try:
                response = self.client.get(robots_url)
            except httpx2.HTTPError as exc:
                raise EngineError(f"couldn't read {robots_url}: {exc}") from exc
            if response.status_code >= 500:
                raise EngineError(f"{robots_url} answered HTTP {response.status_code}")
            if response.status_code >= 400 or response.is_redirect:
                rules.parse([])
            else:
                rules.parse(
                    response.content[:MAX_ROBOTS_BYTES].decode("utf-8", "replace").splitlines()
                )
            self._robots[origin] = rules
        return rules.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> httpx2.Response:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url, self.domain, allow_private=self.allow_private)
            if not self._allowed(url):
                raise RobotsBlockedError(
                    f"the site's robots.txt asks tools like this not to read {url}"
                )
            response = self.client.get(url)
            if response.is_redirect and "location" in response.headers:
                url = urljoin(url, response.headers["location"])
                continue
            if response.status_code >= 400:
                raise EngineError(f"HTTP {response.status_code} from {url}")
            if len(response.content) > MAX_BYTES:
                raise EngineError(f"{url} is larger than {MAX_BYTES // 1_000_000} MB")
            return response
        raise EngineError(f"too many redirects from {url}")

    def close(self) -> None:
        self.client.close()


def dig(data: Any, path: str | None) -> Any:
    """`a.b.0.c` into nested dicts and lists; None when any step is missing."""
    if not path:
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict):
        value = value.get("name") or value.get("text") or value.get("value")
    if isinstance(value, list):
        value = ", ".join(t for t in (_text(v) for v in value) if t)
    return value


def _text(value: Any) -> str | None:
    value = _unwrap(value)
    text = html_to_text(str(value)) if value is not None else ""
    return text or None


def _job(
    *,
    external_id: Any,
    url: Any,
    title: Any,
    company: Any,
    location: Any = None,
    description: Any = None,
    posted_at: Any = None,
    closes_at: Any = None,
    base: str,
) -> NormalizedJob | None:
    title_text, link = _text(title), _text(url)
    if not title_text or not link:
        return None
    link = urljoin(base, link)
    if not link.startswith(("https://", "http://")):
        return None
    where = _text(location)
    body = _unwrap(description)
    desc = clean_posting(str(body) if body is not None else None)
    return NormalizedJob(
        external_id=str(external_id or link)[:255],
        url=link,
        company=_text(company) or "",
        title=title_text[:255],
        location=where,
        remote=looks_remote(where, title_text),
        description=desc.text,
        integrity=desc.integrity,
        posted_at=parse_datetime(posted_at) if isinstance(posted_at, str | int | float) else None,
        closes_at=parse_date(closes_at) if isinstance(closes_at, str) else None,
    )


# --- JSON-LD ------------------------------------------------------------------------------


def _jsonld_blocks(html: str) -> Iterator[Any]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            yield json.loads(script.get_text() or "null")
        except ValueError:
            continue


def _postings(node: Any) -> Iterator[dict[str, Any]]:
    """Every JobPosting in a JSON-LD tree (bare, in @graph, or in an ItemList)."""
    if isinstance(node, list):
        for item in node:
            yield from _postings(item)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "JobPosting" in kinds:
            yield node
        for key in ("@graph", "itemListElement", "item"):
            if key in node:
                yield from _postings(node[key])


def postings_in(html: str) -> list[dict[str, Any]]:
    return [p for block in _jsonld_blocks(html) for p in _postings(block)]


def from_posting(
    posting: dict[str, Any], page_url: str, company: str | None
) -> NormalizedJob | None:
    org = posting.get("hiringOrganization")
    place = posting.get("jobLocation")
    if isinstance(place, list):
        place = place[0] if place else None
    address = dig(place, "address") if isinstance(place, dict) else None
    location = (
        ", ".join(
            str(v)
            for v in (
                dig(address, "addressLocality"),
                dig(address, "addressRegion"),
                dig(address, "addressCountry"),
            )
            if isinstance(v, str) and v
        )
        if isinstance(address, dict)
        else _text(address)
    )
    if posting.get("jobLocationType") == "TELECOMMUTE":
        location = f"{location} (remote)" if location else "Remote"
    return _job(
        external_id=dig(posting, "identifier.value")
        or posting.get("identifier")
        or posting.get("url"),
        url=posting.get("url") or page_url,
        title=posting.get("title"),
        company=company or org,
        location=location,
        description=posting.get("description"),
        posted_at=posting.get("datePosted"),
        closes_at=posting.get("validThrough"),
        base=page_url,
    )


def run_jsonld(d: JsonLdDefinition, fetch: Fetcher) -> tuple[list[NormalizedJob], list[str]]:
    page = fetch.get(d.list_url)
    errors: list[str] = []
    jobs = [j for p in postings_in(page.text) if (j := from_posting(p, str(page.url), d.company))]
    if jobs or not d.link_pattern:
        return jobs, errors
    pattern = re.compile(d.link_pattern)
    soup = BeautifulSoup(page.text, "html.parser")
    links = list(
        dict.fromkeys(
            urljoin(str(page.url), str(a["href"]))
            for a in soup.find_all("a", href=True)
            if isinstance(a, Tag) and pattern.search(str(a["href"]))
        )
    )[: d.max_pages]
    for link in links:
        try:
            detail = fetch.get(link)
        except (EngineError, UnsafeUrlError, httpx2.HTTPError) as exc:
            errors.append(f"{link}: {exc}")
            continue
        jobs += [j for p in postings_in(detail.text) if (j := from_posting(p, link, d.company))]
    return jobs, errors


# --- RSS ----------------------------------------------------------------------------------


def run_rss(d: RssDefinition, fetch: Fetcher) -> tuple[list[NormalizedJob], list[str]]:
    root = _safe_xml(fetch.get(d.feed_url).text)
    jobs: list[NormalizedJob] = []
    atom = "{http://www.w3.org/2005/Atom}"
    items = list(root.iter("item")) or list(root.iter(f"{atom}entry"))
    for item in items:
        fields = {child.tag.removeprefix(atom): (child.text or "").strip() for child in item}
        link = fields.get("link")
        if not link:
            node = item.find(f"{atom}link")
            link = node.get("href") if node is not None else None
        title = fields.get("title", "")
        company, title = split_company(title, d.company_in_title)
        company = company or d.company
        job = _job(
            external_id=fields.get("guid") or fields.get("id") or link,
            url=link,
            title=title,
            company=company,
            location=fields.get("location") or fields.get("region"),
            description=fields.get("description") or fields.get("summary") or fields.get("content"),
            posted_at=fields.get("pubDate") or fields.get("published") or fields.get("updated"),
            base=d.feed_url,
        )
        if job:
            jobs.append(job)
    return jobs, []


# --- JSON API -----------------------------------------------------------------------------


def run_json(d: JsonApiDefinition, fetch: Fetcher) -> tuple[list[NormalizedJob], list[str]]:
    jobs: list[NormalizedJob] = []
    errors: list[str] = []
    f = d.fields
    for page in range(1, d.pages + 1):
        url = d.api_url.replace("{page}", str(page))
        try:
            data = fetch.get(url).json()
        except ValueError as exc:
            raise EngineError(f"{url} didn't return JSON") from exc
        items = dig(data, d.items_path)
        if not isinstance(items, list):
            raise EngineError(f"no list at '{d.items_path or '(top level)'}' in {url}")
        for item in items:
            job = _job(
                external_id=dig(item, f.id),
                url=dig(item, f.url),
                title=dig(item, f.title),
                company=d.company or dig(item, f.company),
                location=dig(item, f.location),
                description=dig(item, f.description),
                posted_at=dig(item, f.posted_at),
                base=d.url_prefix or url,
            )
            if job:
                jobs.append(job)
        if not items or "{page}" not in d.api_url:
            break
    return jobs, errors


# --- HTML ---------------------------------------------------------------------------------


def run_html(d: HtmlDefinition, fetch: Fetcher) -> tuple[list[NormalizedJob], list[str]]:
    page = fetch.get(d.list_url)
    soup = BeautifulSoup(page.text, "html.parser")
    jobs: list[NormalizedJob] = []
    for item in soup.select(d.item_selector):
        title = item.select_one(d.fields.title)
        if title is None:
            continue
        link_node = item.select_one(d.fields.link) if d.fields.link else None
        if link_node is None:
            link_node = title if title.name == "a" else title.find("a") or item.find("a")
        href = link_node.get("href") if isinstance(link_node, Tag) else None

        def text_of(selector: str | None, node: Tag = item) -> str | None:
            found = node.select_one(selector) if selector else None
            return found.get_text(" ", strip=True) if found else None

        job = _job(
            external_id=href,
            url=href,
            title=title.get_text(" ", strip=True),
            company=d.company or text_of(d.fields.company),
            location=text_of(d.fields.location),
            base=str(page.url),
        )
        if job:
            jobs.append(job)
    return jobs, []


def run_definition(
    definition: Definition, *, allow_private: bool = False, limit: int = MAX_JOBS
) -> tuple[list[NormalizedJob], list[str]]:
    fetch = Fetcher(definition.domain, allow_private=allow_private)
    try:
        if isinstance(definition, RssDefinition):
            jobs, errors = run_rss(definition, fetch)
        elif isinstance(definition, JsonLdDefinition):
            jobs, errors = run_jsonld(definition, fetch)
        elif isinstance(definition, JsonApiDefinition):
            jobs, errors = run_json(definition, fetch)
        else:
            jobs, errors = run_html(definition, fetch)
    finally:
        fetch.close()
    unique = list({j.external_id: j for j in jobs}.values())
    return unique[:limit], errors
