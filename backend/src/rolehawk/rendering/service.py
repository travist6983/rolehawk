"""Renders CVs and cover letters to DOCX and PDF with the user's chosen templates."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from rolehawk.config import Settings, update_settings
from rolehawk.paths import DataPaths
from rolehawk.profile.model import Profile
from rolehawk.rendering.docx_builder import cv_docx, letter_docx
from rolehawk.rendering.layout import cv_layout, letter_layout
from rolehawk.rendering.model import CoverLetter, CvDocument, DocumentKind
from rolehawk.rendering.pdf import PdfEngine
from rolehawk.rendering.samples import (
    SAMPLE_CONTACT,
    cv_from_profile,
    has_content,
    sample_cover_letter,
    sample_cv,
)
from rolehawk.rendering.templates import (
    Paper,
    TemplateManifest,
    UnknownTemplateError,
    builtin_templates,
    get_template,
    render_html,
)

Format = Literal["pdf", "docx"]
FORMATS: tuple[Format, ...] = ("pdf", "docx")
MEDIA_TYPES: dict[Format, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
# Letter in the Americas countries that use it; A4 everywhere else.
LETTER_COUNTRIES = {"US", "CA", "MX", "PH", "CL", "CO", "VE", "GT", "CR", "PA", "DO", "SV", "PR"}
DEFAULTS = {DocumentKind.CV: "classic", DocumentKind.COVER_LETTER: "classic-letter"}


class TemplateView(BaseModel):
    id: str
    name: str
    kind: DocumentKind
    description: str
    selected: bool


class DocumentSettingsView(BaseModel):
    cv_template: str
    cover_template: str
    paper: Paper
    paper_auto: bool = Field(description="Paper size follows the search country")
    templates: list[TemplateView]


class DocumentSettingsIn(BaseModel):
    cv_template: str | None = None
    cover_template: str | None = None
    paper: Literal["letter", "a4", "auto"] | None = None


class RenderedFile(BaseModel):
    format: Format
    path: str
    size: int


class Rendered(BaseModel):
    kind: DocumentKind
    template_id: str
    files: list[RenderedFile]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:60] or "document"


class DocumentService:
    def __init__(
        self,
        paths: DataPaths,
        settings: Callable[[], Settings],
        reload_settings: Callable[[], Settings],
        load_profile: Callable[[], Profile],
    ) -> None:
        self._paths = paths
        self._settings = settings
        self._reload = reload_settings
        self._load_profile = load_profile
        self.pdf = PdfEngine()

    # --- settings -----------------------------------------------------------------------

    def paper(self) -> Paper:
        settings = self._settings()
        if settings.documents.paper:
            return settings.documents.paper
        return "letter" if settings.search.country.upper() in LETTER_COUNTRIES else "a4"

    def template_for(self, kind: DocumentKind, template_id: str | None = None) -> TemplateManifest:
        """The requested template, else the user's choice, else the default."""
        docs = self._settings().documents
        chosen = docs.cv_template if kind is DocumentKind.CV else docs.cover_template
        for candidate in (template_id, chosen, DEFAULTS[kind]):
            if candidate:
                try:
                    return get_template(candidate, kind)
                except UnknownTemplateError:
                    if candidate == template_id:
                        raise
        raise UnknownTemplateError(DEFAULTS[kind])  # pragma: no cover - built-ins ship

    def settings_view(self) -> DocumentSettingsView:
        cv = self.template_for(DocumentKind.CV)
        cover = self.template_for(DocumentKind.COVER_LETTER)
        return DocumentSettingsView(
            cv_template=cv.id,
            cover_template=cover.id,
            paper=self.paper(),
            paper_auto=self._settings().documents.paper is None,
            templates=[
                TemplateView(
                    id=m.id,
                    name=m.name,
                    kind=m.kind,
                    description=m.description,
                    selected=m.id in (cv.id, cover.id),
                )
                for m in builtin_templates()
            ],
        )

    def update_settings(self, changes: DocumentSettingsIn) -> DocumentSettingsView:
        values: dict[str, str | None] = {}
        if changes.cv_template is not None:
            values["cv_template"] = get_template(changes.cv_template, DocumentKind.CV).id
        if changes.cover_template is not None:
            values["cover_template"] = get_template(
                changes.cover_template, DocumentKind.COVER_LETTER
            ).id
        if changes.paper is not None:
            values["paper"] = None if changes.paper == "auto" else changes.paper
        if values:
            update_settings(self._paths.config_file, "documents", values)
            self._reload()
        return self.settings_view()

    # --- rendering ----------------------------------------------------------------------

    async def render_cv(
        self, cv: CvDocument, template_id: str | None = None, formats: Sequence[Format] = FORMATS
    ) -> dict[Format, bytes]:
        manifest = self.template_for(DocumentKind.CV, template_id)
        layout = cv_layout(cv, manifest.style.heading_case)
        title = f"{layout.name} CV"
        out: dict[Format, bytes] = {}
        paper = self.paper()
        if "docx" in formats:
            out["docx"] = await asyncio.to_thread(cv_docx, layout, manifest.style, paper, title)
        if "pdf" in formats:
            html = render_html(manifest, layout, paper, title)
            out["pdf"] = await self.pdf.render(html, paper, title)
        return out

    async def render_letter(
        self,
        letter: CoverLetter,
        template_id: str | None = None,
        formats: Sequence[Format] = FORMATS,
    ) -> dict[Format, bytes]:
        manifest = self.template_for(DocumentKind.COVER_LETTER, template_id)
        layout = letter_layout(letter)
        title = f"{layout.name} cover letter"
        out: dict[Format, bytes] = {}
        paper = self.paper()
        if "docx" in formats:
            out["docx"] = await asyncio.to_thread(letter_docx, layout, manifest.style, paper, title)
        if "pdf" in formats:
            html = render_html(manifest, layout, paper, title)
            out["pdf"] = await self.pdf.render(html, paper, title)
        return out

    def _output_folder(self, folder: Path) -> Path:
        root = self._paths.generated_documents.resolve()
        target = folder.resolve()
        if target != root and root not in target.parents:
            raise ValueError("documents are only written inside documents/generated")
        target.mkdir(parents=True, exist_ok=True)
        return target

    async def write(
        self,
        doc: CvDocument | CoverLetter,
        folder: Path,
        basename: str,
        template_id: str | None = None,
        formats: Sequence[Format] = FORMATS,
    ) -> Rendered:
        """Render and save `<folder>/<basename>.pdf|.docx` (inside the data folder only)."""
        target = await asyncio.to_thread(self._output_folder, folder)
        if isinstance(doc, CvDocument):
            kind, manifest = DocumentKind.CV, self.template_for(DocumentKind.CV, template_id)
            rendered = await self.render_cv(doc, manifest.id, formats)
        else:
            kind = DocumentKind.COVER_LETTER
            manifest = self.template_for(kind, template_id)
            rendered = await self.render_letter(doc, manifest.id, formats)
        files: list[RenderedFile] = []
        for fmt, data in rendered.items():
            path = target / f"{_slug(basename)}.{fmt}"
            await asyncio.to_thread(path.write_bytes, data)
            files.append(RenderedFile(format=fmt, path=str(path), size=len(data)))
        return Rendered(kind=kind, template_id=manifest.id, files=files)

    # --- previews -----------------------------------------------------------------------

    def preview_data(self, kind: DocumentKind) -> CvDocument | CoverLetter:
        """The user's own CV when the profile has enough in it, else a sample person. Cover
        letters are always sample text (with the user's contact details when known)."""
        profile = self._load_profile()
        mine = has_content(profile)
        if kind is DocumentKind.CV:
            return cv_from_profile(profile) if mine else sample_cv()
        return sample_cover_letter(cv_from_profile(profile).contact if mine else SAMPLE_CONTACT)

    async def preview(self, template_id: str, fmt: Format) -> bytes:
        manifest = get_template(template_id)
        data = await asyncio.to_thread(self.preview_data, manifest.kind)
        if isinstance(data, CvDocument):
            return (await self.render_cv(data, manifest.id, [fmt]))[fmt]
        return (await self.render_letter(data, manifest.id, [fmt]))[fmt]

    async def aclose(self) -> None:
        await self.pdf.aclose()
