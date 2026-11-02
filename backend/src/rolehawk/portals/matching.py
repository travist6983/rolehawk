"""Keep only jobs that fit a search target, so whole-company and whole-market sources don't
flood the database. /rank does the fine-grained scoring, but the match is still strict:

- The job title has every word of the target, after dropping level words and folding
  spellings together ("Front-End Developer" = "Frontend Engineer").
- The target's role word is the role the job names: the last word of a part of the title
  ("Java Developer - Security" is a developer; "Developer Advocate" is an advocate).
- A target that names a role but no field keeps the word as written: "Senior Developer"
  matches developers, not every Controls, Data, and Security Engineer. It also skips other
  trades that share the word ("Technical Curriculum Developer").
- The target's words can't come from a part of the title that names a different job:
  "Full-Stack BI Architect / Data Engineer" isn't a full-stack engineer.
- The job's location doesn't name only other countries than the target's ("Bengaluru, India"
  for a US search). Unknown and worldwide locations pass.

Keywords on a target widen it: any job with all of a keyword's words matches."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from rolehawk import geo
from rolehawk.portals.base import SearchQuery
from rolehawk.portals.text import norm

# Words that change level, not role: "Senior Data Analyst" still matches "Data Analyst".
_IGNORED = {
    "senior", "sr", "junior", "jr", "lead", "staff", "principal", "head", "associate",
    "intern", "i", "ii", "iii", "iv", "v", "1", "2", "3", "the", "of", "and", "a", "an",
    "for", "to", "in", "at", "with", "remote", "hybrid", "f", "m", "d", "w",
}  # fmt: skip
# Words that can trail a role without naming a new one ("Frontend Engineer Contract"); so can
# all-caps regions and codes ("Account Executive DACH").
_TRAILING = {
    "contract", "contractor", "freelance", "freelancer", "temporary", "temp", "full", "part",
    "time", "fulltime", "parttime", "permanent", "onsite", "new", "grad", "graduate",
    "us", "usa", "uk", "eu", "emea", "apac", "latam", "nyc", "sf",
}  # fmt: skip
# All-caps words that name a field rather than a region, so they're never skipped:
# "Developer API" is about an API, not a developer.
_FIELD_CODES = {
    "api", "apis", "sdk", "sdks", "ui", "ux", "qa", "ai", "ml", "bi", "sre", "etl", "crm",
    "erp", "sql", "cms", "ios", "aws", "gcp", "it", "hr", "seo", "gis", "llm", "nlp", "ar",
    "vr", "xr", "dba", "rpa", "plc", "gpu", "rf",
}  # fmt: skip
_COMPOUNDS = [
    (r"\bfront end\b", "frontend"),
    (r"\bback end\b", "backend"),
    (r"\bfull stack\b", "fullstack"),
    (r"\bdev ops\b", "devops"),
    (r"\bmachine learning\b", "ml"),
    (r"\bsoftware developer\b", "software engineer"),
    (r"\bdeveloper\b", "engineer"),
]
# Where a title splits into parts: "Engineer, Frontend (React) - Remote | Berlin @ Acme".
# A hyphen splits only with spaces around it ("Full-Stack" stays one part); en/em dashes always.
_PARTS = re.compile(r"(\s-\s|\sat\s|[,()\[\]/|:;@\u2013\u2014])", re.IGNORECASE)


def _written(text: str) -> list[str]:
    # Singular ("Developers" -> "developer"), so the compounds see one form.
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in norm(text).split()]


def _folded(text: str) -> list[str]:
    value = " ".join(_written(text))
    for pattern, replacement in _COMPOUNDS:
        value = re.sub(pattern, replacement, value)
    return value.split()


def tokens(text: str) -> set[str]:
    return {w for w in _folded(text) if w not in _IGNORED}


# Words that name a job. A part of a title headed by one names that job, so the target's other
# words can't come from it unless it's the target's role.
_ROLES = set(
    _written(
        "engineer developer architect analyst manager designer scientist advocate writer"
        " copywriter consultant administrator admin specialist director recruiter technician"
        " programmer tester representative executive coordinator officer strategist researcher"
        " editor marketer accountant owner counsel attorney instructor trainer evangelist"
        " producer operator agent assistant generalist auditor planner"
    )
)
# Words in front of a bare role that make it another trade: a curriculum developer doesn't
# write software, so "Senior Developer" skips them. Targets that name the word still match.
_OTHER_TRADES = set(
    _written(
        "curriculum course courseware content instructional training learning elearning"
        " business estate property community talent leadership organizational"
    )
)


def _droppable(word: str) -> bool:
    folded = word.casefold()
    if folded in _IGNORED or folded in _TRAILING:
        return True
    return len(word) > 1 and word.isupper() and folded not in _FIELD_CODES


def _core(part: str) -> str:
    """A title part without trailing words that don't name a role: level words, employment
    type, and all-caps regions or codes ("Account Executive DACH" -> "Account Executive")."""
    words = re.findall(r"\w+", part)
    while len(words) > 1 and _droppable(words[-1]) and tokens(" ".join(words[:-1])):
        words.pop()
    return " ".join(words)


def _kept(part: str, folded: bool) -> list[str]:
    core = _core(part)
    return [w for w in (_folded(core) if folded else _written(core)) if w not in _IGNORED]


def _head(part: str, folded: bool) -> str | None:
    kept = _kept(part, folded)
    return kept[-1] if kept else None


@dataclass(frozen=True)
class _Part:
    words: frozenset[str]  # written and folded
    heads: frozenset[str]  # the role it names (its last word), written and folded
    trade: str | None  # the written word before that role ("curriculum" developer)


def _parts(title: str) -> list[_Part]:
    pieces = _PARTS.split(title)  # text, separator, text, separator, ..., text
    parts: list[_Part] = []
    after_role = False
    for index in range(0, len(pieces), 2):
        text = pieces[index]
        if not tokens(text):
            continue
        written = _kept(text, folded=False)
        heads = {h for folded in (False, True) if (h := _head(text, folded))}
        separator = pieces[index - 1].strip() if index else ""
        if separator == "," and after_role and len(written) == 1 and heads & _ROLES:
            # "Copywriter, Developer": who the copywriter writes for, not a second job.
            heads = set()
        parts.append(
            _Part(
                words=frozenset(_folded(text)) | frozenset(_written(text)),
                heads=frozenset(heads),
                trade=written[-2] if len(written) > 1 else None,
            )
        )
        after_role = bool(heads & _ROLES)
    return parts


@dataclass(frozen=True)
class Wanted:
    words: frozenset[str]
    role: str
    bare: bool = False  # a role with no field ("Senior Developer")


def wanted(title: str) -> Wanted | None:
    """What a job title needs to match the target `title`, or None if it names nothing."""
    words = tokens(title)
    written = {w for w in _written(title) if w not in _IGNORED}
    bare = len(words) == 1 and len(written) == 1
    if bare:
        words = written
    first = next((p for p in _PARTS.split(title) if tokens(p)), "")
    role = _head(first, folded=not bare)
    return Wanted(frozenset(words), role, bare) if words and role else None


def _fits(need: Wanted, parts: list[_Part]) -> bool:
    roles = [
        p
        for p in parts
        if need.role in p.heads and not (need.bare and p.trade in _OTHER_TRADES - need.words)
    ]
    if not roles:
        return False
    pool: set[str] = set()
    for part in parts:
        if part in roles or not part.heads & _ROLES:
            pool |= part.words
    return need.words <= pool


def title_matches(title: str, queries: Iterable[SearchQuery]) -> bool:
    parts = _parts(title)
    folded = tokens(title)
    for query in queries:
        need = wanted(query.title)
        if need and _fits(need, parts):
            return True
        if any(tokens(k) and tokens(k) <= folded for k in query.keywords):
            return True
    return False


def job_matches(title: str, location: str | None, queries: Iterable[SearchQuery]) -> bool:
    """The title matches a target, and the location could be in that target's country."""
    places = geo.detect(location)
    return title_matches(title, [q for q in queries if places.allows(q.country)])
