"""Profile -> CV data, and a sample person for previews before the profile has content."""

from __future__ import annotations

from datetime import date

from offerbound.profile.model import Profile
from offerbound.rendering.model import (
    CoverLetter,
    CvCertification,
    CvContact,
    CvDocument,
    CvEducation,
    CvProject,
    CvRole,
    Recipient,
)


def cv_from_profile(profile: Profile) -> CvDocument:
    """The untailored CV: everything in profile.md, as written. /apply tailors from here."""
    c = profile.contact
    return CvDocument(
        contact=CvContact(
            name=c.name or "Your Name",
            email=c.email,
            phone=c.phone,
            location=c.location,
            links=list(c.links),
        ),
        headline=profile.headline,
        summary=profile.summary,
        experience=[
            CvRole(
                title=e.title,
                organization=e.company,
                location=e.location,
                start=e.start,
                end=e.end,
                current=e.current,
                bullets=list(e.highlights),
            )
            for e in profile.experience
        ],
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
        skills=list(profile.skills),
        projects=[
            CvProject(name=p.name, url=p.url, bullets=list(p.highlights)) for p in profile.projects
        ],
        certifications=[
            CvCertification(name=c.name, issuer=c.issuer, date=c.date)
            for c in profile.certifications
        ],
        achievements=list(profile.achievements),
        languages=list(profile.languages),
    )


def long_date(day: date) -> str:
    """31 October 2026 (no zero padding; %-d isn't available on Windows)."""
    return f"{day.day} {day:%B %Y}"


def has_content(profile: Profile) -> bool:
    return bool(profile.contact.name and (profile.experience or profile.education))


SAMPLE_CONTACT = CvContact(
    name="Ada Example",
    email="ada@example.com",
    phone="+1 555 0100",
    location="Austin, TX",
    links=["linkedin.com/in/ada-example", "github.com/ada-example"],
)


def sample_cv() -> CvDocument:
    return CvDocument(
        contact=SAMPLE_CONTACT,
        headline="Senior Frontend Engineer",
        summary=(
            "Frontend engineer with eight years building accessible, fast web apps for "
            "payments and analytics teams. Comfortable owning a product area end to end."
        ),
        experience=[
            CvRole(
                title="Senior Frontend Engineer",
                organization="Northwind Payments",
                location="Remote",
                start="2021-03",
                current=True,
                bullets=[
                    "Led the checkout redesign across web and mobile web, lifting conversion 12%.",
                    "Built the design system used by 9 product teams (React, TypeScript, "
                    "Storybook).",
                    "Cut median page load from 3.1s to 1.4s with code splitting and caching.",
                ],
            ),
            CvRole(
                title="Frontend Engineer",
                organization="Contoso Analytics",
                location="Austin, TX",
                start="2017-06",
                end="2021-02",
                bullets=[
                    "Shipped the dashboard builder used by 4,000 customers.",
                    "Raised accessibility to WCAG 2.1 AA across the product.",
                ],
            ),
        ],
        education=[
            CvEducation(
                institution="University of Texas at Austin",
                degree="BSc",
                field="Computer Science",
                start="2013",
                end="2017",
            )
        ],
        skills=["TypeScript", "React", "Accessibility", "Performance", "GraphQL", "Node.js"],
        projects=[
            CvProject(
                name="Open-source date picker",
                url="github.com/ada-example/datepicker",
                bullets=["Keyboard-first date picker with 2,000 GitHub stars."],
            )
        ],
        certifications=[CvCertification(name="Certified Accessibility Specialist", date="2022-05")],
        languages=["English (native)", "Spanish (professional)"],
    )


def sample_cover_letter(contact: CvContact = SAMPLE_CONTACT) -> CoverLetter:
    return CoverLetter(
        contact=contact,
        date=long_date(date.today()),
        recipient=Recipient(company="Globex Corporation", name="Hiring Team"),
        greeting="Dear Hiring Team,",
        paragraphs=[
            "I'm applying for the Senior Frontend Engineer role. Your focus on accessible, "
            "fast checkout flows matches the work I've done for the last four years.",
            "At Northwind Payments I led the checkout redesign that lifted conversion 12%, and "
            "I built the design system nine product teams now use.",
            "I'd welcome the chance to talk about how I could help your team ship with the same "
            "care. Thank you for your time.",
        ],
        closing="Sincerely,",
    )
