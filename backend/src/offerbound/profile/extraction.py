"""Resume / CV text -> structured profile with Claude (structured output). The result is a
draft the user reviews before anything is saved."""

from __future__ import annotations

from pydantic import BaseModel, Field

from offerbound.llm.prompting import UNTRUSTED_RULES, untrusted
from offerbound.llm.service import LLMService
from offerbound.llm.types import Message, SystemBlock, Task
from offerbound.profile.model import Preferences, Profile

MAX_EXTRACT_CHARS = 120_000

EXTRACTION_PROMPT = f"""\
You turn a job seeker's own resume, CV, or profile text into a structured profile.

Accuracy rules (these matter more than completeness):
- Extract only what the documents state. Never infer, guess, round, or embellish.
- Keep achievements in the candidate's own words; split multi-sentence bullets only where the
  document clearly lists separate points. Never add numbers that aren't in the text.
- Dates: "YYYY-MM" when the month is given, else "YYYY". Mark current roles with current=true
  and end=null. Leave unknown dates null.
- skills: only skills the document lists or that are named in its text; no synonyms.
- preferences: fill only what the document states outright (e.g. an "Objective" naming target
  roles or locations). Otherwise leave preferences empty.
- Contact: copy name, email, phone, location, and profile links exactly. Omit anything absent.
- {UNTRUSTED_RULES}
"""


class ExtractedSetup(BaseModel):
    profile: Profile = Field(default_factory=Profile)
    preferences: Preferences = Field(default_factory=Preferences)


async def extract_setup(
    llm: LLMService, documents: list[tuple[str, str]], task_id: str | None = None
) -> ExtractedSetup:
    """`documents` is a list of (label, text)."""
    blocks = [untrusted("candidate_document", text, name=label) for label, text in documents]
    body = "\n\n".join(blocks)
    if len(body) > MAX_EXTRACT_CHARS:
        raise ValueError("Those documents are too long to read at once; upload just your CV.")
    return await llm.structured(
        command="setup",
        task=Task.EXTRACT,
        system=[SystemBlock(EXTRACTION_PROMPT)],
        messages=[Message(role="user", text=f"Extract the profile from:\n\n{body}")],
        schema=ExtractedSetup,
        task_id=task_id,
    )
