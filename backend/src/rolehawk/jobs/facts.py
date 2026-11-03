"""Quick facts about a job, read from the posting with no AI: where the work happens, the
years of experience it asks for, and which of the user's skills it names. Discover shows
them before a job is ranked, so the user can sort a long list for free.

Only short skills are looked for ("React", "Node.js", "SQL Server"): phrases like "design
system governance" rarely appear word for word in a posting."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkMode = Literal["remote", "hybrid", "on-site"]

MAX_SKILL_WORDS = 3
MAX_YEARS = 25
MODE_TEXT_CHARS = 3_000  # where postings state the work arrangement

# Other ways postings write a skill (all lowercase).
_ALIASES: dict[str, tuple[str, ...]] = {
    "node.js": ("node", "nodejs"),
    "next.js": ("nextjs",),
    "vue 3": ("vue", "vue.js", "vuejs"),
    "vue": ("vue.js", "vuejs"),
    "react": ("react.js", "reactjs"),
    "postgres": ("postgresql",),
    "postgresql": ("postgres",),
    "javascript": ("js",),
    "html5": ("html",),
    "css3": ("css",),
    "github actions": ("gh actions",),
}

_HYBRID = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE = re.compile(r"\b(?:on-?site|in[- ]office|in[- ]person)\b", re.IGNORECASE)
_YEARS = re.compile(
    r"\b(\d{1,2})\s*\+?\s*(?:(?:-|to|\u2013)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b"
    r"(?=[^.\n]{0,60}\bexperience\b)",
    re.IGNORECASE,
)


class JobFacts(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    work_mode: WorkMode | None = Field(
        default=None, description="Remote, hybrid, or on-site, when the posting says"
    )
    years: int | None = Field(
        default=None, description="The most years of experience the posting asks for"
    )
    skills: list[str] = Field(
        default_factory=list, description="The user's skills the posting names, profile order"
    )


def _pattern(term: str) -> str:
    # Word edges that also work for "C#", ".NET", and "Node.js".
    return rf"(?<![\w.#+]){re.escape(term)}(?![\w#+]|\.\w)"


class SkillFinder:
    """Finds the user's short skills in posting text. Build once per listing."""

    def __init__(self, skills: Sequence[str]) -> None:
        self._skills: list[tuple[str, tuple[str, ...], re.Pattern[str]]] = []
        for skill in skills:
            name = skill.strip()
            words = name.split()
            if not name or len(words) > MAX_SKILL_WORDS or words[0][0].isdigit():
                continue
            terms = (name.lower(), *_ALIASES.get(name.lower(), ()))
            regex = re.compile("|".join(_pattern(t) for t in terms), re.IGNORECASE)
            self._skills.append((name, terms, regex))

    def find(self, text: str) -> list[str]:
        lower = text.lower()
        # The substring check is cheap and rules out most skills before the regex runs.
        return [
            name
            for name, terms, regex in self._skills
            if any(t in lower for t in terms) and regex.search(text)
        ]


def work_mode(
    title: str, location: str | None, remote: bool | None, description: str
) -> WorkMode | None:
    where = f"{title} {location or ''}"
    if _HYBRID.search(where):
        return "hybrid"
    if remote:
        return "remote"
    head = description[:MODE_TEXT_CHARS]
    if _HYBRID.search(head):
        return "hybrid"
    if _ONSITE.search(where) or _ONSITE.search(head):
        return "on-site"
    return None


def years_asked(description: str) -> int | None:
    """The largest "N years ... experience" in the posting (its headline requirement)."""
    found = [int(m.group(1)) for m in _YEARS.finditer(description)]
    plausible = [n for n in found if 0 < n <= MAX_YEARS]
    return max(plausible) if plausible else None


def job_facts(
    finder: SkillFinder,
    *,
    title: str,
    location: str | None,
    remote: bool | None,
    description: str,
) -> JobFacts:
    return JobFacts(
        work_mode=work_mode(title, location, remote, description),
        years=years_asked(description),
        skills=finder.find(f"{title}\n{description}"),
    )
