"""scripts/demo_data.py (README screenshots) keeps working as the app changes."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from rolehawk.paths import DataPaths
from rolehawk.services.runtime import open_runtime

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_data.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("demo_data", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_data"] = module  # dataclasses look their module up by name
    spec.loader.exec_module(module)
    return module


@pytest.mark.anyio
async def test_seed_fills_every_screen(tmp_path: Path) -> None:
    seed = cast(Callable[[Path], Coroutine[Any, Any, None]], load().seed)
    home = tmp_path / "demo"
    await seed(home)

    runtime = open_runtime(DataPaths(home))
    try:
        board = runtime.board.board()
        counts = {column.id: len(column.cards) for column in board.columns}
        assert all(counts[stage] for stage in ("saved", "applying", "applied", "screen"))
        assert all(counts[stage] for stage in ("interview", "offer"))
        flagged = [card for column in board.columns for card in column.cards if card.flags]
        assert flagged, "one application shows review flags"

        insights = runtime.insights.insights()
        assert insights.totals.offers == 1
        assert insights.spend.month_to_date_usd > 0
        assert runtime.profiles.load_profile().contact.name == "Jordan Avery"
        assert runtime.chat.list_sessions()
    finally:
        runtime.engine.dispose()
