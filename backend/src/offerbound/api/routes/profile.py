from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from offerbound.api.deps import RuntimeDep
from offerbound.db.models import RemotePolicy, SearchTarget
from offerbound.memory.files import MemoryTarget
from offerbound.memory.proposals import MemorySnapshot
from offerbound.profile.model import Preferences, Profile
from offerbound.profile.service import Completeness, completeness
from offerbound.services.runtime import Runtime

router = APIRouter(tags=["profile"])


class SearchTargetView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    seniority: str | None
    locations: list[str]
    remote_policy: RemotePolicy
    country: str
    salary_min: int | None
    active: bool


class ProfileOverview(BaseModel):
    profile: Profile
    preferences: Preferences
    completeness: Completeness
    search_targets: list[SearchTargetView]


class MarkdownIn(BaseModel):
    markdown: str = Field(max_length=200_000)


def _overview(runtime: Runtime) -> ProfileOverview:
    profile = runtime.profiles.load_profile()
    prefs = runtime.profiles.load_preferences()
    with runtime.sessions() as session:
        targets = [
            SearchTargetView.model_validate(t)
            for t in session.scalars(select(SearchTarget).order_by(SearchTarget.id))
        ]
    return ProfileOverview(
        profile=profile,
        preferences=prefs,
        completeness=completeness(profile, prefs),
        search_targets=targets,
    )


@router.get("/api/profile")
async def get_profile(runtime: RuntimeDep) -> ProfileOverview:
    """The parsed view of profile.md and preferences.md, plus derived search targets."""
    return await asyncio.to_thread(_overview, runtime)


@router.put("/api/memory/{target}")
async def put_memory(target: MemoryTarget, body: MarkdownIn, runtime: RuntimeDep) -> MemorySnapshot:
    """The user's own edit to a memory file, saved exactly as written."""
    await asyncio.to_thread(runtime.profiles.save_raw, target, body.markdown)
    return await asyncio.to_thread(runtime.memory.snapshot)
