"""What Claude writes for /apply, and how it becomes a CV.

The model chooses and rewrites; it never states structured facts. Roles, projects,
education, and certifications are picked by their index in the profile, so employers,
titles, dates, degrees, and certifications are always copied from profile.md."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from offerbound.db.models import Job
from offerbound.llm.prompting import TRUTHFULNESS_RULES, UNTRUSTED_RULES, untrusted
from offerbound.profile.model import Profile
from offerbound.rendering.model import (
    CoverLetter,
    CvCertification,
    CvContact,
    CvDocument,
    CvEducation,
    CvProject,
    CvRole,
    CvSection,
    Recipient,
)
from offerbound.rendering.samples import long_date

Section = Literal["summary", "experience", "skills", "cover_letter"]
SECTIONS: tuple[Section, ...] = ("summary", "experience", "skills", "cover_letter")
POSTING_CHARS = 8_000


class RoleDraft(BaseModel):
    index: int = Field(description="Position of the role in the profile's experience list")
    bullets: list[str] = Field(description="Rewritten highlights for this job, best first")


class ProjectDraft(BaseModel):
    index: int = Field(description="Position of the project in the profile's projects list")
    bullets: list[str]


class CvDraft(BaseModel):
    headline: str | None = Field(description="One line, e.g. the target title")
    summary: str = Field(description="2-4 sentences tailored to this job")
    roles: list[RoleDraft] = Field(description="Roles to include, in the order to show them")
    skills: list[str] = Field(description="Skills from the profile, most relevant first")
    projects: list[ProjectDraft] = Field(description="Relevant projects only; may be empty")
    certification_indexes: list[int] = Field(description="Relevant certifications by index")


class LetterDraft(BaseModel):
    greeting: str = Field(description='e.g. "Dear Hiring Team,"')
    paragraphs: list[str] = Field(description="3-4 short paragraphs")
    closing: str = Field(description='e.g. "Sincerely,"')


class ApplicationDraft(BaseModel):
    cv: CvDraft
    cover_letter: LetterDraft


WRITER_RULES = f"""You tailor a job seeker's CV and cover letter to one job posting.

The profile below is the only source of facts about the candidate. You choose and rewrite;
you never add facts:
- Pick roles, projects, and certifications by their index in the profile. Never invent or
  rename an employer, title, date, degree, or certification.
- Rewrite each chosen role's bullets from that role's own highlights: reorder, tighten, and
  lead with what this job asks for. Keep every number exactly as the profile states it, and
  add no new numbers, percentages, team sizes, or amounts.
- Skills come only from the profile (its skills list or words used in its highlights).
- Reframe emphasis, never substance. Every line must survive an interview: if the candidate
  would have to say "well, what I actually meant was...", it goes too far. Don't describe
  adjacent work in the posting's exact terms, and don't merge study and industry work into
  one claim.

How to write (recruiters skim, and they read clichés as AI-written):
- Show, don't claim: back each strength with a specific example, tool, or result from the
  profile. No clichés or filler ("I am writing to express my interest", "passionate about",
  "great fit", "leverage my skills", "hit the ground running", "proven track record", "team
  player", "fast-paced environment").
- No em dashes. Use a comma, a period, or a new sentence.
- Confident, not apologetic: "I bring X, shown by Y", not "I think I could contribute".
- CV headline: their title or specialty plus the posting's key term (for example "Data
  analyst specializing in supply-chain forecasting"), never "Application for ...".
- CV bullets start with a verb (implied first person) and vary their openings.
- The cover letter looks forward and is not a CV recap: open with the role and one specific
  reason for this company; then which of their problems the candidate can take on and how,
  backed by one or two past examples; then a short, confident close. 3-4 paragraphs, under
  300 words, first person.
- Greet the person the posting names, if it names one; otherwise "Dear Hiring Team,".
- Write the cover letter in the language the posting is written in. Keep the CV in the
  profile's language.

{TRUTHFULNESS_RULES}

{UNTRUSTED_RULES}"""


def indexed_profile(profile: Profile) -> str:
    """The profile with indexes on every list the draft refers to."""
    lines = ["Experience (pick by index):"]
    for i, e in enumerate(profile.experience):
        dates = f"{e.start or '?'} to {'present' if e.current else e.end or '?'}"
        lines.append(f"  [{i}] {e.title} at {e.company or 'n/a'} ({dates})")
        lines += [f"      - {h}" for h in e.highlights]
    lines.append("Projects (pick by index):")
    for i, p in enumerate(profile.projects):
        lines.append(f"  [{i}] {p.name}")
        lines += [f"      - {h}" for h in p.highlights]
    lines.append("Certifications (pick by index):")
    lines += [f"  [{i}] {c.name}" for i, c in enumerate(profile.certifications)]
    lines.append("Skills: " + ", ".join(profile.skills))
    return "\n".join(lines)


def job_brief(job: Job) -> str:
    header = f"Job: {job.title} at {job.company} | location: {job.location or 'not stated'}"
    return header + "\n" + untrusted("job_posting", job.description[:POSTING_CHARS], job_id=job.id)


def draft_prompt(job: Job, profile: Profile) -> str:
    return (
        f"{job_brief(job)}\n\n<profile_index>\n{indexed_profile(profile)}\n</profile_index>\n\n"
        "Draft the tailored CV and cover letter for this job."
    )


def revision_prompt(problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        "A check of the draft found these problems:\n"
        f"{listed}\n\nReturn the full draft again with each one fixed: remove or reword "
        "anything the profile doesn't support so every fact comes from it, and rewrite clichés "
        "with something concrete from the profile. Change nothing else."
    )


def section_prompt(section: Section, current: str, instruction: str | None) -> str:
    ask = f"\nThe user asks: {instruction.strip()}" if instruction and instruction.strip() else ""
    return (
        f"Here is the current draft:\n{current}\n\nRewrite only the {section.replace('_', ' ')} "
        f"part.{ask}\nReturn the full draft with every other part unchanged."
    )


def build_cv(profile: Profile, draft: CvDraft) -> CvDocument:
    """A CvDocument whose structured facts all come from the profile."""
    c = profile.contact
    roles: list[CvRole] = []
    seen: set[int] = set()
    for role in draft.roles:
        if not 0 <= role.index < len(profile.experience) or role.index in seen:
            continue
        seen.add(role.index)
        e = profile.experience[role.index]
        roles.append(
            CvRole(
                title=e.title,
                organization=e.company,
                location=e.location,
                start=e.start,
                end=e.end,
                current=e.current,
                bullets=[b.strip() for b in role.bullets if b.strip()] or list(e.highlights),
            )
        )
    projects = [
        CvProject(
            name=profile.projects[p.index].name,
            url=profile.projects[p.index].url,
            bullets=[b.strip() for b in p.bullets if b.strip()],
        )
        for p in draft.projects
        if 0 <= p.index < len(profile.projects)
    ]
    certifications = [
        CvCertification(
            name=profile.certifications[i].name,
            issuer=profile.certifications[i].issuer,
            date=profile.certifications[i].date,
        )
        for i in dict.fromkeys(draft.certification_indexes)
        if 0 <= i < len(profile.certifications)
    ]
    return CvDocument(
        contact=CvContact(
            name=c.name or "Your Name",
            email=c.email,
            phone=c.phone,
            location=c.location,
            links=list(c.links),
        ),
        headline=draft.headline,
        summary=draft.summary,
        experience=roles,
        education=[
            CvEducation(
                institution=e.institution,
                degree=e.degree,
                field=e.field,
                start=e.start,
                end=e.end,
                details=[e.notes] if e.notes else [],
            )
            for e in profile.education
        ],
        skills=list(dict.fromkeys(s.strip() for s in draft.skills if s.strip())),
        projects=projects,
        certifications=certifications,
        achievements=list(profile.achievements),
        languages=list(profile.languages),
        section_order=list(CvSection),
    )


def build_letter(profile: Profile, job: Job, draft: LetterDraft) -> CoverLetter:
    from datetime import date

    c = profile.contact
    return CoverLetter(
        contact=CvContact(
            name=c.name or "Your Name",
            email=c.email,
            phone=c.phone,
            location=c.location,
            links=list(c.links),
        ),
        date=long_date(date.today()),
        recipient=Recipient(company=job.company or None),
        greeting=draft.greeting.strip() or "Dear Hiring Team,",
        paragraphs=[p.strip() for p in draft.paragraphs if p.strip()] or ["(empty)"],
        closing=draft.closing.strip() or "Sincerely,",
    )


def draft_from_documents(cv: CvDocument, letter: CoverLetter, profile: Profile) -> ApplicationDraft:
    """Express current documents as a draft again (for regenerating one section)."""

    def role_index(role: CvRole) -> int:
        for i, e in enumerate(profile.experience):
            if (e.title, e.company, e.start) == (role.title, role.organization, role.start):
                return i
        return -1

    def project_index(name: str) -> int:
        return next((i for i, p in enumerate(profile.projects) if p.name == name), -1)

    def cert_index(name: str) -> int:
        return next((i for i, c in enumerate(profile.certifications) if c.name == name), -1)

    return ApplicationDraft(
        cv=CvDraft(
            headline=cv.headline,
            summary=cv.summary or "",
            roles=[RoleDraft(index=role_index(r), bullets=r.bullets) for r in cv.experience],
            skills=cv.skills,
            projects=[
                ProjectDraft(index=project_index(p.name), bullets=p.bullets) for p in cv.projects
            ],
            certification_indexes=[cert_index(c.name) for c in cv.certifications],
        ),
        cover_letter=LetterDraft(
            greeting=letter.greeting, paragraphs=letter.paragraphs, closing=letter.closing
        ),
    )
