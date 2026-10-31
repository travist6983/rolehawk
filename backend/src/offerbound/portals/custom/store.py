"""Custom sources on disk: <data>/portals/<id>.py, generated from a template. The file
holds the definition as a literal and is read with ast.literal_eval, never imported or
executed, so editing it can't run code inside Offerbound."""

from __future__ import annotations

import ast
import json
import logging
import pprint
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from offerbound.portals.custom.definition import DefinitionEnvelope
from offerbound.portals.custom.sandbox import Definition

log = logging.getLogger(__name__)

PREFIX = "custom-"

TEMPLATE = '''"""Custom job source: {name}

Added with /add-portal on {day} from {source_url}
How it reads jobs: {how}

This file is data, not code. Offerbound reads DEFINITION with ast.literal_eval (it never
imports this file) and runs it with its own engine in a separate process with a timeout,
fetching only from {domain}. Edit the values to adjust the source; delete the file to
remove it.
"""

DEFINITION = {literal}
'''

HOW = {
    "rss": "the site's RSS/Atom job feed",
    "jsonld": "JobPosting structured data (JSON-LD)",
    "json_api": "the site's JSON job list",
    "html": "CSS selectors on the careers page",
}


def portal_id(definition_id: str) -> str:
    return f"{PREFIX}{definition_id}"


def plugin_source(definition: Definition, day: date | None = None) -> str:
    data = definition.model_dump(mode="json", exclude_none=True)
    return TEMPLATE.format(
        name=definition.name.replace('"""', "'''"),
        day=(day or date.today()).isoformat(),
        source_url=definition.source_url,
        how=HOW[definition.kind],
        domain=definition.domain,
        literal=pprint.pformat(data, width=88, sort_dicts=False),
    )


def parse_plugin(source: str) -> Definition:
    """The DEFINITION literal from a plugin file, validated. Raises ValueError."""
    tree = ast.parse(source)
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "DEFINITION"
        ):
            value = ast.literal_eval(node.value)
            try:
                return DefinitionEnvelope.model_validate({"definition": value}).definition
            except ValidationError as exc:
                raise ValueError(str(exc)) from exc
    raise ValueError("no DEFINITION in the plugin file")


class PluginFiles:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def path(self, definition_id: str) -> Path:
        return self.folder / f"{definition_id}.py"

    def save(self, definition: Definition) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.path(definition.id)
        path.write_text(plugin_source(definition), encoding="utf-8")
        return path

    def load_all(self) -> list[Definition]:
        found: list[Definition] = []
        if not self.folder.is_dir():
            return found
        for path in sorted(self.folder.glob("*.py")):
            try:
                definition = parse_plugin(path.read_text(encoding="utf-8"))
            except (ValueError, SyntaxError) as exc:
                log.warning("skipping custom source %s: %s", path.name, exc)
                continue
            if definition.id == path.stem:
                found.append(definition)
        return found

    def remove(self, definition_id: str) -> bool:
        path = self.path(definition_id)
        if path.is_file():
            path.unlink()
            return True
        return False


def definition_json(definition: Definition) -> str:
    return json.dumps(definition.model_dump(mode="json", exclude_none=True), indent=2)
