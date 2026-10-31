"""Turn uploaded files into text (resumes) or a structured profile (LinkedIn exports).

Files are untrusted: sizes are capped, archives are inspected without extracting to disk, and
only known LinkedIn CSVs are read."""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum

from offerbound.profile.linkedin import LINKEDIN_FILES, parse_linkedin_export
from offerbound.profile.model import Profile

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2_000
MAX_TEXT_CHARS = 200_000
MIN_PDF_TEXT = 200  # below this, pypdf probably missed the text layer; try pdfplumber


class DocumentKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "text"
    LINKEDIN = "linkedin"


class DocumentError(ValueError):
    """The file can't be used; the message is safe to show the user."""

    @property
    def user_message(self) -> str:
        return str(self)


@dataclass
class ParsedDocument:
    kind: DocumentKind
    text: str
    profile: Profile | None = None  # set for structured imports (LinkedIn)
    warnings: list[str] = field(default_factory=list)


def _check_archive(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise DocumentError("That archive has too many files.")
    if sum(info.file_size for info in infos) > MAX_ARCHIVE_UNCOMPRESSED:
        raise DocumentError("That archive is too large once unpacked.")


def _pdf_text(data: bytes) -> tuple[str, list[str]]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    warnings: list[str] = []
    text = ""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("That PDF is password protected. Export an unlocked copy.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as exc:
        log.info("pypdf could not read the PDF: %s", exc)
    if len(text.strip()) < MIN_PDF_TEXT:
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                fallback = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as exc:  # pdfplumber raises many types for malformed files
            log.info("pdfplumber could not read the PDF: %s", exc)
            fallback = ""
        if len(fallback.strip()) > len(text.strip()):
            text = fallback
    if not text.strip():
        raise DocumentError(
            "No text found in that PDF. If it's a scan, upload the original document or paste "
            "your CV text instead."
        )
    if len(text.strip()) < MIN_PDF_TEXT:
        warnings.append("Very little text was found in that PDF; check the result carefully.")
    return text, warnings


def _docx_text(data: bytes) -> str:
    from docx import Document

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        _check_archive(archive)
    document = Document(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                lines.append(" | ".join(dict.fromkeys(cells)))  # merged cells repeat
    return "\n".join(lines)


def _decode(data: bytes) -> str | None:
    """Text files only: UTF-16 needs its BOM, and NUL bytes otherwise mean binary."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentError("That file is over 10 MB.")
    if not data:
        raise DocumentError("That file is empty.")
    name = filename.lower()

    if data.startswith(b"%PDF"):
        text, warnings = _pdf_text(data)
        return ParsedDocument(DocumentKind.PDF, text[:MAX_TEXT_CHARS], warnings=warnings)

    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                _check_archive(archive)
                names = {n.rsplit("/", 1)[-1] for n in archive.namelist()}
                if "word/document.xml" in archive.namelist():
                    kind = DocumentKind.DOCX
                elif names & LINKEDIN_FILES:
                    profile, summary = parse_linkedin_export(archive)
                    return ParsedDocument(DocumentKind.LINKEDIN, summary, profile=profile)
                else:
                    raise DocumentError(
                        "That ZIP isn't a LinkedIn data export (no Positions.csv or Profile.csv)."
                    )
        except zipfile.BadZipFile as exc:
            raise DocumentError("That file looks damaged; it couldn't be opened.") from exc
        if kind is DocumentKind.DOCX:
            return ParsedDocument(DocumentKind.DOCX, _docx_text(data)[:MAX_TEXT_CHARS])

    if name.endswith((".doc", ".pages", ".rtf", ".odt")):
        raise DocumentError("Save it as PDF or DOCX first, or paste the text.")
    decoded = _decode(data)
    sample = (decoded or "")[:5000]
    printable = sum(ch.isprintable() or ch.isspace() for ch in sample)
    if decoded is None or printable < 0.9 * len(sample):
        raise DocumentError("That file type isn't supported. Upload a PDF, DOCX, TXT, or ZIP.")
    return ParsedDocument(DocumentKind.TEXT, decoded[:MAX_TEXT_CHARS])
