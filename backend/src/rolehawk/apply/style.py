"""House style for generated CVs and cover letters, checked without AI.

Recruiters read clichés and dash-heavy prose as AI-written. The writer prompt (drafts.py)
asks for concrete, forward-looking text; this module is the safety net. Clichés found in a
draft go into the same single revision round as the fact check, and anything left is shown
to the user as a style flag. Em dashes are replaced in the model's output (never in the
user's own edits), and dashes inside number ranges become ASCII hyphens, which ATS parsers
read reliably."""

from __future__ import annotations

import re

from rolehawk.apply.truth import DocumentName, Flag
from rolehawk.rendering.model import CoverLetter, CvDocument

# Phrases that add nothing a recruiter can check. Matched case-insensitively on word
# boundaries; each entry says what to do instead.
CLICHES: dict[str, str] = {
    "i am writing to express my interest": "open with the role and one specific reason",
    "i am writing to apply": "open with the role and one specific reason",
    "passionate about": "show it with something you did",
    "great fit": "name the requirement you meet and how",
    "perfect fit": "name the requirement you meet and how",
    "ideal candidate": "name the requirement you meet and how",
    "leverage my": "say what you'd do",
    "hit the ground running": "say what you'd do first",
    "drive results": "name the result",
    "results-driven": "name a result",
    "proven track record": "give the record",
    "team player": "describe the teamwork and its outcome",
    "go-getter": "show initiative with an example",
    "think outside the box": "describe the idea",
    "fast-paced environment": "describe the pace concretely, or cut it",
    "synergy": "say what working together produced",
    "synergies": "say what working together produced",
    "dynamic team": "describe the team",
    "excited to apply": "say what draws you to this role",
    "thrilled to apply": "say what draws you to this role",
    "delve": "use a plain verb",
    "tapestry": "use a plain word",
    "a testament to": "state the fact directly",
    "cutting-edge": "name the technology",
    "seamlessly": "describe what worked",
    "in today's fast-paced": "cut the opener",
    "wealth of experience": "give the experience",
    "i believe i would be": "state what you bring",
}
_CLICHE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(c) for c in sorted(CLICHES, key=len, reverse=True)) + r")"
    r"(?![\w-])",
    re.IGNORECASE,
)
_RANGE_DASH = re.compile(r"(?<=\d)\s?[\u2012\u2013\u2014\u2015]\s?(?=\d)")
_SENTENCE_DASH = re.compile(r"\s*(?:\u2014|\u2015|--)\s*|\s+\u2013\s+")


def plain_dashes(text: str) -> str:
    """Em dashes become commas; dashes inside number ranges become ASCII hyphens."""
    text = _RANGE_DASH.sub("-", text)
    text = _SENTENCE_DASH.sub(", ", text)
    return re.sub(r",\s*([,.;:!?])", r"\1", text).replace(" ,", ",")


def polish(
    cv: CvDocument, letter: CoverLetter, section: str | None = None
) -> tuple[CvDocument, CoverLetter]:
    """Apply plain_dashes to what the model wrote: everything, or one regenerated section
    ("summary", "experience", "cover_letter") so the user's own edits elsewhere stay as-is."""
    update: dict[str, object] = {}
    if section in (None, "summary"):
        update["headline"] = plain_dashes(cv.headline) if cv.headline else cv.headline
        update["summary"] = plain_dashes(cv.summary) if cv.summary else cv.summary
    if section in (None, "experience"):
        update["experience"] = [
            r.model_copy(update={"bullets": [plain_dashes(b) for b in r.bullets]})
            for r in cv.experience
        ]
        update["projects"] = [
            p.model_copy(update={"bullets": [plain_dashes(b) for b in p.bullets]})
            for p in cv.projects
        ]
    if section in (None, "cover_letter"):
        letter = letter.model_copy(
            update={"paragraphs": [plain_dashes(p) for p in letter.paragraphs]}
        )
    return cv.model_copy(update=update), letter


def _flags(document: DocumentName, location: str, text: str | None) -> list[Flag]:
    if not text:
        return []
    found = list(dict.fromkeys(m.group(1).lower() for m in _CLICHE.finditer(text)))
    return [
        Flag(
            document=document,
            location=location,
            text=text,
            issue=f'"{phrase}" is a cliché: {CLICHES[phrase]}',
            source="check",
            kind="style",
        )
        for phrase in found
    ]


def check_style(cv: CvDocument, letter: CoverLetter) -> list[Flag]:
    flags = _flags("cv", "headline", cv.headline) + _flags("cv", "summary", cv.summary)
    for i, role in enumerate(cv.experience):
        for j, bullet in enumerate(role.bullets):
            flags += _flags("cv", f"experience.{i}.bullets.{j}", bullet)
    for i, paragraph in enumerate(letter.paragraphs):
        flags += _flags("cover_letter", f"paragraphs.{i}", paragraph)
    return flags
