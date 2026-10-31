"""The second Claude pass: read the drafts against the profile and the job, and flag any
claim the profile doesn't support. Flags are shown to the user, highlighted in place."""

from __future__ import annotations

from pydantic import BaseModel, Field

from offerbound.llm.prompting import UNTRUSTED_RULES
from offerbound.rendering.model import CoverLetter, CvDocument

REVIEW_RULES = f"""You are a strict fact checker for job applications. You compare a tailored
CV and cover letter with the candidate's memory (profile, preferences, facts).

Flag every statement the memory doesn't support:
- employers, titles, dates, degrees, certifications, or numbers that aren't in the profile
- skills, tools, technologies, domains, or responsibilities the profile never mentions
- overstated claims ("led" when the profile says "contributed", "expert" with no basis)
- anything taken from the job posting and presented as the candidate's experience

Don't flag faithful rephrasing, reordering, or omissions. Quote the exact line and say in one
short sentence what isn't supported. Use the line keys exactly as given. If everything is
supported, return no flags.

{UNTRUSTED_RULES}"""


class ReviewFlag(BaseModel):
    location: str = Field(description="The line key, e.g. experience.0.bullets.2")
    text: str = Field(description="The flagged text, quoted exactly")
    issue: str = Field(description="What the profile doesn't support, in one sentence")


class ReviewResult(BaseModel):
    flags: list[ReviewFlag]


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


def review_prompt(posting: str, cv: CvDocument, letter: CoverLetter) -> str:
    cv_text = "\n".join(f"[cv:{k}] {v}" for k, v in cv_lines(cv).items())
    letter_text = "\n".join(f"[cover_letter:{k}] {v}" for k, v in letter_lines(letter).items())
    return (
        f"{posting}\n\nCV lines:\n{cv_text}\n\nCover letter lines:\n{letter_text}\n\n"
        "Check every line against my memory. Use keys like cv:summary or "
        "cover_letter:paragraphs.1 as the location."
    )
