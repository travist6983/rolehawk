"""Per-country defaults from data/country_sources.toml (feeds, currency, salary period)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ENV_DATA_DIR = "ROLEHAWK_DATA_DIR"
FALLBACK = "*"

COUNTRY_NAMES = {
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "DE": "Germany",
    "IN": "India",
}


@dataclass(frozen=True)
class CountryDefaults:
    code: str
    feeds: tuple[str, ...]
    currency: str
    salary_period: str


def data_dir() -> Path:
    """Bundled data (release wheel) or the repo's data/ folder (source checkout)."""
    if override := os.environ.get(ENV_DATA_DIR):
        return Path(override)
    here = Path(__file__).resolve()
    bundled = here.parent / "data"
    return bundled if bundled.is_dir() else here.parents[3] / "data"


@cache
def _table() -> dict[str, dict[str, object]]:
    path = data_dir() / "country_sources.toml"
    if not path.is_file():
        return {FALLBACK: {"feeds": [], "currency": "USD", "salary_period": "year"}}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def defaults_for(country: str | None) -> CountryDefaults:
    table = _table()
    code = (country or "").upper()
    row = table.get(code) or table.get(FALLBACK) or {}
    feeds = row.get("feeds", [])
    return CountryDefaults(
        code=code or FALLBACK,
        feeds=tuple(str(f) for f in feeds) if isinstance(feeds, list) else (),
        currency=str(row.get("currency", "USD")),
        salary_period=str(row.get("salary_period", "year")),
    )


def known_countries() -> list[tuple[str, str]]:
    """(code, name) for countries with tuned defaults, for pickers."""
    return [(code, COUNTRY_NAMES.get(code, code)) for code in sorted(_table()) if code != FALLBACK]
