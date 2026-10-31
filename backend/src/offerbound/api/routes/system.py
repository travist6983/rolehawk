from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from offerbound.api.deps import PolicyDep, RuntimeDep
from offerbound.services import health

router = APIRouter(prefix="/api", tags=["system"])


class HealthOut(BaseModel):
    status: str
    version: str


class SessionOut(BaseModel):
    token: str
    data_root: str
    version: str


@router.get("/health")
def get_health() -> HealthOut:
    return HealthOut(**health.status())


@router.get("/session")
def get_session(runtime: RuntimeDep, policy: PolicyDep) -> SessionOut:
    """Lets the page recover its token after a reload (cookie-authenticated, same-origin)."""
    return SessionOut(
        token=policy.token, data_root=str(runtime.paths.root), version=health.status()["version"]
    )
