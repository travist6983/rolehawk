"""Subprocess entry point: `python -I -m rolehawk.portals.custom.runner`.

Reads {"definition": ..., "allow_private": bool, "limit": int} as JSON on stdin and writes
{"jobs": [...], "errors": [...]} (or {"error": "..."}) as JSON on stdout. It runs in a
separate process with a clean environment and a timeout (see sandbox.py)."""

from __future__ import annotations

import json
import sys

from pydantic import ValidationError

from rolehawk.portals.custom.definition import DefinitionEnvelope, UnsafeUrlError
from rolehawk.portals.custom.engine import EngineError, run_definition


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        definition = DefinitionEnvelope.model_validate(
            {"definition": request["definition"]}
        ).definition
        jobs, errors = run_definition(
            definition,
            allow_private=bool(request.get("allow_private", False)),
            limit=int(request.get("limit", 500)),
        )
    except (EngineError, UnsafeUrlError, ValidationError, ValueError, KeyError) as exc:
        json.dump({"error": f"{type(exc).__name__}: {exc}"[:500]}, sys.stdout)
        return 1
    except Exception as exc:  # report anything, never a traceback with local paths
        json.dump({"error": f"{type(exc).__name__}: {str(exc)[:300]}"}, sys.stdout)
        return 1
    json.dump(
        {"jobs": [j.model_dump(mode="json") for j in jobs], "errors": errors[:20]}, sys.stdout
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
