"""The ATS check: read the rendered CV the way an applicant tracking system does.

An ATS parses the file's text layer, not the page, so a CV can look right and still import
badly. After every render this extracts the CV's text (PDF, or DOCX when PDF export isn't
available) and checks what a parser needs: readable text, the email and phone as literal
text, date ranges joined by ASCII hyphens (Workday drops dates joined by an en dash), every
role's dates, and section headings in order.

It also scores keyword coverage against the posting's requirements (listed by the writer in
drafts.py), deterministically and in the posting's own words:
- covered: the posting's term is in the CV
- synonym: only another name for it is (ATS matching is often literal)
- missing_have: the profile shows it but the CV never says it, the one worth fixing; it goes
  into the draft's revision round and, if still missing, becomes a flag
- gap: the profile doesn't show it either. It stays a gap: never stuffed in.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from offerbound.apply.truth import FactIndex, Flag
from offerbound.profile.model import Profile
from offerbound.rendering.layout import Bullets, Entry, Paragraph, cv_layout
from offerbound.rendering.model import CvDocument

KeywordStatus = Literal["covered", "synonym", "missing_have", "gap"]
Priority = Literal["required", "preferred"]


class PostingRequirement(BaseModel):
    """One requirement as the posting states it (the writer lists them while drafting)."""

    requirement: str = Field(description='Short, as the posting says it: "3+ years of SQL"')
    priority: Priority = Field(description="required, or preferred (nice to have)")
    terms: list[str] = Field(
        description="The posting's own keywords for it, exactly as written, e.g. ['SQL']"
    )
    also: list[str] = Field(
        description="Other names for the same thing, e.g. ['Amazon Web Services'] for 'AWS'"
    )


class RequirementView(PostingRequirement):
    """A requirement with what the checks found: keyword coverage in the CV's text layer
    and, from the AI review, whether the documents address it."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    keyword: KeywordStatus | None = None
    matched: str | None = Field(default=None, description="The term found in the CV")
    addressed: bool | None = Field(default=None, description="From the AI review")
    note: str | None = None


class AtsCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class AtsReport(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    source: Literal["pdf", "docx"]
    checks: list[AtsCheck] = Field(default_factory=list)


# --- matching -----------------------------------------------------------------------------


def fold(text: str) -> str:
    """Comparable text: NFKC, case-folded, hyphens and slashes as spaces, one space."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[\u2010-\u2015/_-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains(text: str, term: str) -> bool:
    """Whole-term match on folded text, allowing a plural ("dashboard" finds "dashboards")."""
    needle = fold(term)
    if not needle:
        return False
    pattern = rf"(?<![\w+#]){re.escape(needle)}(?:e?s)?(?![\w+#])"
    return re.search(pattern, fold(text)) is not None


def cv_text(cv: CvDocument) -> str:
    """The CV's words as the renderers lay them out, for checking a draft before rendering."""
    layout = cv_layout(cv)
    lines = [layout.name, layout.headline or "", *layout.contact]
    for section in layout.sections:
        lines.append(section.title)
        for block in section.blocks:
            if isinstance(block, Paragraph):
                lines.append(block.text)
            elif isinstance(block, Entry):
                lines += [block.title, block.subtitle or "", block.dates or "", *block.bullets]
            elif isinstance(block, Bullets):
                lines += list(block.items)
    return "\n".join(line for line in lines if line)


def _fields(req: PostingRequirement) -> dict[str, object]:
    return req.model_dump(include=set(PostingRequirement.model_fields))


def coverage(
    requirements: list[PostingRequirement], text: str, profile: Profile
) -> list[RequirementView]:
    facts = FactIndex(profile)
    views: list[RequirementView] = []
    for req in requirements:
        terms = [t for t in req.terms if t.strip()] or [req.requirement]
        found = next((t for t in terms if contains(text, t)), None)
        alias = None if found else next((a for a in req.also if contains(text, a)), None)
        if found:
            status: KeywordStatus = "covered"
        elif alias:
            status = "synonym"
        elif any(facts.mentions(t) for t in [*terms, *req.also]):
            status = "missing_have"
        else:
            status = "gap"
        views.append(
            RequirementView.model_validate(
                {**_fields(req), "keyword": status, "matched": found or alias}
            )
        )
    return views


def missing_flags(views: list[RequirementView], required_only: bool) -> list[Flag]:
    """Requirements the profile supports but the CV never names."""
    return [
        Flag(
            document="cv",
            location="skills",
            text=(v.terms or [v.requirement])[0],
            issue=(
                "The posting asks for this and your profile shows it, but the CV never says "
                "it. Add it where it fits, ideally in a bullet that shows it."
            ),
            source="check",
            kind="ats",
        )
        for v in views
        if v.keyword == "missing_have" and (v.priority == "required" or not required_only)
    ]


# --- parsing ------------------------------------------------------------------------------

_UNICODE_RANGE = re.compile(
    r"(?:\b\d{4}|\b[A-Z][a-z]{2} \d{4})\s*[\u2012-\u2015\u2212]\s*"
    r"(?:\d{4}|[A-Z][a-z]{2}\b|Present)"
)


def parse_checks(cv: CvDocument, text: str) -> list[AtsCheck]:
    checks: list[AtsCheck] = []
    garbage = "(cid:" in text or "\ufffd" in text
    checks.append(
        AtsCheck(
            name="Readable text",
            passed=bool(text.strip()) and not garbage,
            detail="The text layer extracts cleanly."
            if text.strip() and not garbage
            else "Parts of the text extract as unreadable glyphs.",
        )
    )
    flat = " ".join(text.split())
    if cv.contact.email:
        ok = cv.contact.email.casefold() in flat.casefold()
        checks.append(
            AtsCheck(
                name="Email as text",
                passed=ok,
                detail="Your email address is plain text."
                if ok
                else "Your email isn't in the text layer (only an icon or a link?).",
            )
        )
    if cv.contact.phone:
        digits = re.sub(r"\D", "", cv.contact.phone)
        ok = bool(digits) and digits in re.sub(r"\D", "", text)
        checks.append(
            AtsCheck(
                name="Phone as text",
                passed=ok,
                detail="Your phone number is plain text."
                if ok
                else "Your phone number isn't in the text layer.",
            )
        )
    bad = _UNICODE_RANGE.findall(text)
    checks.append(
        AtsCheck(
            name="Plain hyphens in dates",
            passed=not bad,
            detail="Date ranges use plain hyphens."
            if not bad
            else f"Dates joined by a typographic dash can be dropped on import: {bad[0]}",
        )
    )
    layout = cv_layout(cv)
    missing = [
        block.title
        for section in layout.sections
        for block in section.blocks
        if isinstance(block, Entry) and block.dates and fold(block.dates) not in fold(text)
    ]
    checks.append(
        AtsCheck(
            name="Dates on every entry",
            passed=not missing,
            detail="Every role and degree has its dates."
            if not missing
            else f"Dates are missing from the text for: {', '.join(missing[:3])}",
        )
    )
    folded, position, ordered = fold(text), 0, True
    for section in layout.sections:
        found = folded.find(fold(section.title), position)
        if found < 0:
            ordered = False
            break
        position = found
    checks.append(
        AtsCheck(
            name="Headings in order",
            passed=ordered,
            detail="Section headings read in the order they appear."
            if ordered
            else "Section headings are missing or out of order in the text layer.",
        )
    )
    return checks


def check_flags(checks: list[AtsCheck]) -> list[Flag]:
    return [
        Flag(
            document="cv",
            location="contact" if "Email" in c.name or "Phone" in c.name else "layout",
            text=c.name,
            issue=c.detail,
            source="check",
            kind="ats",
        )
        for c in checks
        if not c.passed
    ]
