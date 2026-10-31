"""LinkedIn "Get a copy of your data" export (ZIP of CSVs) -> Profile, without any AI call.

Only career data is imported. Birth date, address, messages, and connections are ignored."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterator

from offerbound.profile.model import (
    Certification,
    Contact,
    Education,
    Experience,
    Profile,
    Project,
)
from offerbound.profile.parsing import dedupe, parse_date

LINKEDIN_FILES = {
    "Profile.csv",
    "Positions.csv",
    "Education.csv",
    "Skills.csv",
    "Certifications.csv",
    "Projects.csv",
    "Languages.csv",
    "Email Addresses.csv",
}
MAX_CSV_BYTES = 5 * 1024 * 1024


def _rows(archive: zipfile.ZipFile, name: str, expected: str) -> Iterator[dict[str, str]]:
    """Rows of the first matching CSV. Some exports put notes above the header; skip them."""
    member = next((n for n in archive.namelist() if n.rsplit("/", 1)[-1] == name), None)
    if member is None or archive.getinfo(member).file_size > MAX_CSV_BYTES:
        return
    text = archive.read(member).decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if expected in line), None)
    if start is None:
        return
    for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        yield {k.strip(): (v or "").strip() for k, v in row.items() if k}


def _highlights(description: str) -> list[str]:
    parts = re.split(r"\n+|(?:^|\s)[•▪◦]\s*", description)
    return [re.sub(r"^\s*[-*]\s*", "", p).strip() for p in parts if p and p.strip()]


def parse_linkedin_export(archive: zipfile.ZipFile) -> tuple[Profile, str]:
    """Returns the profile and a readable text summary (stored as the document's text)."""
    profile = Profile()

    for row in _rows(archive, "Profile.csv", "First Name"):
        name = " ".join(p for p in [row.get("First Name"), row.get("Last Name")] if p)
        profile.contact = Contact(
            name=name or None,
            location=row.get("Geo Location") or None,
            links=[w.strip() for w in re.split(r"[,\n]", row.get("Websites", "")) if w.strip()],
        )
        profile.headline = row.get("Headline") or None
        profile.summary = row.get("Summary") or None
        break

    for row in _rows(archive, "Email Addresses.csv", "Email Address"):
        if row.get("Primary", "").lower() == "yes" or not profile.contact.email:
            profile.contact.email = row.get("Email Address") or profile.contact.email

    for row in _rows(archive, "Positions.csv", "Company Name"):
        if not row.get("Title"):
            continue
        end = parse_date(row.get("Finished On"))
        profile.experience.append(
            Experience(
                title=row["Title"],
                company=row.get("Company Name") or None,
                location=row.get("Location") or None,
                start=parse_date(row.get("Started On")),
                end=end,
                current=end is None and bool(row.get("Started On")),
                highlights=_highlights(row.get("Description", "")),
            )
        )

    for row in _rows(archive, "Education.csv", "School Name"):
        if not row.get("School Name"):
            continue
        notes = "; ".join(p for p in [row.get("Notes"), row.get("Activities")] if p)
        profile.education.append(
            Education(
                institution=row["School Name"],
                degree=row.get("Degree Name") or None,
                start=parse_date(row.get("Start Date")),
                end=parse_date(row.get("End Date")),
                notes=notes or None,
            )
        )

    profile.skills = dedupe(
        [r["Name"] for r in _rows(archive, "Skills.csv", "Name") if r.get("Name")]
    )

    for row in _rows(archive, "Certifications.csv", "Name"):
        if row.get("Name"):
            profile.certifications.append(
                Certification(
                    name=row["Name"],
                    issuer=row.get("Authority") or None,
                    date=parse_date(row.get("Started On")),
                    url=row.get("Url") or None,
                )
            )

    for row in _rows(archive, "Projects.csv", "Title"):
        if row.get("Title"):
            profile.projects.append(
                Project(
                    name=row["Title"],
                    url=row.get("Url") or None,
                    highlights=_highlights(row.get("Description", "")),
                )
            )

    profile.languages = dedupe(
        [
            f"{r['Name']} ({r['Proficiency']})" if r.get("Proficiency") else r["Name"]
            for r in _rows(archive, "Languages.csv", "Name")
            if r.get("Name")
        ]
    )

    summary = (
        f"LinkedIn export: {len(profile.experience)} positions, {len(profile.education)} "
        f"education entries, {len(profile.skills)} skills, {len(profile.certifications)} "
        f"certifications, {len(profile.projects)} projects."
    )
    return profile, summary
