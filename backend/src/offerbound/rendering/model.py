"""What goes on a CV or cover letter. /apply fills these (tailored, truthful); the renderer
turns them into DOCX and PDF with a chosen template."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class DocumentKind(StrEnum):
    CV = "cv"
    COVER_LETTER = "cover_letter"


class CvSection(StrEnum):
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    ACHIEVEMENTS = "achievements"
    LANGUAGES = "languages"


DEFAULT_ORDER = list(CvSection)


class CvContact(_Model):
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class CvRole(_Model):
    title: str
    organization: str | None = None
    location: str | None = None
    start: str | None = Field(default=None, description="YYYY or YYYY-MM")
    end: str | None = Field(default=None, description="YYYY or YYYY-MM; null when current")
    current: bool = False
    bullets: list[str] = Field(default_factory=list)


class CvEducation(_Model):
    institution: str
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None
    details: list[str] = Field(default_factory=list)


class CvProject(_Model):
    name: str
    url: str | None = None
    bullets: list[str] = Field(default_factory=list)


class CvCertification(_Model):
    name: str
    issuer: str | None = None
    date: str | None = None


class CvDocument(_Model):
    contact: CvContact
    headline: str | None = None
    summary: str | None = None
    experience: list[CvRole] = Field(default_factory=list)
    education: list[CvEducation] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[CvProject] = Field(default_factory=list)
    certifications: list[CvCertification] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    section_order: list[CvSection] = Field(
        default_factory=lambda: list(DEFAULT_ORDER),
        description="Sections in display order; empty sections are skipped",
    )


class Recipient(_Model):
    company: str | None = None
    name: str | None = Field(default=None, description="Hiring manager, if known")
    address_lines: list[str] = Field(default_factory=list)


class CoverLetter(_Model):
    contact: CvContact
    date: str | None = Field(default=None, description="As it should appear, e.g. 31 October 2026")
    recipient: Recipient = Field(default_factory=Recipient)
    greeting: str = "Dear Hiring Manager,"
    paragraphs: list[str] = Field(min_length=1)
    closing: str = "Sincerely,"
    signature: str | None = Field(default=None, description="Defaults to the contact name")
