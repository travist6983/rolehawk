"""Shared normalization helpers: HTML to text, remote detection, salaries, dedupe keys."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime

from offerbound.portals.integrity import clean_posting


def html_to_text(markup: str | None) -> str:
    """Readable plain text from HTML (entity-escaped HTML too), with hidden elements and
    invisible characters removed (portals/integrity.py). Descriptions use clean_posting()
    directly so what was removed is reported."""
    return clean_posting(markup).text


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


def parse_date(value: object) -> date | None:
    """An application deadline from a source or a model: ISO dates or datetimes, epoch
    times, RFC 822. Free text ("ASAP", "rolling") and implausible years are None, never a
    guess (a wrong deadline would hide an open job)."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        moment = parse_datetime(value)
        if moment is None:
            return None
        parsed = moment.date()
    return parsed if 2000 <= parsed.year <= 2100 else None


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
