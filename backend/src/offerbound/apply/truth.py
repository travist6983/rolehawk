"""The truthfulness rule, checked without AI.

Generated documents may rephrase and reorder, but never add employers, titles, dates,
degrees, certifications, or numbers that aren't in profile.md. Drafting copies structured
facts from the profile by index, so most of this holds by construction; this check is the
safety net for numbers in free text, skills, and anything edited by hand or produced
outside the app (the Claude Code skill)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel

from offerbound.profile.model import Profile
from offerbound.rendering.model import CoverLetter, CvDocument

DocumentName = Literal["cv", "cover_letter"]


class Flag(BaseModel):
    document: DocumentName
    location: str  # "summary", "experience.0.bullets.2", "skills", "paragraphs.1"
    text: str
    issue: str
    source: Literal["check", "review"]


_NUMBER = re.compile(r"(?<![\w.])[$€£]?\d[\d,]*(?:\.\d+)?\s?(?:%|[kKmMbB]\b|x\b)?")
_SMALL_OK = {str(n) for n in range(0, 11)}  # "2 teams", "top 3": counting words, not claims


def _norm_number(raw: str) -> str:
    digits = re.sub(r"[^\d.]", "", raw.replace(",", ""))
    if "." in digits:
        digits = digits.rstrip("0").rstrip(".")
    return digits


def numbers_in(text: str) -> set[str]:
    return {n for n in (_norm_number(m) for m in _NUMBER.findall(text)) if n}


def _profile_text(profile: Profile) -> str:
    return profile.model_dump_json()


def _fold(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


class FactIndex:
    """What the profile says, in comparable form."""

    def __init__(self, profile: Profile, extra_text: Iterable[str] = ()) -> None:
        text = _profile_text(profile)
        self.numbers = numbers_in(text) | _SMALL_OK
        for extra in extra_text:  # e.g. the job posting, for cover letters quoting it
            self.numbers |= numbers_in(extra)
        self.text = _fold(text)
        self.roles = {
            (_fold(e.title), _fold(e.company), _fold(e.start), _fold(e.end))
            for e in profile.experience
        }
        self.education = {
            (_fold(e.institution), _fold(e.degree), _fold(e.field)) for e in profile.education
        }
        self.certifications = {_fold(c.name) for c in profile.certifications}
        self.skills = {_fold(s) for s in profile.skills}

    def unknown_numbers(self, text: str) -> list[str]:
        found = [m.strip() for m in _NUMBER.findall(text)]
        return [raw for raw in found if _norm_number(raw) and _norm_number(raw) not in self.numbers]

    def mentions(self, phrase: str) -> bool:
        needle = _fold(phrase)
        return bool(needle) and (
            needle in self.skills
            or re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", self.text) is not None
        )


def _number_flags(facts: FactIndex, document: DocumentName, location: str, text: str) -> list[Flag]:
    unknown = facts.unknown_numbers(text)
    if not unknown:
        return []
    return [
        Flag(
            document=document,
            location=location,
            text=text,
            issue=f"{', '.join(unknown)} isn't in your profile",
            source="check",
        )
    ]


def check_cv(cv: CvDocument, profile: Profile) -> list[Flag]:
    facts = FactIndex(profile)
    flags: list[Flag] = []

    def numbers(location: str, text: str | None) -> None:
        if text:
            flags.extend(_number_flags(facts, "cv", location, text))

    numbers("headline", cv.headline)
    numbers("summary", cv.summary)
    for i, role in enumerate(cv.experience):
        key = (_fold(role.title), _fold(role.organization), _fold(role.start), _fold(role.end))
        if key not in facts.roles:
            flags.append(
                Flag(
                    document="cv",
                    location=f"experience.{i}",
                    text=f"{role.title}, {role.organization or ''}".strip(", "),
                    issue="This role, employer, or its dates don't match your profile",
                    source="check",
                )
            )
        for j, bullet in enumerate(role.bullets):
            numbers(f"experience.{i}.bullets.{j}", bullet)
    for i, edu in enumerate(cv.education):
        if (_fold(edu.institution), _fold(edu.degree), _fold(edu.field)) not in facts.education:
            flags.append(
                Flag(
                    document="cv",
                    location=f"education.{i}",
                    text=" ".join(x for x in (edu.degree, edu.field, edu.institution) if x),
                    issue="This degree or school doesn't match your profile",
                    source="check",
                )
            )
    for i, cert in enumerate(cv.certifications):
        if _fold(cert.name) not in facts.certifications:
            flags.append(
                Flag(
                    document="cv",
                    location=f"certifications.{i}",
                    text=cert.name,
                    issue="This certification isn't in your profile",
                    source="check",
                )
            )
    for i, skill in enumerate(cv.skills):
        if not facts.mentions(skill):
            flags.append(
                Flag(
                    document="cv",
                    location=f"skills.{i}",
                    text=skill,
                    issue="This skill isn't in your profile",
                    source="check",
                )
            )
    for i, project in enumerate(cv.projects):
        for j, bullet in enumerate(project.bullets):
            numbers(f"projects.{i}.bullets.{j}", bullet)
    for i, item in enumerate(cv.achievements):
        numbers(f"achievements.{i}", item)
    return flags


def check_letter(letter: CoverLetter, profile: Profile, posting: str = "") -> list[Flag]:
    """Numbers quoted from the posting ("your team of 40") are allowed in a letter."""
    facts = FactIndex(profile, [posting])
    flags: list[Flag] = []
    for i, paragraph in enumerate(letter.paragraphs):
        flags.extend(_number_flags(facts, "cover_letter", f"paragraphs.{i}", paragraph))
    return flags
