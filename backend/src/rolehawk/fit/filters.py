"""Hard filters run before any AI scoring, so Claude only sees jobs that could work.

Status filters (dismissed, already applied, already ranked) are SQL. Preference filters
(country, location and remote, salary floor, excluded words) need text parsing, so they run
in Python over the SQL result, and each rejection is counted so the user sees why jobs were
skipped."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.orm import Session

from rolehawk import geo
from rolehawk.db.models import Application, Job, JobScore, RemotePolicy, SearchTarget
from rolehawk.db.types import utcnow
from rolehawk.portals.text import looks_remote
from rolehawk.profile.model import Preferences, SalaryFloor, SalaryPeriod

HOURS_PER_YEAR = 2080

# Why the preference filters skip a job, in the order they're checked.
SkipReason = Literal["excluded", "country", "location", "salary"]


class FilterCounts(BaseModel):
    """Jobs skipped before scoring, by reason."""

    already_ranked: int = 0
    applied: int = 0
    dismissed: int = 0
    closed: int = 0  # the deadline has passed
    country: int = 0
    location: int = 0
    salary: int = 0
    excluded: int = 0

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


@dataclass(frozen=True)
class TargetRule:
    country: str
    remote_only: bool
    onsite: bool
    places: tuple[str, ...]  # the folded city of each location ("denver", "sterling heights")
    exclude: tuple[re.Pattern[str], ...]
    regions: frozenset[str] = frozenset()  # states/provinces the locations name ("US-MI")


@dataclass
class Rules:
    targets: list[TargetRule] = field(default_factory=list)
    exclude: list[re.Pattern[str]] = field(default_factory=list)  # from deal breakers
    floor_per_year: float | None = None
    floor_currency: str | None = None


_NEGATION = re.compile(r"^(?:no|not|never|avoid)\s+", re.IGNORECASE)
MAX_DEAL_BREAKER_WORDS = 3


def deal_breaker_terms(deal_breakers: Sequence[str]) -> list[str]:
    """Short deal breakers double as excluded words ("no crypto" -> "crypto"). Longer ones
    ("nothing that needs weekly travel") are left to the AI scorer."""
    terms: list[str] = []
    for item in deal_breakers:
        term = _NEGATION.sub("", item.strip()).strip(" .;")
        if term and len(term.split()) <= MAX_DEAL_BREAKER_WORDS:
            terms.append(term)
    return terms


def _word(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term.strip())}(?!\w)", re.IGNORECASE)


def build_rules(targets: Sequence[SearchTarget], prefs: Preferences) -> Rules:
    rules = Rules()
    for t in targets:
        rules.targets.append(
            TargetRule(
                country=(t.country or "").upper(),
                remote_only=t.remote_policy is RemotePolicy.REMOTE,
                onsite=t.remote_policy is RemotePolicy.ONSITE,
                places=tuple(city for p in t.locations or () if (city := geo.city_part(p))),
                exclude=tuple(_word(x) for x in t.exclude or () if x.strip()),
                regions=frozenset[str]().union(
                    *(geo.place_subdivisions(p) for p in t.locations or ())
                ),
            )
        )
    rules.exclude = [_word(term) for term in deal_breaker_terms(prefs.deal_breakers)]
    if prefs.salary_floor is not None:
        rules.floor_per_year = per_year(prefs.salary_floor)
        rules.floor_currency = prefs.salary_floor.currency.upper()
    return rules


def load_rules(session: Session, prefs: Preferences) -> Rules:
    """Rules from the active search targets and the preferences."""
    active = select(SearchTarget).where(SearchTarget.active.is_(True))
    return build_rules(list(session.scalars(active)), prefs)


def per_year(floor: SalaryFloor) -> float:
    if floor.period is SalaryPeriod.MONTH:
        return floor.amount * 12
    if floor.period is SalaryPeriod.HOUR:
        return floor.amount * HOURS_PER_YEAR
    return float(floor.amount)


# --- salary text --------------------------------------------------------------------------

_AMOUNT = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([km])?\b", re.IGNORECASE)
_NOT_YEARLY = re.compile(r"\b(hour|hourly|hr|day|daily|week|weekly|month|monthly)\b", re.I)
_CODES = ("USD", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF", "SGD", "INR", "JPY", "SEK", "PLN")
_DOLLAR_CURRENCIES = {"USD", "CAD", "AUD", "NZD", "SGD"}


def salary_max(text: str | None, currency: str) -> float | None:
    """The top of a yearly salary range, when it's clearly in `currency`; otherwise None
    (unknown never filters a job out)."""
    if not text or _NOT_YEARLY.search(text):
        return None
    upper = text.upper()
    codes = [c for c in _CODES if re.search(rf"\b{c}\b", upper)]
    if codes:
        if codes != [currency]:
            return None
    elif "€" in text:
        if currency != "EUR":
            return None
    elif "£" in text:
        if currency != "GBP":
            return None
    elif "$" in text and currency not in _DOLLAR_CURRENCIES:
        return None
    amounts: list[float] = []
    for number, suffix in _AMOUNT.findall(text):
        value = float(number.replace(",", ""))
        if suffix.lower() == "k":
            value *= 1_000
        elif suffix.lower() == "m":
            value *= 1_000_000
        if value >= 1_000:  # skip "3 years", "401k"-style noise below a plausible salary
            amounts.append(value)
    return max(amounts) if amounts else None


# --- per-job checks -----------------------------------------------------------------------


def _is_remote(job: Job) -> bool:
    return job.remote is True or looks_remote(job.location, job.title) is True


def country_ok(job: Job, rules: Rules) -> bool:
    """Drops jobs whose location names only other countries ("Remote - India" for a US
    search). Unknown or worldwide locations pass, and so does a job in any target's country."""
    countries = {t.country for t in rules.targets if t.country}
    if not countries:
        return True
    places = geo.detect(job.location)
    return any(places.allows(c) for c in countries)


def location_ok(job: Job, rules: Rules) -> bool:
    """Passes if any search target accepts it: remote (unless the target is on-site only),
    in one of its cities, or in the same state or province as one. Locations that name no
    state or known city ("United States", "Troy, Oakland County", "N/A") pass too: there's
    nothing to check, and the AI scorer weighs the commute."""
    if not rules.targets:
        return True
    remote = _is_remote(job)
    where = f" {geo.fold(job.location)} " if job.location else ""
    places = geo.detect(job.location)
    for target in rules.targets:
        if target.remote_only:
            if remote:
                return True
            continue
        if not target.places or not where:
            return True
        if remote and not target.onsite:
            return True
        if any(f" {place} " in where for place in target.places):
            return True
        if target.regions & places.subdivisions:
            return True
        if not places.local and not remote:
            return True
    return False


def excluded(job: Job, rules: Rules) -> bool:
    """Excluded words (deal breakers, per-target excludes) in the title or company name.
    Descriptions aren't checked: "no Java" shouldn't drop every posting that mentions Java."""
    text = f"{job.title} {job.company}"
    patterns = [*rules.exclude, *(p for t in rules.targets for p in t.exclude)]
    return any(p.search(text) for p in patterns)


def salary_ok(job: Job, rules: Rules) -> bool:
    if rules.floor_per_year is None or rules.floor_currency is None:
        return True
    top = salary_max(job.salary_text, rules.floor_currency)
    return top is None or top >= rules.floor_per_year


def skip_reason(job: Job, rules: Rules) -> SkipReason | None:
    """Why the preference filters skip this job, or None when it could work."""
    if excluded(job, rules):
        return "excluded"
    if not country_ok(job, rules):
        return "country"
    if not location_ok(job, rules):
        return "location"
    if not salary_ok(job, rules):
        return "salary"
    return None


# --- the candidate query ------------------------------------------------------------------


def _status_counts(session: Session, base: Select[Job], rescore: bool) -> FilterCounts:
    def count(stmt: Select[Job]) -> int:
        ids = stmt.with_only_columns(Job.id).subquery()
        return session.scalar(select(func.count()).select_from(ids)) or 0

    applied = exists().where(Application.job_id == Job.id)
    scored = exists().where(JobScore.job_id == Job.id)
    live = Job.dismissed_at.is_(None)
    return FilterCounts(
        dismissed=count(base.where(Job.dismissed_at.is_not(None))),
        applied=count(base.where(live, applied)),
        closed=count(base.where(live, ~applied, ~_open())),
        already_ranked=0 if rescore else count(base.where(live, ~applied, _open(), scored)),
    )


def _open() -> ColumnElement[bool]:
    """No deadline, or one that hasn't passed."""
    return or_(Job.closes_at.is_(None), Job.closes_at >= utcnow().date())


def candidates(
    session: Session,
    rules: Rules,
    *,
    job_ids: Sequence[int] | None = None,
    rescore: bool = False,
    limit: int | None = None,
) -> tuple[list[Job], FilterCounts]:
    """Jobs worth scoring, newest first, and how many were filtered out for each reason."""
    base = select(Job)
    if job_ids is not None:
        base = base.where(Job.id.in_(job_ids))
    counts = _status_counts(session, base, rescore)

    stmt = base.where(
        Job.dismissed_at.is_(None), ~exists().where(Application.job_id == Job.id), _open()
    ).order_by(Job.scraped_at.desc(), Job.id.desc())
    if not rescore:
        stmt = stmt.where(~exists().where(JobScore.job_id == Job.id))

    kept: list[Job] = []
    for job in session.scalars(stmt):
        reason = skip_reason(job, rules)
        if reason is None:
            kept.append(job)
        else:
            setattr(counts, reason, getattr(counts, reason) + 1)
    if limit is not None:
        kept = kept[:limit]
    return kept, counts
