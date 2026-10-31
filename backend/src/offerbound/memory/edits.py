"""Pure text edits on markdown memory files, applied when a proposal is accepted."""

from __future__ import annotations

import re


class EditConflictError(ValueError):
    """The text a proposal expected is missing or ambiguous (the file changed since)."""


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _as_bullet(text: str) -> str:
    text = text.strip()
    return text if text.startswith(("-", "*", "#")) else f"- {text}"


def _line_body(line: str) -> str:
    return re.sub(r"^\s*[-*]\s+", "", line).strip()


def add(document: str, text: str, section: str | None = None) -> str:
    """Append `text` as a bullet at the end of `## section` (created if missing), or at the end
    of the document. Adding text that is already present is a no-op."""
    bullet = _as_bullet(text)
    if any(_line_body(line) == _line_body(bullet) for line in document.splitlines()):
        return document
    lines = document.rstrip("\n").split("\n")
    if section is None:
        return "\n".join([*lines, bullet]) + "\n"

    start = level = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(2).strip().lower() == section.strip().lower():
            start, level = index, len(match.group(1))
            break
    if start is None or level is None:
        return "\n".join([*lines, "", f"## {section.strip()}", "", bullet]) + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = _HEADING.match(lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    if insert_at == start + 1:  # empty section: keep a blank line after the heading
        new_lines = [*lines[: start + 1], "", bullet, *lines[end:]]
        if end < len(lines):
            new_lines.insert(start + 3, "")
    else:
        new_lines = [*lines[:insert_at], bullet, *lines[insert_at:]]
    return "\n".join(new_lines) + "\n"


def _locate(document: str, old: str) -> tuple[str, int]:
    old = old.strip()
    if not old:
        raise EditConflictError("empty text to match")
    lines = document.split("\n")
    line_hits = [i for i, line in enumerate(lines) if _line_body(line) == _line_body(old)]
    if len(line_hits) == 1:
        return "line", line_hits[0]
    count = document.count(old)
    if count == 1:
        return "substring", document.index(old)
    raise EditConflictError(
        "text not found" if count == 0 and not line_hits else "text matches more than once"
    )


def replace(document: str, old: str, new: str) -> str:
    kind, where = _locate(document, old)
    if kind == "line":
        lines = document.split("\n")
        prefix = re.match(r"^\s*(?:[-*]\s+)?", lines[where])
        lines[where] = f"{prefix.group(0) if prefix else ''}{_line_body(new)}"
        return "\n".join(lines)
    return document[:where] + new.strip() + document[where + len(old.strip()) :]


def remove(document: str, old: str) -> str:
    kind, where = _locate(document, old)
    if kind == "line":
        lines = document.split("\n")
        del lines[where]
        return "\n".join(lines)
    return document[:where] + document[where + len(old.strip()) :]
