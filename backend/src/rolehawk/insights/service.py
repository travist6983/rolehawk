"""Writes the HTML report into <data>/reports/."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from rolehawk.db.types import utcnow
from rolehawk.insights.board import BoardService
from rolehawk.insights.report import render_report
from rolehawk.insights.stats import InsightsService
from rolehawk.paths import DataPaths


class ReportFile(BaseModel):
    filename: str
    path: str
    size: int


class ReportService:
    def __init__(
        self,
        paths: DataPaths,
        board: BoardService,
        insights: InsightsService,
        name: Callable[[], str | None],
    ) -> None:
        self._paths = paths
        self._board = board
        self._insights = insights
        self._name = name

    def generate(self) -> ReportFile:
        now = utcnow()
        html = render_report(self._insights.insights(now), self._board.board(), self._name(), now)
        folder = self._paths.reports
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"rolehawk-report-{now:%Y-%m-%d}.html"
        path.write_text(html, encoding="utf-8")
        return ReportFile(filename=path.name, path=str(path), size=path.stat().st_size)

    def path_for(self, filename: str) -> Path:
        """A report in the reports folder, by bare filename only."""
        folder = self._paths.reports.resolve()
        path = (folder / filename).resolve()
        if path.parent != folder or path.suffix != ".html" or not path.is_file():
            raise KeyError(filename)
        return path
