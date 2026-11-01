"""Merge newly imported data into the existing profile so re-running /setup edits rather than
duplicates. Existing values win; imports only fill gaps and add what's new."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from offerbound.profile.model import (
    Contact,
    Education,
    Experience,
    Preferences,
    Profile,
)
from offerbound.profile.parsing import dedupe


def norm(text: str | None) -> str:
    """Comparison key: case-, punctuation-, and suffix-insensitive ("Acme, Inc." == "acme")."""
    value = re.sub(r"[^\w\s]", " ", (text or "").casefold())
    value = re.sub(r"\b(inc|ltd|llc|gmbh|corp|corporation|co|plc|limited)\b", " ", value)
    return " ".join(value.split())


_TITLE_WORDS = {
    "sr": "senior",
    "snr": "senior",
    "jr": "junior",
    "jnr": "junior",
    "mgr": "manager",
    "mngr": "manager",
    "eng": "engineer",
    "engr": "engineer",
    "dev": "developer",
    "assoc": "associate",
    "asst": "assistant",
    "dir": "director",
    "vp": "vice president",
    "svp": "senior vice president",
    "ii": "2",
    "iii": "3",
    "iv": "4",
}


def title_key(title: str | None) -> str:
    """Titles compared the way people write them: "Sr. Data Eng" == "Senior Data Engineer",
    "Analyst II" == "Analyst 2", "&" == "and"."""
    value = re.sub(r"&", " and ", (title or "").casefold())
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(_TITLE_WORDS.get(word, word) for word in value.split())


@dataclass
class MergeReport:
    added: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)

    def bump(self, bucket: dict[str, int], key: str, n: int = 1) -> None:
        if n:
            bucket[key] = bucket.get(key, 0) + n

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated)


def _fill[T](current: T | None, incoming: T | None) -> T | None:
    return current if current not in (None, "", []) else incoming


def _merge_contact(current: Contact, incoming: Contact) -> Contact:
    return Contact(
        name=_fill(current.name, incoming.name),
        email=_fill(current.email, incoming.email),
        phone=_fill(current.phone, incoming.phone),
        location=_fill(current.location, incoming.location),
        links=dedupe([*current.links, *incoming.links]),
    )


def _experience_key(exp: Experience) -> tuple[str, str]:
    return norm(exp.company), title_key(exp.title)


def _merge_experience(
    current: list[Experience], incoming: list[Experience], report: MergeReport
) -> list[Experience]:
    merged = [exp.model_copy(deep=True) for exp in current]
    index = {_experience_key(exp): exp for exp in merged}
    for new in incoming:
        existing = index.get(_experience_key(new))
        if existing is None:
            merged.append(new.model_copy(deep=True))
            index[_experience_key(new)] = merged[-1]
            report.bump(report.added, "experience")
            continue
        before = existing.model_dump()
        existing.company = _fill(existing.company, new.company)
        existing.location = _fill(existing.location, new.location)
        if not existing.start and new.start:
            existing.start, existing.end, existing.current = new.start, new.end, new.current
        existing.highlights = dedupe([*existing.highlights, *new.highlights])
        if existing.model_dump() != before:
            report.bump(report.updated, "experience")

    def recency(exp: Experience) -> tuple[int, str]:
        return (1 if exp.current else 0, exp.end or exp.start or "")

    return sorted(merged, key=recency, reverse=True)


def _merge_education(
    current: list[Education], incoming: list[Education], report: MergeReport
) -> list[Education]:
    merged = [edu.model_copy(deep=True) for edu in current]
    for new in incoming:
        match = next(
            (
                e
                for e in merged
                if norm(e.institution) == norm(new.institution)
                and (not e.degree or not new.degree or norm(e.degree) == norm(new.degree))
            ),
            None,
        )
        if match is None:
            merged.append(new.model_copy(deep=True))
            report.bump(report.added, "education")
            continue
        before = match.model_dump()
        match.degree = _fill(match.degree, new.degree)
        match.field = _fill(match.field, new.field)
        match.start = _fill(match.start, new.start)
        match.end = _fill(match.end, new.end)
        match.notes = _fill(match.notes, new.notes)
        if match.model_dump() != before:
            report.bump(report.updated, "education")
    return merged


def _union(current: list[str], incoming: list[str], report: MergeReport, key: str) -> list[str]:
    merged = dedupe([*current, *incoming])
    report.bump(report.added, key, len(merged) - len(dedupe(current)))
    return merged


def merge_profile(current: Profile, incoming: Profile) -> tuple[Profile, MergeReport]:
    report = MergeReport()
    projects = [p.model_copy(deep=True) for p in current.projects]
    for project in incoming.projects:
        if not any(norm(p.name) == norm(project.name) for p in projects):
            projects.append(project)
            report.bump(report.added, "projects")
    certifications = [c.model_copy(deep=True) for c in current.certifications]
    for cert in incoming.certifications:
        if not any(norm(c.name) == norm(cert.name) for c in certifications):
            certifications.append(cert)
            report.bump(report.added, "certifications")
    merged = Profile(
        contact=_merge_contact(current.contact, incoming.contact),
        headline=_fill(current.headline, incoming.headline),
        summary=_fill(current.summary, incoming.summary),
        experience=_merge_experience(current.experience, incoming.experience, report),
        education=_merge_education(current.education, incoming.education, report),
        skills=_union(current.skills, incoming.skills, report, "skills"),
        projects=projects,
        certifications=certifications,
        achievements=_union(current.achievements, incoming.achievements, report, "achievements"),
        languages=_union(current.languages, incoming.languages, report, "languages"),
        extra_sections={**incoming.extra_sections, **current.extra_sections},
    )
    for name in ("contact", "headline", "summary"):
        if getattr(merged, name) != getattr(current, name):
            report.bump(report.updated, name)
    return merged, report


def merge_preferences(current: Preferences, incoming: Preferences) -> Preferences:
    return Preferences(
        target_titles=dedupe([*current.target_titles, *incoming.target_titles]),
        seniority=_fill(current.seniority, incoming.seniority),
        locations=dedupe([*current.locations, *incoming.locations]),
        remote=current.remote or incoming.remote,
        country=_fill(current.country, incoming.country),
        salary_floor=current.salary_floor or incoming.salary_floor,
        work_authorization=_fill(current.work_authorization, incoming.work_authorization),
        deal_breakers=dedupe([*current.deal_breakers, *incoming.deal_breakers]),
        energizing=dedupe([*current.energizing, *incoming.energizing]),
        draining=dedupe([*current.draining, *incoming.draining]),
        extra_sections={**incoming.extra_sections, **current.extra_sections},
    )
