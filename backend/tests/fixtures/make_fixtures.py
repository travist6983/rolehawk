"""Regenerate the fixture resumes: `uv run python tests/fixtures/make_fixtures.py`.

All people and companies here are fictional."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

HERE = Path(__file__).parent / "resumes"

RESUME_LINES = [
    "Ada Example",
    "ada@example.com | +1 555 0100 | Austin, TX | github.com/ada-example",
    "",
    "Senior Frontend Engineer",
    "",
    "EXPERIENCE",
    "Senior Frontend Engineer, Northwind Payments (Mar 2021 - Present), Remote",
    "- Led the checkout redesign, lifting conversion 12%",
    "- Built a design system used by 6 product teams",
    "Frontend Engineer, Contoso Health (Jun 2017 - Feb 2021), Austin, TX",
    "- Migrated the patient portal from AngularJS to React",
    "- Mentored four junior engineers",
    "",
    "EDUCATION",
    "BSc Computer Science, University of Texas at Austin, 2013 - 2017",
    "",
    "SKILLS",
    "TypeScript, React, Node.js, GraphQL, PostgreSQL, Accessibility",
]


def write_txt() -> None:
    (HERE / "ada_example.txt").write_text("\n".join(RESUME_LINES) + "\n", encoding="utf-8")


def write_docx() -> None:
    from docx import Document

    document = Document()
    document.add_heading(RESUME_LINES[0], level=0)
    for line in RESUME_LINES[1:]:
        if line.isupper():
            document.add_heading(line.title(), level=1)
        elif line.startswith("- "):
            document.add_paragraph(line[2:], style="List Bullet")
        elif line:
            document.add_paragraph(line)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Languages"
    table.rows[0].cells[1].text = "English, Spanish"
    document.save(str(HERE / "ada_example.docx"))


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf() -> None:
    """A minimal one-page PDF with a real text layer, written by hand (no PDF library)."""
    ops = ["BT", "/F1 10 Tf", "14 TL", "50 780 Td"]
    for line in RESUME_LINES:
        ops.append(f"({_pdf_escape(line.replace('\u2013', '-'))}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    (HERE / "ada_example.pdf").write_bytes(out.getvalue())


LINKEDIN = {
    "Profile.csv": (
        "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,"
        "Zip Code,Geo Location,Twitter Handles,Websites,Instant Messengers\n"
        'Ada,Example,,"1 Secret St",Jan 1 1990,Senior Frontend Engineer,'
        '"Frontend engineer who loves accessible UIs.",Software,78701,"Austin, Texas",,'
        "https://ada.example.com,\n"
    ),
    "Email Addresses.csv": (
        "Email Address,Confirmed,Primary,Updated On\n"
        "old@example.com,Yes,No,1/1/20\n"
        "ada@example.com,Yes,Yes,1/1/24\n"
    ),
    "Positions.csv": (
        "Company Name,Title,Description,Location,Started On,Finished On\n"
        'Northwind Payments,Senior Frontend Engineer,"Led the checkout redesign, lifting '
        'conversion 12%\nBuilt a design system used by 6 product teams",Remote,Mar 2021,\n'
        "Contoso Health,Frontend Engineer,Migrated the patient portal to React,"
        '"Austin, TX",Jun 2017,Feb 2021\n'
    ),
    "Education.csv": (
        "School Name,Start Date,End Date,Notes,Degree Name,Activities\n"
        "University of Texas at Austin,2013,2017,,BSc Computer Science,ACM chapter\n"
    ),
    "Skills.csv": "Name\nTypeScript\nReact\nAccessibility\nReact\n",
    "Certifications.csv": (
        "Name,Url,Authority,Started On,Finished On,License Number\n"
        "AWS Certified Developer,,Amazon Web Services,Jan 2023,,\n"
    ),
    "Connections.csv": "Notes:\nThis should never be read\n\nFirst Name,Last Name\nBob,Private\n",
}


def write_linkedin() -> None:
    with zipfile.ZipFile(HERE / "linkedin_export.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in LINKEDIN.items():
            archive.writestr(f"Basic_LinkedInDataExport/{name}", content)


if __name__ == "__main__":
    HERE.mkdir(parents=True, exist_ok=True)
    write_txt()
    write_docx()
    write_pdf()
    write_linkedin()
    print(f"wrote fixtures to {HERE}")
