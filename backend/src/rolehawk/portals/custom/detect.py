"""/add-portal detection: look at a careers URL and find the most reliable way to read it,
best first: a known ATS (add the company to the watchlist), an RSS/Atom feed, JSON-LD
JobPosting data (on the page or on the job pages it links to), a JSON API. HTML scraping is
the last resort and needs Claude to propose selectors (generate.py)."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx2
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel

from rolehawk.portals.custom.definition import (
    FieldMap,
    JsonApiDefinition,
    JsonLdDefinition,
    PortalDefinition,
    RssDefinition,
    UnsafeUrlError,
    site_domain,
)
from rolehawk.portals.custom.engine import EngineError, Fetcher, dig, postings_in

EXCERPT_CHARS = 14_000
JOB_LINK = re.compile(r"/(jobs?|careers?|positions?|openings?|vacanc(y|ies)|roles?)/", re.I)
ATS_LINKS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?:job-)?boards(?:\.eu)?\.greenhouse\.io/([A-Za-z0-9._-]+)"), "greenhouse"),
    (re.compile(r"^boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9._-]+)"), "greenhouse"),
    (re.compile(r"^jobs(?:\.eu)?\.lever\.co/([A-Za-z0-9._-]+)"), "lever"),
    (re.compile(r"^jobs\.ashbyhq\.com/([A-Za-z0-9._-]+)"), "ashby"),
    (re.compile(r"^apply\.workable\.com/([A-Za-z0-9._-]+)"), "workable"),
    (re.compile(r"^(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9._-]+)"), "smartrecruiters"),
]
TITLE_KEYS = ("title", "jobTitle", "job_title", "name", "position", "text")
URL_KEYS = ("url", "absolute_url", "hostedUrl", "jobUrl", "applyUrl", "apply_url", "link", "href")
LOCATION_KEYS = ("location", "location.name", "locationName", "city", "categories.location")
ID_KEYS = ("id", "jobId", "job_id", "uuid", "requisitionId")
DESCRIPTION_KEYS = ("description", "content", "descriptionPlain", "summary")
DATE_KEYS = (
    "datePosted",
    "posted_at",
    "postedAt",
    "created_at",
    "createdAt",
    "updated_at",
    "publishedAt",
)


class Candidate(BaseModel):
    kind: Literal["watchlist", "rss", "jsonld", "json_api", "html"]
    title: str
    detail: str
    definition: PortalDefinition | None = None
    ats: str | None = None
    slug: str | None = None


class Inspection(BaseModel):
    url: str
    final_url: str | None
    page_title: str | None
    candidates: list[Candidate]
    error: str | None = None


class PageSample(BaseModel):
    """Third-party page content for Claude to propose a definition from."""

    url: str
    excerpt: str
    api_hints: list[str]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return (slug or "site")[:40].strip("-") or "site"


def _base_fields(url: str, name: str) -> dict[str, Any]:
    return {"id": slugify(name), "name": name[:80], "source_url": url}


def ats_link(url: str) -> tuple[str, str] | None:
    parts = urlsplit(url)
    target = f"{parts.hostname or ''}{parts.path}"
    for pattern, ats in ATS_LINKS:
        match = pattern.match(target)
        if match:
            return ats, match.group(1)
    return None


def _first_key(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    return next(
        (k for k in keys if isinstance(dig(item, k), str | int) and dig(item, k) != ""), None
    )


def find_job_list(
    data: Any, path: str = "", depth: int = 0
) -> tuple[str, list[dict[str, Any]]] | None:
    """The first list of objects that look like jobs (have a title-like and a link-like key)."""
    if depth > 4:
        return None
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data[:5]):
        sample = data[0]
        if _first_key(sample, TITLE_KEYS) and _first_key(sample, URL_KEYS):
            return path, data
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_$@-]+", key):
                continue
            found = find_job_list(value, f"{path}.{key}" if path else key, depth + 1)
            if found:
                return found
    return None


def json_candidate(url: str, data: Any, name: str) -> Candidate | None:
    found = find_job_list(data)
    if not found:
        return None
    path, items = found
    sample = items[0]
    fields = FieldMap(
        title=_first_key(sample, TITLE_KEYS) or "title",
        url=_first_key(sample, URL_KEYS) or "url",
        id=_first_key(sample, ID_KEYS),
        location=_first_key(sample, LOCATION_KEYS),
        description=_first_key(sample, DESCRIPTION_KEYS),
        posted_at=_first_key(sample, DATE_KEYS),
    )
    definition = JsonApiDefinition(
        **_base_fields(url, name), api_url=url, items_path=path, fields=fields
    )
    return Candidate(
        kind="json_api",
        title="JSON job list",
        detail=f"{len(items)} jobs at '{path or 'the top level'}', mapped automatically",
        definition=definition,
    )


def _page_name(soup: BeautifulSoup, url: str) -> str:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = re.split("\\s+[|\N{EN DASH}\N{EM DASH}-]\\s+", title)[-1] if title else ""
    return title or (urlsplit(url).hostname or "site").removeprefix("www.")


def _link_pattern(links: list[str]) -> str:
    """A regex matching job page paths like the examples: /jobs/123 -> ^/jobs/[^/?#]+/?$"""
    path = urlsplit(links[0]).path.rstrip("/")
    prefix = path.rsplit("/", 1)[0]
    return "^(?:https?://[^/]+)?" + re.escape(prefix) + r"/[^/?#]+/?$"


JOB_WORDS = re.compile(r"jobs?|careers?|positions?|openings?|vacanc|hiring|roles?", re.I)
FEED_TYPES = ("application/rss+xml", "application/atom+xml")


def job_feeds(soup: BeautifulSoup, page_url: str, domain: str) -> list[tuple[str, str]]:
    """Feeds the page links (in <head> or as "Subscribe via RSS" links) on the same domain,
    best first: ones that say they're about jobs, then ones on the page's own host. Sites
    often link several (news, releases...), so a feed is only offered if it looks like jobs
    or it's the only one."""
    found: dict[str, str] = {}
    for tag in soup.find_all(["link", "a"], href=True):
        if not isinstance(tag, Tag):
            continue
        href = str(tag["href"])
        is_feed = (tag.name == "link" and str(tag.get("type") or "") in FEED_TYPES) or (
            tag.name == "a" and re.search(r"rss|atom|feed", href, re.I) is not None
        )
        if not is_feed:
            continue
        feed = urljoin(page_url, href)
        if site_domain(urlsplit(feed).hostname or "") != domain:
            continue
        label = str(tag.get("title") or tag.get_text(" ", strip=True) or "")
        found.setdefault(feed, label)
    host = urlsplit(page_url).hostname

    def score(item: tuple[str, str]) -> int:
        feed, label = item
        return 2 * bool(JOB_WORDS.search(f"{label} {feed}")) + int(urlsplit(feed).hostname == host)

    ranked = sorted(found.items(), key=score, reverse=True)
    jobs = [item for item in ranked if JOB_WORDS.search(f"{item[1]} {item[0]}")]
    return jobs or (ranked if len(ranked) == 1 else [])


def inspect(url: str, *, allow_private: bool = False) -> Inspection:
    known = ats_link(url)
    if known:
        ats, slug = known
        return Inspection(
            url=url,
            final_url=url,
            page_title=None,
            candidates=[
                Candidate(
                    kind="watchlist",
                    title=f"{ats.title()} job board",
                    detail=f"Add '{slug}' to your {ats.title()} watchlist; it's searched already.",
                    ats=ats,
                    slug=slug,
                )
            ],
        )
    host = urlsplit(url).hostname or ""
    fetch = Fetcher(site_domain(host), allow_private=allow_private)
    try:
        page = fetch.get(url)
        candidates: list[Candidate] = []
        content_type = page.headers.get("content-type", "")
        name = (urlsplit(str(page.url)).hostname or host).removeprefix("www.")

        if "json" in content_type:
            try:
                candidate = json_candidate(url, page.json(), name)
            except ValueError:
                candidate = None
            if candidate:
                candidates.append(candidate)
            return Inspection(
                url=url, final_url=str(page.url), page_title=None, candidates=candidates
            )

        text = page.text
        if "xml" in content_type or text.lstrip().startswith(("<?xml", "<rss", "<feed")):
            candidates.append(
                Candidate(
                    kind="rss",
                    title="Job feed (RSS/Atom)",
                    detail="The link is a feed.",
                    definition=RssDefinition(**_base_fields(url, name), feed_url=url),
                )
            )
            return Inspection(
                url=url, final_url=str(page.url), page_title=None, candidates=candidates
            )

        soup = BeautifulSoup(text, "html.parser")
        name = _page_name(soup, url)
        for feed, label in job_feeds(soup, str(page.url), fetch.domain)[:3]:
            candidates.append(
                Candidate(
                    kind="rss",
                    title="Job feed (RSS/Atom)",
                    detail=f"{label}: {feed}" if label else f"The page links a feed: {feed}",
                    definition=RssDefinition(**_base_fields(url, name), feed_url=feed),
                )
            )

        on_page = postings_in(text)
        if on_page:
            candidates.append(
                Candidate(
                    kind="jsonld",
                    title="Structured job data (JSON-LD)",
                    detail=f"{len(on_page)} JobPosting entries on this page.",
                    definition=JsonLdDefinition(**_base_fields(url, name), list_url=url),
                )
            )
        else:
            links = list(
                dict.fromkeys(
                    urljoin(str(page.url), str(a["href"]))
                    for a in soup.find_all("a", href=True)
                    if isinstance(a, Tag) and JOB_LINK.search(str(a["href"]))
                )
            )
            links = [link for link in links if link.rstrip("/") != str(page.url).rstrip("/")]
            for link in links[:3]:
                try:
                    detail = fetch.get(link)
                except (EngineError, UnsafeUrlError, httpx2.HTTPError):
                    continue
                if postings_in(detail.text):
                    pattern = _link_pattern([link])
                    matching = [other for other in links if re.search(pattern, other)]
                    candidates.append(
                        Candidate(
                            kind="jsonld",
                            title="Structured job data on job pages (JSON-LD)",
                            detail=f"{len(matching)} job links; each page has JobPosting data.",
                            definition=JsonLdDefinition(
                                **_base_fields(url, name), list_url=url, link_pattern=pattern
                            ),
                        )
                    )
                    break
        return Inspection(url=url, final_url=str(page.url), page_title=name, candidates=candidates)
    except (EngineError, UnsafeUrlError, httpx2.HTTPError) as exc:
        return Inspection(url=url, final_url=None, page_title=None, candidates=[], error=str(exc))
    finally:
        fetch.close()


_API_HINT = re.compile(r"""["'](/[^"'\s]*?(?:api|jobs?|positions|openings)[^"'\s]*?)["']""", re.I)


def page_sample(url: str, *, allow_private: bool = False) -> PageSample:
    """A trimmed copy of the page (no scripts or styles) and API-looking URLs from it."""
    host = urlsplit(url).hostname or ""
    fetch = Fetcher(site_domain(host), allow_private=allow_private)
    try:
        page = fetch.get(url)
    finally:
        fetch.close()
    hints = list(dict.fromkeys(urljoin(str(page.url), m) for m in _API_HINT.findall(page.text)))
    soup = BeautifulSoup(page.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "head"]):
        tag.decompose()
    body = soup.body or soup
    for tag in body.find_all(True):
        if isinstance(tag, Tag):
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in ("class", "id", "href")}
    excerpt = re.sub(r"\s+", " ", str(body))[:EXCERPT_CHARS]
    return PageSample(url=str(page.url), excerpt=excerpt, api_hints=hints[:15])
