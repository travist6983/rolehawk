"""Runs a custom source in a separate Python process (`-I`: isolated, no user site or env
paths) with a minimal environment (no API keys or Offerbound settings), a scratch working
directory, and a hard timeout."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Mapping

from pydantic import BaseModel

from offerbound.portals.base import NormalizedJob
from offerbound.portals.custom.definition import (
    HtmlDefinition,
    JsonApiDefinition,
    JsonLdDefinition,
    RssDefinition,
)

Definition = RssDefinition | JsonLdDefinition | JsonApiDefinition | HtmlDefinition
TIMEOUT_S = 60.0
# Only what Python and the network stack need to start, on every OS.
_KEEP_ENV = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
             "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")  # fmt: skip


class SandboxResult(BaseModel):
    ok: bool
    jobs: list[NormalizedJob]
    errors: list[str]
    error: str | None = None


def clean_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ if source is None else source
    return {k: v for k, v in env.items() if k.upper() in _KEEP_ENV}


async def run_in_sandbox(
    definition: Definition,
    *,
    timeout_s: float = TIMEOUT_S,
    allow_private: bool = False,
    limit: int = 500,
) -> SandboxResult:
    payload = json.dumps(
        {
            "definition": definition.model_dump(mode="json"),
            "allow_private": allow_private,
            "limit": limit,
        }
    ).encode()
    with tempfile.TemporaryDirectory(prefix="offerbound-portal-") as scratch:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-m",
            "offerbound.portals.custom.runner",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=scratch,
            env=clean_env(),
        )
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(payload), timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            return SandboxResult(
                ok=False, jobs=[], errors=[], error=f"stopped after {timeout_s:.0f}s"
            )
    try:
        data = json.loads(stdout or b"{}")
    except ValueError:
        return SandboxResult(ok=False, jobs=[], errors=[], error="the source runner crashed")
    if "error" in data:
        return SandboxResult(ok=False, jobs=[], errors=[], error=str(data["error"]))
    return SandboxResult(
        ok=True,
        jobs=[NormalizedJob.model_validate(j) for j in data.get("jobs", [])],
        errors=[str(e) for e in data.get("errors", [])],
    )
