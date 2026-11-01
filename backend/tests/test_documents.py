import io
import zipfile
from pathlib import Path
from typing import ClassVar

import pytest

from rolehawk.profile import documents
from rolehawk.profile.documents import DocumentError, DocumentKind, parse_document

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("ada_example.txt", DocumentKind.TEXT),
        ("ada_example.docx", DocumentKind.DOCX),
        ("ada_example.pdf", DocumentKind.PDF),
    ],
)
def test_resume_formats_yield_text(name: str, kind: DocumentKind) -> None:
    parsed = parse_document(name, (FIXTURES / name).read_bytes())
    assert parsed.kind is kind
    assert "Northwind Payments" in parsed.text
    assert "Led the checkout redesign" in parsed.text
    assert parsed.profile is None


def test_docx_includes_tables() -> None:
    parsed = parse_document("cv.docx", (FIXTURES / "ada_example.docx").read_bytes())
    assert "Languages | English, Spanish" in parsed.text


def test_kind_is_detected_from_content_not_extension() -> None:
    parsed = parse_document("resume.txt", (FIXTURES / "ada_example.pdf").read_bytes())
    assert parsed.kind is DocumentKind.PDF


def test_linkedin_export_maps_directly() -> None:
    parsed = parse_document("export.zip", (FIXTURES / "linkedin_export.zip").read_bytes())
    assert parsed.kind is DocumentKind.LINKEDIN
    profile = parsed.profile
    assert profile is not None
    assert profile.contact.name == "Ada Example"
    assert profile.contact.email == "ada@example.com"  # the primary address
    assert profile.contact.location == "Austin, Texas"
    assert profile.headline == "Senior Frontend Engineer"
    current, previous = profile.experience
    assert (current.company, current.start, current.end, current.current) == (
        "Northwind Payments",
        "2021-03",
        None,
        True,
    )
    assert current.highlights == [
        "Led the checkout redesign, lifting conversion 12%",
        "Built a design system used by 6 product teams",
    ]
    assert (previous.start, previous.end, previous.current) == ("2017-06", "2021-02", False)
    assert profile.education[0].degree == "BSc Computer Science"
    assert profile.skills == ["TypeScript", "React", "Accessibility"]
    assert profile.certifications[0].issuer == "Amazon Web Services"
    # Private data is never imported.
    dumped = profile.model_dump_json()
    assert "Secret St" not in dumped
    assert "1990" not in dumped
    assert "Bob" not in dumped


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "empty"),
        (b"\x00\x01\x02\x03" * 500, "isn't supported"),
        (_zip({"photos/cat.jpg": "x"}), "isn't a LinkedIn data export"),
        (b"PK\x03\x04garbage", "damaged"),
    ],
)
def test_unusable_files_explain_themselves(data: bytes, message: str) -> None:
    with pytest.raises(DocumentError, match=message):
        parse_document("upload.bin", data)


def test_old_word_files_ask_for_a_conversion() -> None:
    with pytest.raises(DocumentError, match="PDF or DOCX"):
        parse_document("resume.doc", b"\xd0\xcf\x11\xe0 binary word")


def test_size_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(DocumentError, match="over 10 MB"):
        parse_document("big.txt", b"x" * 11)


def test_zip_bombs_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "MAX_ARCHIVE_UNCOMPRESSED", 1_000)
    bomb = _zip({"Positions.csv": "Company Name,Title\n" + "x" * 5_000})
    with pytest.raises(DocumentError, match="too large once unpacked"):
        parse_document("export.zip", bomb)


def test_pdf_without_text_layer() -> None:
    blank = (FIXTURES / "ada_example.pdf").read_bytes().replace(b"Tj T*", b"Tz T*")
    with pytest.raises(DocumentError, match="No text found"):
        parse_document("scan.pdf", blank)


def test_pdfplumber_fallback_when_pypdf_finds_little(monkeypatch: pytest.MonkeyPatch) -> None:
    import pypdf

    class Page:
        def extract_text(self) -> str:
            return ""

    class Reader:
        is_encrypted = False
        pages: ClassVar[list[Page]] = [Page()]

        def __init__(self, _stream: object) -> None:
            pass

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    parsed = parse_document("cv.pdf", (FIXTURES / "ada_example.pdf").read_bytes())
    assert "Northwind Payments" in parsed.text  # recovered by pdfplumber
