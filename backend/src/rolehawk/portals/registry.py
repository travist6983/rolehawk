from __future__ import annotations

from rolehawk.portals.ats import Ashby, Greenhouse, Lever, Workable
from rolehawk.portals.base import Portal
from rolehawk.portals.feeds import Adzuna, RemoteOK, USAJobs, WeWorkRemotely

BUILTIN: list[Portal] = [
    Greenhouse(),
    Lever(),
    Ashby(),
    Workable(),
    RemoteOK(),
    WeWorkRemotely(),
    Adzuna(),
    USAJobs(),
]

ATS_IDS = {p.id for p in BUILTIN if "watchlist" in p.requires}


def get_portal(portal_id: str) -> Portal:
    for portal in BUILTIN:
        if portal.id == portal_id:
            return portal
    raise KeyError(portal_id)
