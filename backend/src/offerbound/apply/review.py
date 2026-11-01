"""The second Claude pass, with a fresh context: read the drafts against the profile and the
posting like a careful reviewer. It flags claims the profile doesn't support, stretches the
candidate couldn't defend in an interview, and generic sentences, and it checks that every
posting requirement is addressed. Flags are shown to the user, highlighted in place."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from offerbound.apply.ats import PostingRequirement
from offerbound.llm.prompting import UNTRUSTED_RULES
from offerbound.rendering.model import CoverLetter, CvDocument

REVIEW_RULES = f"""You review a tailored CV and cover letter for one job before the candidate
sends them. Compare them with the candidate's memory (profile, preferences, facts) and the
posting, and flag lines with one of these kinds:

- unsupported: employers, titles, dates, degrees, certifications, numbers, skills, tools,
  domains, or responsibilities the memory doesn't support; anything from the posting
  presented as the candidate's experience; overstated claims ("led" when the profile says
  "contributed", "expert" with no basis).
- stretch: grounded in the profile, but framed further than the candidate could defend in an
  interview without backtracking: adjacent work described in the posting's exact terms,
  study and industry work merged into one claim, a responsibility inflated. Say what makes
  it a stretch and how to soften it.
- generic: a sentence any applicant could write (no specific example, tool, or result), or
  cover-letter text that repeats the CV instead of saying what the candidate would do for
  this employer. Summary and cover letter only.

Don't flag faithful rephrasing, reordering, or leaving profile facts out. Quote the exact
line, use the line keys exactly as given, and keep each issue to one short sentence.

Then, for each numbered requirement, say whether the documents address it: shown with
evidence, or acknowledged honestly as a gap with a bridge, counts as addressed; silently
skipped does not. Add a one-sentence note.

If everything is fine, return no flags and mark every requirement addressed.

{UNTRUSTED_RULES}"""

ReviewKind = Literal["unsupported", "stretch", "generic"]


class ReviewFlag(BaseModel):
    location: str = Field(description="The line key, e.g. cv:experience.0.bullets.2")
    text: str = Field(description="The flagged text, quoted exactly")
    issue: str = Field(description="What's wrong, in one sentence")
    kind: ReviewKind = Field(default="unsupported", description="unsupported, stretch, or generic")


class RequirementReview(BaseModel):
    index: int = Field(description="The requirement's number, exactly as given")
    addressed: bool
    note: str = Field(description="One sentence: where it's addressed, or what's missing")


class ReviewResult(BaseModel):
    flags: list[ReviewFlag]
    requirements: list[RequirementReview] = Field(default_factory=list)


def cv_lines(cv: CvDocument) -> dict[str, str]:
    lines: dict[str, str] = {}
    if cv.headline:
        lines["headline"] = cv.headline
    if cv.summary:
        lines["summary"] = cv.summary
    for i, role in enumerate(cv.experience):
        lines[f"experience.{i}"] = f"{role.title}, {role.organization or ''}".strip(", ")
        for j, bullet in enumerate(role.bullets):
            lines[f"experience.{i}.bullets.{j}"] = bullet
    if cv.skills:
        lines["skills"] = ", ".join(cv.skills)
    for i, project in enumerate(cv.projects):
        for j, bullet in enumerate(project.bullets):
            lines[f"projects.{i}.bullets.{j}"] = bullet
    return lines


def letter_lines(letter: CoverLetter) -> dict[str, str]:
    return {f"paragraphs.{i}": p for i, p in enumerate(letter.paragraphs)}


def review_prompt(
    posting: str,
    cv: CvDocument,
    letter: CoverLetter,
    requirements: list[PostingRequirement] | None = None,
) -> str:
    cv_text = "\n".join(f"[cv:{k}] {v}" for k, v in cv_lines(cv).items())
    letter_text = "\n".join(f"[cover_letter:{k}] {v}" for k, v in letter_lines(letter).items())
    listed = "\n".join(
        f"{i}. ({r.priority}) {r.requirement}" for i, r in enumerate(requirements or [])
    )
    asks = f"\n\nThe posting's requirements:\n{listed}" if listed else ""
    return (
        f"{posting}\n\nCV lines:\n{cv_text}\n\nCover letter lines:\n{letter_text}{asks}\n\n"
        "Check every line against my memory and the posting. Use keys like cv:summary or "
        "cover_letter:paragraphs.1 as the location."
    )
