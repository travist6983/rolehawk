"""Built-in document templates: a manifest (name, kind, style) plus a Jinja2 HTML file per
template. The DOCX builder reads the same style, so both formats look alike."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from offerbound.rendering.layout import SEPARATOR, CvLayout, LetterLayout
from offerbound.rendering.model import DocumentKind

BUILTIN_DIR = Path(__file__).parent / "templates"
Paper = Literal["letter", "a4"]


class TemplateStyle(BaseModel):
    """Every value lands in CSS or DOCX formatting, so each one is tightly constrained."""

    model_config = ConfigDict(extra="forbid")

    font: str = Field(pattern=r"^[A-Za-z0-9 ]{1,40}$", description="DOCX font name")
    font_stack: str = Field(pattern=r"^[A-Za-z0-9 ,-]{1,200}$", description="CSS font-family")
    body_pt: float = Field(ge=8, le=14)
    name_pt: float = Field(ge=12, le=32)
    heading_pt: float = Field(ge=8, le=18)
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    heading_case: Literal["upper", "title"]
    name_align: Literal["left", "center"]
    heading_rule: bool
    margin_in: float = Field(ge=0.4, le=1.5)
    line_height: float = Field(ge=1.0, le=2.0)


class TemplateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    name: str
    kind: DocumentKind
    description: str
    style: TemplateStyle


class UnknownTemplateError(KeyError):
    pass


@cache
def builtin_templates() -> tuple[TemplateManifest, ...]:
    manifests = []
    for path in sorted(BUILTIN_DIR.glob("*/manifest.json")):
        manifest = TemplateManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if manifest.id != path.parent.name:
            raise ValueError(f"template folder {path.parent.name} has id {manifest.id}")
        manifests.append(manifest)
    order = {"classic": 0, "modern": 1, "compact": 2, "classic-letter": 3, "modern-letter": 4}
    return tuple(sorted(manifests, key=lambda m: (order.get(m.id, 99), m.id)))


def get_template(template_id: str, kind: DocumentKind | None = None) -> TemplateManifest:
    for manifest in builtin_templates():
        if manifest.id == template_id and (kind is None or manifest.kind is kind):
            return manifest
    raise UnknownTemplateError(template_id)


@cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(BUILTIN_DIR),
        autoescape=select_autoescape(default=True, default_for_string=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(
    manifest: TemplateManifest, doc: CvLayout | LetterLayout, paper: Paper, title: str
) -> str:
    template = _environment().get_template(f"{manifest.id}/template.html.j2")
    return template.render(
        doc=doc,
        style=manifest.style,
        paper="Letter" if paper == "letter" else "A4",
        title=title,
        separator=SEPARATOR,
    )
