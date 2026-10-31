from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _strictify(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _strictify(v) for k, v in node.items() if k not in ("title", "default")}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    return node


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema for a `strict: true` tool: every object closed, every property required
    (optional values are expressed as nullable types). Inputs are still validated with the
    pydantic model on arrival."""
    schema: dict[str, Any] = _strictify(model.model_json_schema())
    return schema
