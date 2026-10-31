from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Response

from offerbound.api.deps import RuntimeDep
from offerbound.rendering.pdf import PdfUnavailableError
from offerbound.rendering.service import MEDIA_TYPES, DocumentSettingsIn, DocumentSettingsView
from offerbound.rendering.templates import UnknownTemplateError

router = APIRouter(tags=["documents"])


@router.get("/api/documents/settings")
async def document_settings(runtime: RuntimeDep) -> DocumentSettingsView:
    """Templates, the chosen CV and cover letter templates, and the paper size."""
    return await asyncio.to_thread(runtime.documents.settings_view)


@router.patch("/api/documents/settings")
async def update_document_settings(
    body: DocumentSettingsIn, runtime: RuntimeDep
) -> DocumentSettingsView:
    try:
        return await asyncio.to_thread(runtime.documents.update_settings, body)
    except UnknownTemplateError:
        raise HTTPException(status_code=422, detail="Unknown template") from None


@router.get(
    "/api/templates/{template_id}/preview",
    response_class=Response,
    responses={200: {"content": {MEDIA_TYPES["pdf"]: {}, MEDIA_TYPES["docx"]: {}}}},
)
async def preview_template(
    template_id: str, runtime: RuntimeDep, format: Literal["pdf", "docx"] = "pdf"
) -> Response:
    """The template filled with your profile (or a sample person while it's empty)."""
    try:
        data = await runtime.documents.preview(template_id, format)
    except UnknownTemplateError:
        raise HTTPException(status_code=404, detail="Unknown template") from None
    except PdfUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.user_message) from None
    disposition = "inline" if format == "pdf" else "attachment"
    return Response(
        data,
        media_type=MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f'{disposition}; filename="{template_id}-preview.{format}"',
            "Cache-Control": "no-store",
        },
    )
