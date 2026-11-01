"""CV and cover letter rendering: shared layout, DOCX/PDF content parity for every template,
ATS-friendliness, escaping, offline rendering, paper sizes, settings, the API, and commands.

PDF tests use Playwright's headless Chromium (`uv run playwright install --only-shell
chromium`; CI installs it)."""

from __future__ import annotations

import asyncio
import io
import threading
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from offerbound.apply.ats import parse_checks
from offerbound.install.layout import browser_hint
from offerbound.profile.model import Contact, Experience, Profile
from offerbound.rendering.docx_builder import cv_docx, letter_docx
from offerbound.rendering.layout import (
    Bullets,
    Entry,
    Paragraph,
    cv_layout,
    letter_layout,
    month_year,
    period,
)
from offerbound.rendering.model import (
    CoverLetter,
    CvContact,
    CvDocument,
    CvEducation,
    CvRole,
    CvSection,
    DocumentKind,
)
from offerbound.rendering.pdf import PdfEngine, PdfUnavailableError
from offerbound.rendering.samples import sample_cover_letter, sample_cv
from offerbound.rendering.service import DocumentSettingsIn
from offerbound.rendering.templates import (
    Paper,
    TemplateManifest,
    builtin_templates,
    render_html,
)
from offerbound.rendering.text import docx_text, pdf_text, words
from offerbound.services.runtime import Runtime

pytestmark = pytest.mark.anyio


def tricky_cv() -> CvDocument:
    """Accents, symbols, markup-looking text, and enough bullets to run onto page two."""
    return CvDocument(
        contact=CvContact(
            name="Zoë O'Brien-Núñez",
            email="zoe@example.com",
            location="São Paulo, Brazil",
            links=["github.com/zoe"],
        ),
        headline="Data & Analytics Lead",
        summary=(
            "I write <script>alert('x')</script> and SQL; R&D at 3\N{MULTIPLICATION SIGN} scale."
        ),
        experience=[
            CvRole(
                title=f"Analytics Lead {i}",
                organization="Müller & Söhne GmbH",
                location="Berlin",
                start=f"20{10 + i}-0{1 + i % 9}",
                end=f"20{11 + i}",
                bullets=[
                    f"Grew revenue {i * 7}% by modelling churn — point {j}." for j in range(5)
                ],
            )
            for i in range(8)
        ],
        education=[CvEducation(institution="Universidade de São Paulo", degree="MSc")],
        skills=["Python", "SQL", "dbt", "Looker"],
        section_order=[CvSection.SKILLS, CvSection.SUMMARY, CvSection.EXPERIENCE],
    )


@dataclass(frozen=True)
class Rendered:
    manifest: TemplateManifest
    paper: Paper
    html: str
    pdf: bytes
    docx: bytes
    expected: str  # every word the layout says should appear


def _expected_text(doc: CvDocument | CoverLetter, manifest: TemplateManifest) -> str:
    if isinstance(doc, CvDocument):
        layout = cv_layout(doc, manifest.style.heading_case)
        parts = [layout.name, layout.headline or "", layout.contact_text or ""]
        for section in layout.sections:
            parts.append(section.title)
            for block in section.blocks:
                if isinstance(block, Paragraph):
                    parts.append(block.text)
                elif isinstance(block, Bullets):
                    parts.extend(block.items)
                elif isinstance(block, Entry):
                    parts += [block.title, block.subtitle or "", block.dates or "", *block.bullets]
        return "\n".join(parts)
    letter = letter_layout(doc)
    return "\n".join(
        [
            letter.name,
            letter.contact_text or "",
            letter.date or "",
            *letter.recipient,
            letter.greeting,
            *letter.paragraphs,
            letter.closing,
            letter.signature,
        ]
    )


async def _render_all() -> dict[str, Rendered]:
    engine = PdfEngine()
    out: dict[str, Rendered] = {}
    try:
        for manifest in builtin_templates():
            docs: list[tuple[str, CvDocument | CoverLetter]]
            if manifest.kind is DocumentKind.CV:
                docs = [("sample", sample_cv()), ("tricky", tricky_cv())]
            else:
                docs = [("sample", sample_cover_letter())]
            for label, doc in docs:
                papers: tuple[Paper, ...] = ("letter", "a4")
                for paper in papers:
                    if isinstance(doc, CvDocument):
                        layout = cv_layout(doc, manifest.style.heading_case)
                        docx = cv_docx(layout, manifest.style, paper, "t")
                        html = render_html(manifest, layout, paper, "t")
                    else:
                        letter = letter_layout(doc)
                        docx = letter_docx(letter, manifest.style, paper, "t")
                        html = render_html(manifest, letter, paper, "t")
                    pdf = await engine.render(html, paper, "t")
                    out[f"{manifest.id}/{label}/{paper}"] = Rendered(
                        manifest, paper, html, pdf, docx, _expected_text(doc, manifest)
                    )
    finally:
        await engine.aclose()
    return out


@pytest.fixture(scope="module")
def rendered() -> dict[str, Rendered]:
    """Every template x sample x paper size, rendered once with one browser."""
    return asyncio.run(_render_all())


KEYS = [
    f"{m.id}/{label}/{paper}"
    for m in builtin_templates()
    for label in (("sample", "tricky") if m.kind is DocumentKind.CV else ("sample",))
    for paper in ("letter", "a4")
]


# --- layout -------------------------------------------------------------------------------


def test_dates_and_periods() -> None:
    assert month_year("2021-03") == "Mar 2021"
    assert month_year("2021") == "2021"
    assert month_year("Spring 2020") == "Spring 2020"
    assert period("2021-03", None, current=True) == "Mar 2021 - Present"
    assert period("2020", "2020") == "2020"
    assert period(None, "2019-12") == "Dec 2019"
    assert period(None, None) is None


def test_layout_follows_section_order_and_skips_empty_sections() -> None:
    layout = cv_layout(tricky_cv(), "upper")
    assert [s.title for s in layout.sections] == ["SKILLS", "SUMMARY", "EXPERIENCE"]
    assert layout.contact == ("zoe@example.com", "São Paulo, Brazil", "github.com/zoe")
    first = layout.sections[2].blocks[0]
    assert isinstance(first, Entry)
    assert first.subtitle == "Müller & Söhne GmbH, Berlin"

    bare = cv_layout(CvDocument(contact=CvContact(name="A\x00 B ")), "title")
    assert bare.name == "A B"
    assert bare.sections == ()


def test_all_templates_load() -> None:
    ids = [m.id for m in builtin_templates()]
    assert ids == ["classic", "modern", "compact", "classic-letter", "modern-letter"]
    assert {m.kind for m in builtin_templates()} == {DocumentKind.CV, DocumentKind.COVER_LETTER}


# --- DOCX/PDF parity (the snapshot test) --------------------------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_docx_and_pdf_say_the_same_thing(rendered: dict[str, Rendered], key: str) -> None:
    r = rendered[key]
    expected = words(r.expected)
    assert words(pdf_text(r.pdf)) == expected
    assert words(docx_text(r.docx)) == expected


@pytest.mark.parametrize("key", [k for k in KEYS if k.endswith("/sample/letter")])
def test_reading_order_is_top_to_bottom(rendered: dict[str, Rendered], key: str) -> None:
    r = rendered[key]
    text = pdf_text(r.pdf)
    first_line = text.strip().splitlines()[0]
    assert first_line.strip() == "Ada Example"
    if r.manifest.kind is DocumentKind.CV:
        headings = [
            line.strip()
            for line in text.splitlines()
            if line.strip().casefold() in {"summary", "experience", "education", "skills"}
        ]
        assert [h.casefold() for h in headings] == ["summary", "experience", "education", "skills"]


# --- ATS-friendliness ---------------------------------------------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_outputs_are_ats_friendly(rendered: dict[str, Rendered], key: str) -> None:
    r = rendered[key]
    text = pdf_text(r.pdf)
    assert not any("ﬀ" <= c <= "ﬆ" for c in text), "ligatures break words for parsers"

    archive = zipfile.ZipFile(io.BytesIO(r.docx))
    body = archive.read("word/document.xml").decode()
    assert "<w:tbl>" not in body  # no tables
    assert "txbxContent" not in body  # no text boxes
    assert "<w:drawing" not in body  # no images
    styles = archive.read("word/styles.xml").decode()
    assert "asciiTheme" not in styles.split('w:styleId="Heading1"')[1].split("</w:style>")[0]
    doc = Document(io.BytesIO(r.docx))
    assert doc.paragraphs[0].style is not None
    assert doc.paragraphs[0].style.name == "Title"
    if r.manifest.kind is DocumentKind.CV:
        assert any(p.style is not None and p.style.name == "Heading 1" for p in doc.paragraphs)


CV_KEYS = [
    f"{m.id}/{label}/{paper}"
    for m in builtin_templates()
    if m.kind is DocumentKind.CV
    for label in ("sample", "tricky")
    for paper in ("letter", "a4")
]


@pytest.mark.parametrize("key", CV_KEYS)
def test_cvs_pass_the_ats_parse_checks(rendered: dict[str, Rendered], key: str) -> None:
    r = rendered[key]
    cv = tricky_cv() if "/tricky/" in key else sample_cv()
    for text in (pdf_text(r.pdf), docx_text(r.docx)):
        failed = [c for c in parse_checks(cv, text) if not c.passed]
        assert failed == [], failed


def test_long_cvs_flow_onto_more_pages(rendered: dict[str, Rendered]) -> None:
    assert len(PdfReader(io.BytesIO(rendered["compact/tricky/letter"].pdf)).pages) >= 2


def test_text_is_escaped_not_executed(rendered: dict[str, Rendered]) -> None:
    r = rendered["modern/tricky/letter"]
    assert "<script>" not in r.html
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;" in r.html
    assert "<script>alert('x')</script>" in pdf_text(r.pdf).replace("\n", " ")


@pytest.mark.parametrize(("paper", "size"), [("letter", (612, 792)), ("a4", (595, 842))])
def test_paper_sizes(rendered: dict[str, Rendered], paper: str, size: tuple[int, int]) -> None:
    r = rendered[f"classic/sample/{paper}"]
    box = PdfReader(io.BytesIO(r.pdf)).pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == size
    section = Document(io.BytesIO(r.docx)).sections[0]
    assert section.page_width is not None
    assert round(section.page_width.pt) == size[0]


# --- the PDF engine -----------------------------------------------------------------------


@pytest.fixture
def local_server() -> Iterator[tuple[str, list[str]]]:
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", hits
    server.shutdown()
    server.server_close()


async def test_rendering_is_offline_and_script_free(local_server: tuple[str, list[str]]) -> None:
    base, hits = local_server
    html = (
        f'<html><body><img src="{base}/pixel.png"><link rel="stylesheet" href="{base}/x.css">'
        f'<script>fetch("{base}/js")</script><p>Rendered</p></body></html>'
    )
    engine = PdfEngine()
    try:
        pdf = await engine.render(html, "letter", "t")
    finally:
        await engine.aclose()
    assert "Rendered" in pdf_text(pdf)
    assert hits == []


async def test_missing_chromium_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from playwright.async_api import BrowserType
    from playwright.async_api import Error as PlaywrightError

    async def broken(*_args: object, **_kwargs: object) -> None:
        raise PlaywrightError("Executable doesn't exist at /nowhere\nmore detail")

    monkeypatch.setattr(BrowserType, "launch", broken)
    engine = PdfEngine()
    try:
        with pytest.raises(PdfUnavailableError) as info:
            await engine.render("<p>x</p>", "letter", "t")
    finally:
        await engine.aclose()
    assert "offerbound doctor" in info.value.user_message
    assert browser_hint().startswith("uv run playwright install")  # a source checkout


# --- the service --------------------------------------------------------------------------


async def test_settings_choose_templates_and_paper(runtime: Runtime) -> None:
    docs = runtime.documents
    view = docs.settings_view()
    assert (view.cv_template, view.cover_template, view.paper, view.paper_auto) == (
        "classic",
        "classic-letter",
        "letter",
        True,
    )
    assert [t.id for t in view.templates if t.selected] == ["classic", "classic-letter"]

    updated = docs.update_settings(DocumentSettingsIn(cv_template="compact", paper="a4"))
    assert (updated.cv_template, updated.paper, updated.paper_auto) == ("compact", "a4", False)
    assert 'cv_template = "compact"' in runtime.paths.config_file.read_text(encoding="utf-8")

    auto = docs.update_settings(DocumentSettingsIn(paper="auto"))
    assert auto.paper == "letter"
    runtime.settings.search.country = "DE"
    assert docs.paper() == "a4"

    with pytest.raises(KeyError):
        docs.update_settings(DocumentSettingsIn(cv_template="modern-letter"))  # wrong kind


async def test_previews_use_the_profile_when_it_has_content(runtime: Runtime) -> None:
    docs = runtime.documents
    sample = docs.preview_data(DocumentKind.CV)
    assert isinstance(sample, CvDocument)
    assert sample.contact.name == "Ada Example"

    runtime.profiles.save_profile(
        Profile(
            contact=Contact(name="Grace Hopper", email="grace@example.com"),
            experience=[Experience(title="Rear Admiral", company="US Navy", highlights=["COBOL"])],
        )
    )
    mine = docs.preview_data(DocumentKind.CV)
    assert isinstance(mine, CvDocument)
    assert mine.contact.name == "Grace Hopper"
    assert mine.experience[0].bullets == ["COBOL"]
    letter = docs.preview_data(DocumentKind.COVER_LETTER)
    assert isinstance(letter, CoverLetter)
    assert letter.contact.name == "Grace Hopper"

    pdf = await docs.preview("modern", "pdf")
    assert "Grace Hopper" in pdf_text(pdf)
    docx = await docs.preview("modern-letter", "docx")
    assert "Grace Hopper" in docx_text(docx)


def _size(path: str) -> int:
    return Path(path).stat().st_size


async def test_write_saves_files_inside_generated_only(runtime: Runtime) -> None:
    docs = runtime.documents
    folder = runtime.paths.generated_documents / "app-1"
    result = await docs.write(sample_cv(), folder, "Ada Example CV", formats=["docx"])
    assert result.template_id == "classic"
    (saved,) = result.files
    assert Path(saved.path) == folder / "ada-example-cv.docx"
    assert saved.size == _size(saved.path)

    with pytest.raises(ValueError, match="only written inside"):
        await docs.write(sample_cv(), runtime.paths.root / "elsewhere", "cv", formats=["docx"])
    with pytest.raises(ValueError, match="only written inside"):
        await docs.write(sample_cv(), folder / ".." / ".." / "..", "cv", formats=["docx"])


# --- API and commands ---------------------------------------------------------------------


def runtime_of(client: TestClient) -> Runtime:
    runtime: Runtime = cast(FastAPI, client.app).state.runtime
    return runtime


def test_documents_api(client: TestClient) -> None:
    settings = client.get("/api/documents/settings").json()
    assert settings["cv_template"] == "classic"
    assert len(settings["templates"]) == 5

    changed = client.patch("/api/documents/settings", json={"cover_template": "modern-letter"})
    assert changed.json()["cover_template"] == "modern-letter"
    bad = client.patch("/api/documents/settings", json={"cv_template": "nope"})
    assert bad.status_code == 422

    pdf = client.get("/api/templates/modern/preview")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline")
    assert pdf.content.startswith(b"%PDF")
    docx = client.get("/api/templates/classic-letter/preview", params={"format": "docx"})
    assert docx.headers["content-disposition"].startswith("attachment")
    assert docx.content.startswith(b"PK")
    assert client.get("/api/templates/nope/preview").status_code == 404


def test_preview_explains_missing_chromium(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(*_args: object, **_kwargs: object) -> bytes:
        raise PdfUnavailableError("no browser")

    monkeypatch.setattr(runtime_of(client).documents.pdf, "render", unavailable)
    response = client.get("/api/templates/classic/preview")
    assert response.status_code == 503
    assert "doctor" in response.json()["detail"]


def test_template_commands(client: TestClient) -> None:
    listed = client.post("/api/commands/templates", json={"params": {}}).json()["result"]
    assert listed["paper"] == "letter"
    preview = client.post(
        "/api/commands/document-preview",
        json={"params": {"kind": "cv", "template_id": "compact"}},
    ).json()["result"]
    assert preview["template_id"] == "compact"
    paths = {f["format"]: Path(f["path"]) for f in preview["files"]}
    assert paths["pdf"].name == "cv-compact.pdf"
    assert paths["pdf"].parent.name == "previews"
    assert paths["docx"].read_bytes().startswith(b"PK")
