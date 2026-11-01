from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from rolehawk.api.deps import PolicyDep, RuntimeDep
from rolehawk.api.security import TOKEN_COOKIE
from rolehawk.services import health

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


@router.post("/session", status_code=204)
def establish_session(response: Response, policy: PolicyDep) -> None:
    """Called once by the page with its token header. Sets the HttpOnly cookie EventSource
    needs (EventSource can't send headers), including behind the Vite dev proxy."""
    response.set_cookie(TOKEN_COOKIE, policy.token, httponly=True, samesite="strict", path="/")
