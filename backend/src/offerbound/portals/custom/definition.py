"""A custom job source, as data. /add-portal produces one of these (by detection, or Claude
proposes it); Offerbound's engine runs it. Nothing in a definition is executable."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Sequence
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,40}$"
_PATH = r"^[A-Za-z0-9_$@\-]+(\.[A-Za-z0-9_$@\-]+)*$"  # dot path: data.jobs, location.name


class UnsafeUrlError(ValueError):
    pass


CompanyInTitle = Literal["none", "prefix_colon", "suffix_comma", "suffix_at"]
_SPLITS: dict[str, tuple[str, bool]] = {  # separator, company comes first
    "prefix_colon": (": ", True),
    "suffix_comma": (", ", False),
    "suffix_at": (" at ", False),
}
_MAX_COMPANY = 80


def split_company(title: str, how: CompanyInTitle | None) -> tuple[str | None, str]:
    """(company, title) for feed titles like "Acme: Analyst", "Analyst, Acme" or
    "Analyst at Acme". (None, title) when the title doesn't follow the pattern."""
    if how is None or how == "none":
        return None, title
    sep, company_first = _SPLITS[how]
    if company_first:
        company, found, rest = title.partition(sep)
    else:
        rest, found, company = title.rpartition(sep)
    company, rest = company.strip(), rest.strip()
    if not found or not company or not rest or len(company) > _MAX_COMPANY:
        return None, title
    return company, rest


def guess_company_in_title(titles: Sequence[str]) -> CompanyInTitle:
    """The pattern at least 80% of the titles follow, most specific first, or "none"."""
    if len(titles) < 3:
        return "none"
    for how in ("prefix_colon", "suffix_at", "suffix_comma"):
        if sum(1 for t in titles if split_company(t, how)[0]) >= 0.8 * len(titles):
            return how
    return "none"


def _http_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("must be an http(s) URL")
    if parts.username or parts.password:
        raise ValueError("URLs with credentials aren't allowed")
    return value.strip()


def site_domain(host: str) -> str:
    """The domain a source may fetch from: its host's last two labels (example.com), or the
    address itself for an IP host."""
    host = host.lower().rstrip(".").strip("[]")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        return ".".join(labels[-2:]) if len(labels) >= 2 else host
    return host


def check_url(url: str, domain: str, *, allow_private: bool = False) -> None:
    """Refuse URLs outside the source's domain, and any host that resolves to a private,
    loopback, or link-local address (the user's own machine and network)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        raise UnsafeUrlError(f"not a web URL: {url}")
    if host != domain and not host.endswith("." + domain):
        raise UnsafeUrlError(f"{host} is outside {domain}")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"can't resolve {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise UnsafeUrlError(f"{host} points to a private address")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_PATTERN, description="lowercase-with-dashes")
    name: str = Field(min_length=1, max_length=80)
    source_url: str = Field(description="The page the user pasted")
    company: str | None = Field(
        default=None, max_length=120, description="When every job is at one company"
    )

    @field_validator("source_url")
    @classmethod
    def _source(cls, value: str) -> str:
        return _http_url(value)

    @property
    def domain(self) -> str:
        return site_domain(urlsplit(self.source_url).hostname or "")


class RssDefinition(_Base):
    kind: Literal["rss"] = "rss"
    feed_url: str
    company_in_title: CompanyInTitle | None = Field(
        default=None,
        description='Titles carry the company: "Acme: Analyst" (prefix_colon), "Analyst, Acme"'
        ' (suffix_comma), "Analyst at Acme" (suffix_at), or not at all (none). Unset means'
        " the test run guesses it from the feed.",
    )

    @field_validator("feed_url")
    @classmethod
    def _feed(cls, value: str) -> str:
        return _http_url(value)


class JsonLdDefinition(_Base):
    """JobPosting structured data, on the page itself or on job pages it links to."""

    kind: Literal["jsonld"] = "jsonld"
    list_url: str
    link_pattern: str | None = Field(
        default=None,
        max_length=200,
        description="Regex that job page links match (e.g. /jobs/\\d+); unset: data on the page",
    )
    max_pages: int = Field(default=40, ge=1, le=100)

    @field_validator("list_url")
    @classmethod
    def _list(cls, value: str) -> str:
        return _http_url(value)

    @field_validator("link_pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        if value:
            re.compile(value)
        return value


class FieldMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(pattern=_PATH)
    url: str = Field(pattern=_PATH)
    id: str | None = Field(default=None, pattern=_PATH)
    company: str | None = Field(default=None, pattern=_PATH)
    location: str | None = Field(default=None, pattern=_PATH)
    description: str | None = Field(default=None, pattern=_PATH)
    posted_at: str | None = Field(default=None, pattern=_PATH)


class JsonApiDefinition(_Base):
    kind: Literal["json_api"] = "json_api"
    api_url: str = Field(description="May contain {page}; GET only")
    items_path: str = Field(
        default="", pattern=r"^(|" + _PATH[1:-1] + r")$", description="Dot path to the list"
    )
    fields: FieldMap
    url_prefix: str | None = Field(default=None, description="For relative job links")
    pages: int = Field(default=1, ge=1, le=10)

    @field_validator("api_url", "url_prefix")
    @classmethod
    def _urls(cls, value: str | None) -> str | None:
        if value is not None:
            _http_url(value.replace("{page}", "1"))
        return value


class HtmlFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=200, description="CSS selector inside the item")
    link: str | None = Field(
        default=None, max_length=200, description="CSS selector; default: the title's link"
    )
    location: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)


class HtmlDefinition(_Base):
    kind: Literal["html"] = "html"
    list_url: str
    item_selector: str = Field(max_length=200, description="CSS selector for one job")
    fields: HtmlFields

    @field_validator("list_url")
    @classmethod
    def _list(cls, value: str) -> str:
        return _http_url(value)


PortalDefinition = Annotated[
    RssDefinition | JsonLdDefinition | JsonApiDefinition | HtmlDefinition,
    Field(discriminator="kind"),
]


class DefinitionEnvelope(BaseModel):
    """Wrapper so a definition can be validated from plain data."""

    definition: PortalDefinition
