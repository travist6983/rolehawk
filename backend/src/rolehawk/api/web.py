"""Serves the prebuilt frontend (single-page app) from the same origin as the API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

ENV_WEB_DIR = "ROLEHAWK_WEB_DIR"

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>RoleHawk</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">
<h1>The dashboard isn't built yet</h1>
<p>Run <code>npm run build</code> in <code>frontend/</code>, or use the dev server with
<code>uv run poe dev</code> and <code>npm run dev</code>.</p></body>"""


def find_web_dir() -> Path | None:
    """$ROLEHAWK_WEB_DIR if set (and only it), else the release bundle (rolehawk/web),
    else a source checkout's frontend/dist."""
    override = os.environ.get(ENV_WEB_DIR)
    if override:
        candidates = [Path(override)]
    else:
        here = Path(__file__).resolve()
        candidates = [here.parents[1] / "web", here.parents[4] / "frontend" / "dist"]
    return next((c.resolve() for c in candidates if (c / "index.html").is_file()), None)


def mount_web(app: FastAPI, web_dir: Path | None) -> None:
    """Register last: unknown non-API paths fall back to index.html for client routing."""

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        if web_dir is None:
            return HTMLResponse(NOT_BUILT)
        candidate = (web_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(web_dir):
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else None
            headers = {"Cache-Control": cache} if cache else None
            return FileResponse(candidate, headers=headers)
        return FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-cache"})
