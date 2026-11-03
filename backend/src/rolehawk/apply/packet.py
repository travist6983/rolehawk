"""The apply packet: everything an application form asks for, in one place, for Claude Code
to fill the form in the user's own browser (skills/apply). It never submits; the user does.

Facts come from the profile and preferences only. Saved answers cover the questions forms
keep asking; anything else is left for the user (`leave_for_user`), never guessed."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from rolehawk.apply.autofill import Applicant, Ats, applicant_from, application_url
from rolehawk.db.models import Job
from rolehawk.profile.markdown import answer_key
from rolehawk.profile.model import Education, Experience, Preferences, Profile, SavedAnswer
from rolehawk.profile.parsing import format_salary
from rolehawk.rendering.service import Format

# Questions most forms ask. The /apply skill asks the user for any without a saved answer.
STANDARD_QUESTIONS = (
    "Will you now or in the future require visa sponsorship?",
    "What are your salary expectations?",
    "When can you start?",
    "Are you willing to relocate?",
    "How did you hear about this job?",
)

# What Claude leaves for the user on every form.
LEAVE_FOR_USER = (
    "Signing in or creating an account (passwords are never typed for you)",
    "CAPTCHAs and other human checks",
    "Legal attestations, terms, and consent checkboxes",
    "Voluntary self-identification (gender, race, veteran, disability)",
    "Any question your profile and saved answers don't answer",
    "The final Submit button",
)


class ApplyPacket(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    application_id: int
    job_id: int
    job_title: str = Field(description="Third-party text")
    company: str = Field(description="Third-party text")
    posting_url: str
    application_url: str = Field(description="Where the form usually is")
    ats: Ats
    applicant: Applicant
    cv_file: str | None = Field(description="The tailored CV to upload (PDF when there is one)")
    cover_letter_file: str | None
    cover_letter_text: str = Field(description="For forms with a cover letter text box")
    work_history: list[Experience] = Field(description="From the profile, newest first")
    education: list[Education]
    skills: list[str]
    languages: list[str]
    certifications: list[str]
    work_authorization: str | None
    salary_floor: str | None = Field(
        description="The user's minimum. Not an expectation: ask before using it as one"
    )
    locations: list[str]
    answers: list[SavedAnswer] = Field(description="Saved answers to common questions")
    missing_answers: list[str] = Field(
        description="Common questions with no saved answer yet: ask the user once and save"
    )
    leave_for_user: list[str]


def _file(files: dict[Format, str]) -> str | None:
    return files.get("pdf") or files.get("docx")


def build_packet(
    application_id: int,
    job: Job,
    profile: Profile,
    prefs: Preferences,
    cv_files: dict[Format, str],
    cover_files: dict[Format, str],
    cover_letter_text: str,
) -> ApplyPacket:
    contact = profile.contact
    form_url, ats = application_url(job.url)
    saved = {answer_key(a.question) for a in prefs.answers}
    return ApplyPacket(
        application_id=application_id,
        job_id=job.id,
        job_title=job.title,
        company=job.company,
        posting_url=job.url,
        application_url=form_url,
        ats=ats,
        applicant=applicant_from(
            contact.name, contact.email, contact.phone, contact.location, contact.links
        ),
        cv_file=_file(cv_files),
        cover_letter_file=_file(cover_files),
        cover_letter_text=cover_letter_text,
        work_history=profile.experience,
        education=profile.education,
        skills=profile.skills,
        languages=profile.languages,
        certifications=[c.name for c in profile.certifications],
        work_authorization=prefs.work_authorization,
        salary_floor=format_salary(prefs.salary_floor) if prefs.salary_floor else None,
        locations=prefs.locations,
        answers=prefs.answers,
        missing_answers=[q for q in STANDARD_QUESTIONS if answer_key(q) not in saved],
        leave_for_user=list(LEAVE_FOR_USER),
    )
