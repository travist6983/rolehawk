from __future__ import annotations

from dataclasses import dataclass
from functools import cache
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


# Structured outputs compile the schema into a grammar and refuse big ones with a 400
# ("Schema is too complex for compilation"). Documented limits, totaled across the request
# (https://platform.claude.com/docs/en/build-with-claude/structured-outputs, 2026-11-01).
MAX_OPTIONAL_FIELDS = 24
MAX_UNION_FIELDS = 16

# The API also refuses a schema whose compiled grammar is too big ("The compiled grammar is too
# large"). That limit isn't published and depends on more than one count, so this is a budget
# with headroom, not the real line: resume extraction as one schema was refused at 48 and 49
# properties and accepted at 47 (Haiku 5.5 and Opus 5.5, 2026-11-01). Split anything bigger
# into several requests.
MAX_PROPERTIES = 40


@dataclass(frozen=True)
class SchemaComplexity:
    optional: int  # properties not listed in `required`
    unions: int  # properties using anyOf or a type array (nullable fields count)
    properties: int  # every property, nested ones included

    @property
    def ok(self) -> bool:
        return (
            self.optional <= MAX_OPTIONAL_FIELDS
            and self.unions <= MAX_UNION_FIELDS
            and self.properties <= MAX_PROPERTIES
        )


def schema_complexity(schema: dict[str, Any]) -> SchemaComplexity:
    """Count the way the API does, expanding each `$ref` where it is used (a conservative
    upper bound when one definition is referenced twice)."""
    defs: dict[str, Any] = schema.get("$defs", {})
    optional = unions = properties = 0

    def walk(node: Any, seen: frozenset[str]) -> None:
        nonlocal optional, unions, properties
        if isinstance(node, list):
            for item in node:
                walk(item, seen)
            return
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen and name in defs:
                walk(defs[name], seen | {name})
            return
        props = node.get("properties")
        if isinstance(props, dict):
            required = set(node.get("required", []))
            properties += len(props)
            for key, value in props.items():
                if key not in required:
                    optional += 1
                if isinstance(value, dict) and (
                    "anyOf" in value or isinstance(value.get("type"), list)
                ):
                    unions += 1
        for key, value in node.items():
            if key != "$defs":
                walk(value, seen)

    walk(schema, frozenset())
    return SchemaComplexity(optional=optional, unions=unions, properties=properties)


@cache
def check_output_schema(model: type[BaseModel]) -> SchemaComplexity:
    """Raise before sending a structured-output schema the API would refuse."""
    found = schema_complexity(model.model_json_schema())
    if not found.ok:
        raise ValueError(
            f"{model.__name__} is too complex for structured outputs: {found.optional} optional "
            f"fields (max {MAX_OPTIONAL_FIELDS}), {found.unions} nullable/union fields "
            f"(max {MAX_UNION_FIELDS}), and {found.properties} properties in all "
            f"(max {MAX_PROPERTIES}). Make fields required and use empty values instead, "
            "or split the schema across several requests."
        )
    return found
