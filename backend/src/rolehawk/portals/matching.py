"""Keep only jobs whose title fits a search target, so whole-company and whole-market sources
don't flood the database. /rank does the fine-grained scoring, but the match is still strict:

- The job title has every word of the target, after dropping level words and folding
  spellings together ("Front-End Developer" = "Frontend Engineer").
- The target's role word is the role the job names: the last word of a part of the title
  ("Java Developer - Security" is a developer; "Developer Advocate" is an advocate).
- A target that names a role but no field keeps the word as written: "Senior Developer"
  matches developers, not every Controls, Data, and Security Engineer.

Keywords on a target widen it: any job with all of a keyword's words matches."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

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
_PARTS = re.compile(r"\s-\s|\sat\s|[,()\[\]/|:;@\u2013\u2014]", re.IGNORECASE)


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


def _droppable(word: str) -> bool:
    folded = word.casefold()
    return folded in _IGNORED or folded in _TRAILING or (len(word) > 1 and word.isupper())


def _core(part: str) -> str:
    """A title part without trailing words that don't name a role: level words, employment
    type, and all-caps regions or codes ("Account Executive DACH" -> "Account Executive")."""
    words = re.findall(r"\w+", part)
    while len(words) > 1 and _droppable(words[-1]) and tokens(" ".join(words[:-1])):
        words.pop()
    return " ".join(words)


def _head(part: str, folded: bool) -> str | None:
    core = _core(part)
    kept = [w for w in (_folded(core) if folded else _written(core)) if w not in _IGNORED]
    return kept[-1] if kept else None


def _heads(title: str) -> set[str]:
    """The role each part of a title names (its last word), written and folded."""
    found = set()
    for part in _PARTS.split(title):
        for folded in (False, True):
            if head := _head(part, folded):
                found.add(head)
    return found


@dataclass(frozen=True)
class Wanted:
    words: frozenset[str]
    role: str


def wanted(title: str) -> Wanted | None:
    """What a job title needs to match the target `title`, or None if it names nothing."""
    words = tokens(title)
    written = {w for w in _written(title) if w not in _IGNORED}
    bare = len(words) == 1 and len(written) == 1  # a role with no field
    if bare:
        words = written
    first = next((p for p in _PARTS.split(title) if tokens(p)), "")
    role = _head(first, folded=not bare)
    return Wanted(frozenset(words), role) if words and role else None


def title_matches(title: str, queries: Iterable[SearchQuery]) -> bool:
    folded = tokens(title)
    words = folded | set(_written(title))
    heads = _heads(title)
    for query in queries:
        need = wanted(query.title)
        if need and need.words <= words and need.role in heads:
            return True
        if any(tokens(k) and tokens(k) <= folded for k in query.keywords):
            return True
    return False
