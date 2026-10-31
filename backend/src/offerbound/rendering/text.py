"""Plain text back out of rendered files: for the DOCX/PDF parity tests and for checking a
generated document says only what its data said."""

from __future__ import annotations

import io
import re
import unicodedata
from collections import Counter

from docx import Document
from pypdf import PdfReader


def pdf_text(data: bytes) -> str:
    """Text in reading order. Lines that wrap after a hyphen are rejoined: templates never
    hyphenate automatically, so the hyphen is part of the word ("Keyboard-first")."""
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    return re.sub(r"(?<=\w-)\n(?=\w)", "", text)


def docx_text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


_WORD = re.compile(r"[\w@.+/:%'()-]+")


def words(text: str) -> Counter[str]:
    """Comparable words: Unicode-normalized, case-folded, surrounding punctuation trimmed, and
    separators like "|" or bullets dropped (they're layout, not content)."""
    text = unicodedata.normalize("NFKC", text).casefold()
    found = (w.strip(".,;:()'") for w in _WORD.findall(text))
    return Counter(w for w in found if any(c.isalnum() for c in w))
