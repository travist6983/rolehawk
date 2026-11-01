"""Verify company watchlist candidates against their ATS and write data/companies/<ats>.csv.

    uv run python scripts/verify_watchlist.py candidates.csv

The candidates CSV has columns ats,slug,name,industry,country. Each slug is checked with one
polite request to the ATS's public job board API; only companies with a live board are kept
(with their open job count). Existing rows are re-verified and merged.
"""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path

from rolehawk.countries import data_dir
from rolehawk.portals.ats import AtsPortal
from rolehawk.portals.base import CompanyRef, PortalContext
from rolehawk.portals.http import HttpError, PoliteClient
from rolehawk.portals.registry import ATS_IDS, get_portal

FIELDS = ["slug", "name", "industry", "country"]


async def check(http: PoliteClient, ats: str, slug: str) -> int | None:
    impl = get_portal(ats)
    if not isinstance(impl, AtsPortal):
        raise TypeError(f"{ats} is not an ATS source")
    ctx = PortalContext(http=http, queries=())
    try:
        jobs = await impl.fetch_company(ctx, CompanyRef(slug, slug))
    except (HttpError, KeyError, TypeError, ValueError):
        return None
    return len(jobs)


async def main(candidates: Path) -> None:
    rows: dict[str, dict[str, dict[str, str]]] = {ats: {} for ats in ATS_IDS}
    out_dir = data_dir() / "companies"
    for ats in ATS_IDS:  # existing rows first, so they get re-verified too
        path = out_dir / f"{ats}.csv"
        if path.is_file():
            for row in csv.DictReader(path.open(encoding="utf-8")):
                rows[ats][row["slug"].lower()] = row
    for row in csv.DictReader(candidates.open(encoding="utf-8")):
        if row["ats"] in rows:
            rows[row["ats"]].setdefault(row["slug"].lower(), {k: row.get(k, "") for k in FIELDS})

    http = PoliteClient(retries=1)
    for ats in rows:
        impl = get_portal(ats)
        http.pace(impl.host, impl.min_interval_s, concurrency=4)
    flat = [(ats, row) for ats, entries in rows.items() for row in entries.values()]
    try:
        results = await asyncio.gather(*(check(http, ats, row["slug"]) for ats, row in flat))
    finally:
        await http.aclose()

    checked = list(zip(flat, results, strict=True))
    for ats in sorted(ATS_IDS):
        kept = [row for (a, row), jobs in checked if a == ats and jobs]
        dropped = [row["slug"] for (a, row), jobs in checked if a == ats and not jobs]
        kept.sort(key=lambda r: r["name"].lower())
        with (out_dir / f"{ats}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows({k: row.get(k, "") for k in FIELDS} for row in kept)
        print(f"{ats}: kept {len(kept)}, dropped {len(dropped)}: {', '.join(dropped) or '-'}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
