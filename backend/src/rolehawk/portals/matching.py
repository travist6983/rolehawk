"""Keep only jobs whose title fits a search target, so whole-company and whole-market sources
don't flood the database. Deliberately generous: /rank does the fine-grained scoring."""

from __future__ import annotations

import re
from collections.abc import Iterable

from rolehawk.portals.base import SearchQuery
from rolehawk.portals.text import norm

# Words that change level, not role: "Senior Data Analyst" still matches "Data Analyst".
_IGNORED = {
    "senior", "sr", "junior", "jr", "lead", "staff", "principal", "head", "associate",
    "intern", "i", "ii", "iii", "iv", "v", "1", "2", "3", "the", "of", "and", "a", "an",
    "for", "to", "in", "at", "with", "remote", "hybrid", "f", "m", "d", "w",
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


def tokens(text: str) -> set[str]:
    # Singular first ("Developers" -> "developer"), so the compounds below see one form.
    value = " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in norm(text).split())
    for pattern, replacement in _COMPOUNDS:
        value = re.sub(pattern, replacement, value)
    return {w for w in value.split() if w not in _IGNORED}


def title_matches(title: str, queries: Iterable[SearchQuery]) -> bool:
    job = tokens(title)
    for query in queries:
        wanted = tokens(query.title)
        if wanted and wanted <= job:
            return True
        if any(tokens(k) and tokens(k) <= job for k in query.keywords):
            return True
    return False
