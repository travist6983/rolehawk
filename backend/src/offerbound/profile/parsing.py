"""Small deterministic parsers for interview answers and imports: dates, ranges, salaries."""

from __future__ import annotations

import re
from dataclasses import dataclass

from offerbound.profile.model import SalaryFloor, SalaryPeriod

_MONTHS = {
    name: index
    for index, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
_CURRENT_WORDS = {"present", "current", "now", "today", "ongoing"}


def parse_date(text: str | None) -> str | None:
    """Normalize a date to YYYY-MM or YYYY. Returns None when it can't be read."""
    if not text:
        return None
    value = text.strip().lower().rstrip(".")
    if match := re.fullmatch(r"(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?", value):
        year, month = int(match.group(1)), int(match.group(2))
    elif match := re.fullmatch(r"(\d{1,2})[-/.](\d{4})", value):
        month, year = int(match.group(1)), int(match.group(2))
    elif match := re.fullmatch(r"([a-z]+)\.?,?\s+(\d{4})", value):
        month, year = _MONTHS.get(match.group(1), 0), int(match.group(2))
        if not month:
            return None
    elif match := re.fullmatch(r"(\d{4})", value):
        return match.group(1)
    else:
        return None
    if not 1 <= month <= 12 or not 1900 <= year <= 2100:
        return None
    return f"{year:04d}-{month:02d}"


@dataclass(frozen=True)
class DateRange:
    start: str | None
    end: str | None
    current: bool


def parse_date_range(text: str | None) -> DateRange | None:
    """Parse "Mar 2020 - Present", "2019 to 2021", "2019-2021", "2020-03 - 2024-06" (en/em
    dashes too), "since 2022", or a single date."""
    if not text or not text.strip():
        return None
    value = re.sub(r"\s*[\u2013\u2014]\s*", " - ", text.strip())  # en/em dash -> " - "
    if since := re.fullmatch(r"since\s+(.+)", value, flags=re.IGNORECASE):
        start = parse_date(since.group(1))
        return DateRange(start, None, True) if start else None
    # A bare hyphen between years ("2019-2021") is a range; inside ISO dates it is not.
    if years := re.fullmatch(r"(\d{4})\s*-\s*(\d{4}|[a-z]+)", value, flags=re.IGNORECASE):
        value = f"{years.group(1)} - {years.group(2)}"
    parts = re.split(r"\s+(?:-|to|until|through)\s+", value, flags=re.IGNORECASE)
    if len(parts) == 1:
        single = parse_date(parts[0])
        return DateRange(single, single, False) if single else None
    if len(parts) != 2:
        return None
    start = parse_date(parts[0])
    if start is None:
        return None
    if parts[1].strip().lower() in _CURRENT_WORDS:
        return DateRange(start, None, True)
    end = parse_date(parts[1])
    return DateRange(start, end, False) if end else None


def format_date_range(start: str | None, end: str | None, current: bool) -> str | None:
    if not start and not end:
        return None
    return f"{start or '?'} to {'present' if current else (end or '?')}"


_CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "¥": "JPY"}
_PERIODS = {
    "hour": SalaryPeriod.HOUR,
    "hr": SalaryPeriod.HOUR,
    "hourly": SalaryPeriod.HOUR,
    "month": SalaryPeriod.MONTH,
    "mo": SalaryPeriod.MONTH,
    "monthly": SalaryPeriod.MONTH,
    "year": SalaryPeriod.YEAR,
    "yr": SalaryPeriod.YEAR,
    "annual": SalaryPeriod.YEAR,
    "annually": SalaryPeriod.YEAR,
}


def parse_salary(text: str | None, default_currency: str = "USD") -> SalaryFloor | None:
    """Parse "$120k", "120,000 USD", "£90k per year", "60/hour", "8.5k EUR a month"."""
    if not text:
        return None
    value = text.strip().lower()
    number = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([km])?\b", value)
    if not number:
        return None
    amount = float(number.group(1).replace(",", ""))
    multiplier = {"k": 1_000, "m": 1_000_000}.get(number.group(2) or "", 1)
    currency = next((code for sym, code in _CURRENCY_SYMBOLS.items() if sym in text), None)
    code = re.search(r"\b(usd|gbp|eur|cad|aud|inr|jpy|chf)\b", value)
    if code:
        currency = code.group(1).upper()
    period = next(
        (p for word, p in _PERIODS.items() if re.search(rf"\b{word}\b", value)),
        SalaryPeriod.YEAR,
    )
    return SalaryFloor(
        amount=round(amount * multiplier),
        currency=currency or default_currency.upper(),
        period=period,
    )


def format_salary(floor: SalaryFloor) -> str:
    return f"{floor.amount} {floor.currency} per {floor.period.value}"


def split_list(text: str) -> list[str]:
    """Split a free-text list on newlines, semicolons, or commas; trim bullets; dedupe."""
    separators = r"\n|;" if "\n" in text or ";" in text else r","
    items = [
        re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", part).strip() for part in re.split(separators, text)
    ]
    return dedupe([item for item in items if item])


def split_places(text: str) -> list[str]:
    """Places contain commas ("Austin, TX"), so only semicolons and newlines separate them."""
    return dedupe([part.strip() for part in re.split(r"[;\n]", text) if part.strip()])


def split_lines(text: str) -> list[str]:
    """One item per line (achievements often contain commas); bullets and numbering trimmed."""
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip() for line in text.splitlines()]
    return dedupe([line for line in lines if line])


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out
