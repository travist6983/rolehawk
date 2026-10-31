"""Shared normalization helpers: HTML to text, remote detection, salaries, dedupe keys."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime
from html.parser import HTMLParser

MAX_DESCRIPTION_CHARS = 50_000

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = max(self._skip - 1, 0)
        elif tag in _BLOCK_TAGS and tag != "li":  # the next <li> starts its own line
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(markup: str | None) -> str:
    """Readable plain text from job description HTML (entity-escaped HTML too)."""
    if not markup:
        return ""
    if "&lt;" in markup and "<" not in markup:
        markup = html.unescape(markup)  # Greenhouse/RSS double-encode
    parser = _TextExtractor()
    parser.feed(markup)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_DESCRIPTION_CHARS]


_REMOTE = re.compile(r"\b(remote|anywhere|work from home|wfh|distributed)\b", re.IGNORECASE)


def looks_remote(*texts: str | None) -> bool | None:
    joined = " ".join(t for t in texts if t)
    if not joined:
        return None
    return True if _REMOTE.search(joined) else None


def money(amount: float | int | str | None) -> str | None:
    if amount is None:
        return None
    try:
        value = float(amount)
    except ValueError:
        return None
    if value <= 0:
        return None
    return f"{value:,.0f}"


def salary_range(
    low: float | int | str | None,
    high: float | int | str | None,
    currency: str | None = None,
    period: str | None = None,
) -> str | None:
    lo, hi = money(low), money(high)
    if not lo and not hi:
        return None
    amount = f"{lo}-{hi}" if lo and hi and lo != hi else (lo or hi or "")
    parts = [currency.upper() if currency else None, amount, f"per {period}" if period else None]
    return " ".join(p for p in parts if p)


def parse_datetime(value: object) -> datetime | None:
    """ISO strings, dates, epoch seconds or milliseconds, and RFC 822 (RSS) dates."""
    if value in (None, "", 0):
        return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 10**11 else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        import email.utils

        try:
            parsed = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def norm(text: str | None) -> str:
    value = re.sub(r"[^\w\s]", " ", (text or "").casefold())
    value = re.sub(r"\b(inc|ltd|llc|gmbh|corp|corporation|co|plc|limited)\b", " ", value)
    return " ".join(value.split())


def job_hash(company: str, title: str, location: str | None) -> str:
    """Cross-source dedupe key from normalized company + title + location."""
    key = "|".join([norm(company), norm(title), norm(location)])
    return hashlib.sha256(key.encode()).hexdigest()
