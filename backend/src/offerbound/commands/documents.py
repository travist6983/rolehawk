"""Document templates and previews (what skills and chat call)."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offerbound.commands.registry import CommandContext, CommandRegistry, CommandSpec, NoParams
from offerbound.rendering.model import DocumentKind


class PreviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: DocumentKind = DocumentKind.CV
    template_id: str | None = Field(default=None, description="Default: the chosen template")


async def _templates(ctx: CommandContext, _params: NoParams) -> dict[str, Any]:
    view = await asyncio.to_thread(ctx.runtime.documents.settings_view)
    return view.model_dump(mode="json")


async def _document_preview(ctx: CommandContext, params: PreviewParams) -> dict[str, Any]:
    documents = ctx.runtime.documents
    data = await asyncio.to_thread(documents.preview_data, params.kind)
    manifest = documents.template_for(params.kind, params.template_id)
    folder = ctx.runtime.paths.generated_documents / "previews"
    rendered = await documents.write(
        data, folder, f"{params.kind.value}-{manifest.id}", manifest.id
    )
    return rendered.model_dump(mode="json")


def register_documents(registry: CommandRegistry) -> None:
    registry.register(
        CommandSpec(
            "templates",
            "List CV and cover letter templates, the ones in use, and the paper size.",
            _templates,
        )
    )
    registry.register(
        CommandSpec(
            "document-preview",
            "Render the profile's CV (or a sample cover letter) with a template to DOCX and "
            "PDF under documents/generated/previews, and return the file paths.",
            _document_preview,
            PreviewParams,
            read_only=False,
        )
    )
