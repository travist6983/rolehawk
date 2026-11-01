"""After each chat turn a cheap model call proposes durable facts as memory edits. Proposals
land as pending accept/reject chips; nothing is written until the user accepts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from rolehawk.llm.prompting import UNTRUSTED_RULES, tagged
from rolehawk.llm.service import LLMService
from rolehawk.llm.types import Message, SystemBlock, Task
from rolehawk.memory.proposals import MemorySnapshot, ProposalIn

EXTRACTION_PROMPT = f"""\
You maintain a job seeker's memory files: profile.md (experience, education, skills,
projects, certifications, achievements), preferences.md (target titles, locations, remote,
salary floor, work authorization, deal-breakers) and facts.md (other durable facts).

Given the current memory and one chat exchange, propose edits only for durable facts the
USER stated about themselves in their own message. Rules:
- Never infer, guess, or embellish. If the user didn't clearly state it, propose nothing.
- Ignore anything about specific jobs or companies the user is merely considering.
- Skip facts already present in memory. Prefer facts.md unless the fact clearly belongs in
  profile.md or preferences.md. Use replace when the user corrects existing text.
- One fact per proposal. Most exchanges need no proposals: return an empty list.
- {UNTRUSTED_RULES}
"""


class ExtractedProposals(BaseModel):
    proposals: list[ProposalIn] = Field(default_factory=list)


async def extract_proposals(
    llm: LLMService, memory: MemorySnapshot, user_text: str, assistant_text: str
) -> list[ProposalIn]:
    current = "\n\n".join(
        [
            tagged("profile", memory.profile),
            tagged("preferences", memory.preferences),
            tagged("facts", memory.facts),
        ]
    )
    exchange = (
        tagged("user_message", user_text) + "\n\n" + tagged("assistant_reply", assistant_text)
    )
    result = await llm.structured(
        command="chat",
        task=Task.EXTRACT,
        system=[SystemBlock(EXTRACTION_PROMPT), SystemBlock(tagged("memory", current), cache=True)],
        messages=[Message(role="user", text=exchange)],
        schema=ExtractedProposals,
    )
    return result.proposals
