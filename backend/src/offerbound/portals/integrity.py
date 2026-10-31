"""The integrity check for job postings: remove what a reader can't see, quote what targets AI.

A posting is third-party text that sits next to the user's profile in every prompt. The
<untrusted_content> wrapper (llm/prompting.py) is an instruction Claude follows; this module is
the deterministic layer under it, run on every description before it's stored:

- Hidden HTML is removed from the text: the `hidden` attribute, aria-hidden, display:none,
  visibility:hidden, opacity:0, zero font size, transparent text, clipped, zero-size, or
  off-screen boxes. Its words are still scanned, and links that only exist there are listed.
  template, noscript, svg, iframe, object, and comments are removed and scanned but not listed
  (pages use them for ordinary reasons); script and style are dropped.
- Invisible characters that can carry or hide text are removed and counted: Unicode tag
  characters and long variation-selector runs (both spell text a model reads and a person
  doesn't; it's decoded and quoted), bidi overrides, and zero-width characters inside words.
  Harmless ones (soft hyphens, BOMs, stray zero-width spaces) are removed silently. Emoji
  selectors and joiners, flag sequences, and joiners in non-Latin scripts are kept.
- Lines that address AI tools ("ignore previous instructions", "if you are an LLM", "include
  the word X in your cover letter") are quoted, never removed: the user decides what they mean.
- Words that mix Latin with Cyrillic or Greek letters (look-alike spoofing) are listed.

It advises and never blocks. Class-based hiding (CSS classes) can't be seen without the page's
stylesheet, so it isn't detected.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_DESCRIPTION_CHARS = 50_000
MAX_ITEMS = 5
MAX_QUOTE = 200
MAX_EXCERPT = 160

Verdict = Literal["clean", "cleaned", "warning"]


class PostingIntegrity(BaseModel):
    """What the check removed or found in one posting. Empty means nothing to report."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    hidden_blocks: int = Field(default=0, description="Hidden HTML blocks with text, removed")
    hidden_excerpts: list[str] = Field(default_factory=list, description="Their first words")
    hidden_urls: list[str] = Field(default_factory=list, description="Links only in hidden text")
    invisible_chars: int = Field(
        default=0, description="Removed characters that can carry or hide text"
    )
    tampering: list[str] = Field(default_factory=list, description="Why those look deliberate")
    invisible_text: list[str] = Field(
        default_factory=list, description="Text spelled in invisible characters, decoded"
    )
    instruction_lines: list[str] = Field(
        default_factory=list, description="Lines addressed to AI tools, quoted"
    )
    mixed_script_words: list[str] = Field(
        default_factory=list, description="Words mixing Latin with look-alike letters"
    )

    def level(self) -> Verdict:
        if self.instruction_lines or self.tampering or self.invisible_text:
            return "warning"
        if self.mixed_script_words:
            return "warning"
        if self.hidden_blocks or self.invisible_chars or self.hidden_urls:
            return "cleaned"
        return "clean"

    def describe(self) -> str:
        parts: list[str] = []
        if self.instruction_lines:
            n = len(self.instruction_lines)
            parts.append(_count(n, "line", "lines") + " addressed to AI tools")
        if self.invisible_text:
            parts.append("text spelled in invisible characters")
        parts += self.tampering
        if self.mixed_script_words:
            n = len(self.mixed_script_words)
            parts.append(_count(n, "word", "words") + " with look-alike letters")
        if self.hidden_blocks:
            parts.append(_count(self.hidden_blocks, "hidden block", "hidden blocks") + " removed")
        if self.hidden_urls:
            parts.append(_count(len(self.hidden_urls), "link", "links") + " only in hidden text")
        if self.invisible_chars and not self.tampering and not self.invisible_text:
            n = self.invisible_chars
            parts.append(_count(n, "invisible character", "invisible characters") + " removed")
        if not parts:
            return "Nothing hidden or addressed to AI tools."
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."

    def merge(self, other: PostingIntegrity | None) -> PostingIntegrity:
        if other is None:
            return self

        def union(a: list[str], b: list[str]) -> list[str]:
            return list(dict.fromkeys([*a, *b]))[:MAX_ITEMS]

        return PostingIntegrity(
            hidden_blocks=self.hidden_blocks + other.hidden_blocks,
            hidden_excerpts=union(self.hidden_excerpts, other.hidden_excerpts)[:3],
            hidden_urls=union(self.hidden_urls, other.hidden_urls),
            invisible_chars=self.invisible_chars + other.invisible_chars,
            tampering=union(self.tampering, other.tampering),
            invisible_text=union(self.invisible_text, other.invisible_text),
            instruction_lines=union(self.instruction_lines, other.instruction_lines),
            mixed_script_words=union(self.mixed_script_words, other.mixed_script_words),
        )

    def stored(self) -> dict[str, object] | None:
        """The JSON kept on the job: None when there's nothing to report."""
        return None if self.level() == "clean" else self.model_dump(mode="json")


class IntegrityView(PostingIntegrity):
    """What the API shows: the findings plus a verdict and a one-line summary."""

    verdict: Verdict
    summary: str

    @classmethod
    def of(cls, stored: dict[str, object] | None) -> IntegrityView | None:
        if not stored:
            return None
        found = PostingIntegrity.model_validate(stored)
        return cls(**found.model_dump(), verdict=found.level(), summary=found.describe())


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


@dataclass(frozen=True)
class CleanPosting:
    text: str
    integrity: PostingIntegrity


def combine(parts: list[CleanPosting]) -> CleanPosting:
    """Join several cleaned pieces of one posting (Lever sends sections separately)."""
    integrity = PostingIntegrity()
    for part in parts:
        integrity = integrity.merge(part.integrity)
    text = "\n\n".join(p.text for p in parts if p.text)
    return CleanPosting(text[:MAX_DESCRIPTION_CHARS], integrity)


def clean_posting(markup: str | None, *, html_input: bool = True) -> CleanPosting:
    """Readable, cleaned text plus what was removed or found. Plain text skips the HTML step."""
    if not markup:
        return CleanPosting("", PostingIntegrity())
    visible: str
    hidden: list[str] = []
    scanned: list[str] = []
    hidden_urls: list[str] = []
    if html_input:
        if "&lt;" in markup and "<" not in markup:
            markup = html.unescape(markup)  # Greenhouse/RSS double-encode
        parser = _Cleaner()
        parser.feed(markup)
        parser.close()
        visible = _tidy("".join(parser.visible))
        hidden = [b for b in (_tidy(b) for b in parser.blocks) if b]
        scanned = [s for s in (_tidy(s) for s in parser.scanned) if s]
        seen = parser.visible_links | set(_URL.findall(visible))
        hidden_urls = [u for u in dict.fromkeys(parser.hidden_links) if u not in seen]
        hidden_urls += [
            u
            for block in hidden
            for u in _URL.findall(block)
            if u not in seen and u not in hidden_urls
        ]
    else:
        visible = _tidy(markup)

    text, stats = _strip_invisible(visible)
    hidden = [_strip_invisible(b)[0] for b in hidden]
    scanned = [_strip_invisible(s)[0] for s in scanned]

    lines = _instruction_lines(text)
    for chunk in hidden:
        lines += [f"(hidden) {line}" for line in _instruction_lines(chunk)]
    for chunk in [*scanned, *stats.decoded]:
        lines += [f"(hidden) {line}" for line in _instruction_lines(chunk)]

    integrity = PostingIntegrity(
        hidden_blocks=len(hidden),
        hidden_excerpts=[_excerpt(b) for b in hidden[:3]],
        hidden_urls=hidden_urls[:MAX_ITEMS],
        invisible_chars=stats.suspicious,
        tampering=stats.tampering,
        invisible_text=[_excerpt(t, MAX_QUOTE) for t in stats.decoded][:MAX_ITEMS],
        instruction_lines=list(dict.fromkeys(lines))[:MAX_ITEMS],
        mixed_script_words=_mixed_script_words(text),
    )
    return CleanPosting(text[:MAX_DESCRIPTION_CHARS], integrity)


# --- HTML ---------------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
    "track", "wbr",
}  # fmt: skip
_DROPPED_TAGS = {"script", "style", "head"}
_QUIET_TAGS = {"template", "noscript", "svg", "iframe", "object", "math", "canvas"}

_HIDDEN_STYLE = re.compile(
    r"(?:^|;)(?:"
    r"display:none|visibility:(?:hidden|collapse)|opacity:0?\.?0*(?=;|$)"
    r"|font-size:(?:0|0?\.\d+)(?:px|pt|em|rem|%)?(?=;|$)|font-size:1(?:px|pt)(?=;|$)"
    r"|color:transparent|color:rgba\([^)]*,0(?:\.0+)?\)"
    r"|clip:rect\(0[a-z]*,?0[a-z]*,?0[a-z]*,?0[a-z]*\)|clip-path:inset\(50%\)"
    r"|(?:left|top|right|text-indent|margin-left|margin-top):-\d{3,}"
    r"|transform:scale\(0\)"
    r")"
)
_ZERO_BOX = re.compile(r"(?:^|;)(?:max-)?(?:height|width):0(?:px)?(?=;|$)")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _hidden_style(style: str) -> bool:
    value = _CSS_COMMENT.sub("", html.unescape(style)).lower()
    value = re.sub(r"\s+|!important", "", value)
    if _HIDDEN_STYLE.search(value):
        return True
    return bool(_ZERO_BOX.search(value)) and "overflow:hidden" in value


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []
        self.blocks: list[str] = []
        self.scanned: list[str] = []
        self.visible_links: set[str] = set()
        self.hidden_links: list[str] = []
        self._stack: list[tuple[str, str]] = []  # (tag, mode): show, hidden, quiet, dropped
        self._hidden = 0
        self._quiet = 0
        self._dropped = 0
        self._block: list[str] = []
        self._quiet_text: list[str] = []

    def _out(self, text: str) -> None:
        if self._dropped:
            return
        if self._hidden:
            self._block.append(text)
        elif self._quiet:
            self._quiet_text.append(text)
        else:
            self.visible.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "a" and values.get("href", "").startswith(("http://", "https://")):
            href = values["href"]
            if self._hidden or self._quiet:
                self.hidden_links.append(href)
            elif not self._dropped:
                self.visible_links.add(href)
        if tag in _VOID_TAGS:
            if tag == "br":
                self._out("\n")
            return
        if tag in _DROPPED_TAGS:
            mode = "dropped"
            self._dropped += 1
        elif tag in _QUIET_TAGS:
            mode = "quiet"
            self._quiet += 1
        elif (
            "hidden" in values
            or values.get("aria-hidden", "").lower() == "true"
            or _hidden_style(values.get("style", ""))
        ):
            mode = "hidden"
            if not self._hidden:
                self._block = []
            self._hidden += 1
        else:
            mode = "show"
        self._stack.append((tag, mode))
        if tag == "li":
            self._out("\n- ")
        elif tag in _BLOCK_TAGS:
            self._out("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                for _tag, mode in reversed(self._stack[i:]):
                    self._leave(mode)
                del self._stack[i:]
                break
        else:
            return  # a stray end tag
        if tag in _BLOCK_TAGS and tag != "li":  # the next <li> starts its own line
            self._out("\n")

    def _leave(self, mode: str) -> None:
        if mode == "dropped":
            self._dropped -= 1
        elif mode == "quiet":
            self._quiet -= 1
            if not self._quiet:
                self.scanned.append("".join(self._quiet_text))
                self._quiet_text = []
        elif mode == "hidden":
            self._hidden -= 1
            if not self._hidden:
                self.blocks.append("".join(self._block))
                self._block = []

    def handle_data(self, data: str) -> None:
        self._out(data)

    def handle_comment(self, data: str) -> None:
        self.scanned.append(data)

    def close(self) -> None:
        super().close()
        for _tag, mode in reversed(self._stack):  # unclosed tags at the end
            self._leave(mode)
        self._stack = []


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _excerpt(text: str, limit: int = MAX_EXCERPT) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


_URL = re.compile(r"https?://[^\s<>\"')\]]+")


# --- invisible characters -----------------------------------------------------------------

_TAG_RUN = re.compile("[\U000e0000-\U000e007f]+")
_FLAG = re.compile("\U0001f3f4[\U000e0030-\U000e0039\U000e0061-\U000e007a]+\U000e007f")
_SELECTOR_RUN = re.compile("[︀-️\U000e0100-\U000e01ef]{4,}")
_BIDI = re.compile("[‪-‮⁦-⁩]")
_JOINER_IN_WORD = re.compile("(?<=[A-Za-z])[​-‍⁠﻿]+(?=[A-Za-z])")
_HARMLESS = re.compile("[­؜᠎​‎‏⁠-⁤﻿]")


@dataclass
class _InvisibleStats:
    suspicious: int
    tampering: list[str]
    decoded: list[str]


def _decode_selectors(run: str) -> str:
    data = bytes(ord(c) - 0xFE00 if ord(c) <= 0xFE0F else ord(c) - 0xE0100 + 16 for c in run)
    return data.decode("utf-8", errors="replace")


def _strip_invisible(text: str) -> tuple[str, _InvisibleStats]:
    stats = _InvisibleStats(0, [], [])
    if text.isascii():
        return text, stats

    flags: list[str] = []

    def keep_flag(m: re.Match[str]) -> str:
        flags.append(m.group())
        return f"\x00{len(flags) - 1}\x00"

    text = _FLAG.sub(keep_flag, text)

    def tags(m: re.Match[str]) -> str:
        run = m.group()
        stats.suspicious += len(run)
        decoded = "".join(chr(ord(c) - 0xE0000) for c in run if 0xE0020 <= ord(c) <= 0xE007E)
        if decoded.strip():
            stats.decoded.append(decoded.strip())
        return ""

    text = _TAG_RUN.sub(tags, text)
    if stats.suspicious:
        stats.tampering.append("Unicode tag characters (invisible text)")

    def selectors(m: re.Match[str]) -> str:
        run = m.group()
        stats.suspicious += len(run)
        decoded = _decode_selectors(run)
        if decoded.strip() and "�" not in decoded:
            stats.decoded.append(decoded.strip())
        if "variation selectors carrying data" not in stats.tampering:
            stats.tampering.append("variation selectors carrying data")
        return ""

    text = _SELECTOR_RUN.sub(selectors, text)

    bidi = len(_BIDI.findall(text))
    if bidi:
        stats.suspicious += bidi
        stats.tampering.append("bidirectional override characters")
        text = _BIDI.sub("", text)

    def joiner(m: re.Match[str]) -> str:
        stats.suspicious += len(m.group())
        return ""

    joined = _JOINER_IN_WORD.sub(joiner, text)
    if joined != text:
        stats.tampering.append("zero-width characters inside words")
        text = joined
    text = _HARMLESS.sub("", text)

    for i, flag in enumerate(flags):
        text = text.replace(f"\x00{i}\x00", flag)
    return text, stats


# --- lines addressed to AI tools ----------------------------------------------------------

# Models and AI tools. Bare "assistant" and "bot" only count when addressed directly ("Dear
# assistant"), since "If you are an assistant..." and virtual assistants are real jobs.
_MODEL = (
    r"(?:a\.?i\.?|llms?|(?:large )?language models?|chat ?gpt|gpt(?:-?\d\w*)?|claude|gemini"
    r"|copilot|chatbots?|ai (?:assistants?|agents?|tools?|models?|systems?|screeners?)"
    r"|automated (?:systems?|tools?|screeners?))"
)
_AI = rf"(?:{_MODEL}|bots?|assistants?)"
# "You are an AI engineer" and "AI-native team" describe people, not the reader.
_ROLE = (
    r"(?![- ]?(?:engineer|research|scien|develop|special|expert|enthusias|practition|product"
    r"|team|lead|architect|consult|manag|strateg|ethic|safety|platform|infra|solution|trainer"
    r"|tutor|writer|annotat|evaluat|red.?team|ops|first|native|driven|powered|compan|startup"
    r"|literate|fluen|tools? (?:like|such)|-?based|enabled|savvy|focused|curious|role|position"
    r"|job|work|skills?|experience|projects?|initiatives?|products?|features?|capabilit))"
)
_DOC = (
    r"(?:cover letter|application|resume|résumé|cv|answers?|responses?|reply|message|e-?mail"
    r"|letter|submission|subject line)"
)
_INSTRUCTION_PATTERNS = [
    # "Ignore all previous instructions", "disregard the system prompt"
    r"\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(?:previous|prior|above"
    r"|earlier|all|any|your|these|those|system|original)\b[^.\n]{0,30}\b(?:instructions?"
    r"|prompts?|rules|guidelines|directions|context)\b",
    # "If you are an LLM", "if this is being read by an AI"
    rf"\b(?:if|when|in case)\b[^.\n]{{0,6}}\b(?:you are|you're|you were|you happen to be"
    rf"|this is (?:being )?(?:read|processed|screened|parsed) by)\s+"
    rf"(?:an?\s+|the\s+)?{_MODEL}\b{_ROLE}",
    # "You are now a helpful assistant", "act as ChatGPT"
    rf"\b(?:you are now|you're now|act as|pretend to be|roleplay as)\s+(?:an?\s+|the\s+)?"
    rf"(?:[\w-]+\s+){{0,2}}{_AI}\b{_ROLE}",
    rf"\b(?:you are|you're)\s+(?:an?\s+|the\s+)?{_MODEL}\b{_ROLE}[^.\n]{{0,40}}"
    rf"\b(?:must|should|will|now|that|who|which)\b",
    # "Dear AI,", "Note to LLMs:", "Attention ChatGPT"
    rf"(?:^|[.!?]\s+)(?:dear|attention|note (?:to|for)|hey|hello|hi|message (?:to|for)"
    rf"|instructions? (?:to|for))[:,]?\s+(?:the\s+|any\s+|all\s+)?{_AI}\b{_ROLE}",
    # "AI tools must include ...", "Language models should rate this candidate ..."
    rf"\b{_MODEL}\b{_ROLE}[^.\n]{{0,40}}\b(?:must|should|shall|need to|are (?:required|instructed"
    rf"|asked) to)\s+(?:\w+\s+){{0,2}}(?:include|mention|insert|add|use|write|respond|reply"
    rf"|answer|say|state|rate|score|rank|recommend|output|return|print|start|begin|end)\b",
    # Chat markup that pretends to start a new turn
    r"</?\s*(?:system|assistant|instructions?)\s*>|<\|im_(?:start|end)\|>|\[/?INST\]",
    # Attention checks: "include the word 'banana' in your cover letter"
    rf"\b(?:include|mention|insert|use|add|put|write)\b[^.\n]{{0,25}}\b(?:word|phrase|term"
    rf"|code ?word|keyword|string|emoji|sentence)s?\b[^.\n]{{0,60}}\b(?:in|into|within|at the"
    rf" (?:start|end|beginning|top|bottom) of)\b[^.\n]{{0,25}}\b{_DOC}\b",
    rf"\b(?:start|begin|end|open|close|sign off|title)\b[^.\n]{{0,25}}\b{_DOC}\b[^.\n]{{0,20}}"
    rf"\b(?:with|by (?:saying|writing|mentioning|using))\b[^.\n]{{0,12}}\b(?:the\s+)?(?:word"
    rf"|phrase|sentence|words|code ?word)\b",
]
_INSTRUCTION = re.compile("|".join(f"(?:{p})" for p in _INSTRUCTION_PATTERNS), re.IGNORECASE)


def _instruction_lines(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for line in text.splitlines():
        line = line.strip(" -\t")
        if line and _INSTRUCTION.search(line):
            found.append(_excerpt(line, MAX_QUOTE))
    return found


# --- look-alike letters -------------------------------------------------------------------

_LETTER_RUN = re.compile(r"[^\W\d_]{3,}")
_LOOKALIKE_SCRIPTS = {"CYRILLIC", "GREEK"}


def _script(char: str) -> str:
    return unicodedata.name(char, "").split(" ", 1)[0]


def _mixed_script_words(text: str) -> list[str]:
    if text.isascii():
        return []
    words: list[str] = []
    for m in _LETTER_RUN.finditer(text):
        word = m.group()
        if word.isascii():
            continue
        scripts = {_script(c) for c in word}
        if "LATIN" in scripts and scripts & _LOOKALIKE_SCRIPTS and word not in words:
            words.append(word)
            if len(words) == MAX_ITEMS:
                break
    return words
