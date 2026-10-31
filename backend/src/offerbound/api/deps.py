from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from offerbound.api.security import SecurityPolicy
from offerbound.services.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


def get_policy(request: Request) -> SecurityPolicy:
    policy: SecurityPolicy = request.app.state.policy
    return policy


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
PolicyDep = Annotated[SecurityPolicy, Depends(get_policy)]
