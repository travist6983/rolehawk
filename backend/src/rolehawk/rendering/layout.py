"""The layout both renderers share. A CV or cover letter becomes a list of simple blocks
(heading, entry, bullets, paragraph); the HTML templates and the DOCX builder only decide how
blocks look. Every word comes from here, so DOCX and PDF can't drift apart in content."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rolehawk.rendering.model import CoverLetter, CvDocument, CvSection

SEPARATOR = " | "  # between contact items and inline lists; plain text, ATS-safe
# Date ranges use a plain ASCII hyphen: many ATS parsers (Workday among them) only split a
# range on U+002D, and drop the dates entirely when they are joined by an en dash.
RANGE = " - "
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HeadingCase = Literal["upper", "title"]

SECTION_TITLES = {
    CvSection.SUMMARY: "Summary",
    CvSection.EXPERIENCE: "Experience",
    CvSection.EDUCATION: "Education",
    CvSection.SKILLS: "Skills",
    CvSection.PROJECTS: "Projects",
    CvSection.CERTIFICATIONS: "Certifications",
    CvSection.ACHIEVEMENTS: "Achievements",
    CvSection.LANGUAGES: "Languages",
}


@dataclass(frozen=True)
class Paragraph:
    text: str
    kind: Literal["paragraph"] = "paragraph"


@dataclass(frozen=True)
class Entry:
    """A role, degree, or project: title and dates on one line, details below."""

    title: str
    subtitle: str | None
    dates: str | None
    bullets: tuple[str, ...]
    kind: Literal["entry"] = "entry"


@dataclass(frozen=True)
class Bullets:
    items: tuple[str, ...]
    kind: Literal["bullets"] = "bullets"


Block = Paragraph | Entry | Bullets


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class CvLayout:
    name: str
    headline: str | None
    contact: tuple[str, ...]  # rendered as unbreakable items, so URLs never split
    sections: tuple[Section, ...]

    @property
    def contact_text(self) -> str | None:
        return SEPARATOR.join(self.contact) or None


@dataclass(frozen=True)
class LetterLayout:
    name: str
    contact: tuple[str, ...]
    date: str | None
    recipient: tuple[str, ...]
    greeting: str
    paragraphs: tuple[str, ...]
    closing: str
    signature: str

    @property
    def contact_text(self) -> str | None:
        return SEPARATOR.join(self.contact) or None


def clean(text: str | None) -> str:
    """One line of plain text: collapsed whitespace, no control characters."""
    if not text:
        return ""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def month_year(value: str | None) -> str | None:
    """ "2021-03" -> "Mar 2021"; "2021" stays; anything else is shown as written."""
    value = clean(value)
    if not value:
        return None
    match = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", value)
    if match and 1 <= int(match.group(2)) <= 12:
        return f"{MONTHS[int(match.group(2)) - 1]} {match.group(1)}"
    return value


def period(start: str | None, end: str | None, current: bool = False) -> str | None:
    first = month_year(start)
    last = "Present" if current and not end else month_year(end)
    if first and last:
        return first if first == last else f"{first}{RANGE}{last}"
    return first or last


def _heading(title: str, case: HeadingCase) -> str:
    return title.upper() if case == "upper" else title


def _contact(parts: list[str | None]) -> tuple[str, ...]:
    return tuple(c for c in (clean(p) for p in parts) if c)


def _items(values: list[str]) -> tuple[str, ...]:
    return tuple(c for c in (clean(v) for v in values) if c)


def cv_layout(cv: CvDocument, heading_case: HeadingCase = "title") -> CvLayout:
    c = cv.contact
    sections: list[Section] = []
    for section_id in dict.fromkeys(cv.section_order):  # each section once, in order
        blocks: list[Block] = []
        if section_id is CvSection.SUMMARY and clean(cv.summary):
            blocks.append(Paragraph(clean(cv.summary)))
        elif section_id is CvSection.EXPERIENCE:
            for role in cv.experience:
                where = ", ".join(x for x in (clean(role.organization), clean(role.location)) if x)
                blocks.append(
                    Entry(
                        clean(role.title),
                        where or None,
                        period(role.start, role.end, role.current),
                        _items(role.bullets),
                    )
                )
        elif section_id is CvSection.EDUCATION:
            for edu in cv.education:
                degree = " in ".join(x for x in (clean(edu.degree), clean(edu.field)) if x)
                blocks.append(
                    Entry(
                        degree or clean(edu.institution),
                        clean(edu.institution) if degree else None,
                        period(edu.start, edu.end),
                        _items(edu.details),
                    )
                )
        elif section_id is CvSection.SKILLS and _items(cv.skills):
            blocks.append(Paragraph(SEPARATOR.join(_items(cv.skills))))
        elif section_id is CvSection.PROJECTS:
            for project in cv.projects:
                blocks.append(
                    Entry(
                        clean(project.name),
                        clean(project.url) or None,
                        None,
                        _items(project.bullets),
                    )
                )
        elif section_id is CvSection.CERTIFICATIONS and cv.certifications:
            lines = [
                ", ".join(
                    x for x in (clean(cert.name), clean(cert.issuer), month_year(cert.date)) if x
                )
                for cert in cv.certifications
            ]
            blocks.append(Bullets(_items(lines)))
        elif section_id is CvSection.ACHIEVEMENTS and _items(cv.achievements):
            blocks.append(Bullets(_items(cv.achievements)))
        elif section_id is CvSection.LANGUAGES and _items(cv.languages):
            blocks.append(Paragraph(SEPARATOR.join(_items(cv.languages))))
        blocks = [b for b in blocks if not (isinstance(b, Entry) and not b.title)]
        if blocks:
            sections.append(
                Section(
                    section_id.value,
                    _heading(SECTION_TITLES[section_id], heading_case),
                    tuple(blocks),
                )
            )
    return CvLayout(
        name=clean(c.name),
        headline=clean(cv.headline) or None,
        contact=_contact([c.email, c.phone, c.location, *c.links]),
        sections=tuple(sections),
    )


def letter_layout(letter: CoverLetter) -> LetterLayout:
    c = letter.contact
    r = letter.recipient
    recipient = [r.name, r.company, *r.address_lines]
    return LetterLayout(
        name=clean(c.name),
        contact=_contact([c.email, c.phone, c.location, *c.links]),
        date=clean(letter.date) or None,
        recipient=_items([x for x in recipient if x]),
        greeting=clean(letter.greeting),
        paragraphs=_items(letter.paragraphs),
        closing=clean(letter.closing),
        signature=clean(letter.signature) or clean(c.name),
    )
