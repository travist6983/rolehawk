"""Local-only API protection (docs/SPEC.md "Security, privacy and guardrails").

- Host allowlist blocks DNS rebinding (a remote page resolving its domain to 127.0.0.1).
- Origin allowlist blocks cross-origin requests from other local or remote web pages.
- A random per-launch session token is required on /api/*:
  * `X-RoleHawk-Token` header: accepted for every method (the frontend keeps it in memory).
  * `rolehawk_session` cookie: accepted for safe methods only (GET/HEAD/OPTIONS), so
    EventSource and download links work while cookie-riding writes are impossible.
- Opening the launch URL `/?token=...` sets the cookie.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import parse_qs

from starlette.datastructures import Headers
from starlette.requests import cookie_parser
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TOKEN_HEADER = "x-rolehawk-token"  # noqa: S105 - header name
TOKEN_COOKIE = "rolehawk_session"  # noqa: S105 - cookie name
TOKEN_QUERY = "token"  # noqa: S105 - parameter name
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
PUBLIC_PATHS = frozenset({"/api/health"})


@dataclass(frozen=True)
class SecurityPolicy:
    token: str
    allowed_hosts: frozenset[str]
    allowed_origins: frozenset[str]
    public_paths: frozenset[str] = field(default=PUBLIC_PATHS)

    @classmethod
    def local(cls, token: str, port: int, extra_origins: Iterable[str] = ()) -> SecurityPolicy:
        hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        origins = frozenset({f"http://{host}" for host in hosts} | set(extra_origins))
        return cls(token=token, allowed_hosts=hosts, allowed_origins=origins)

    def token_matches(self, candidate: str | None) -> bool:
        return candidate is not None and hmac.compare_digest(
            candidate.encode(), self.token.encode()
        )


class SessionGuard:
    def __init__(self, app: ASGIApp, policy: SecurityPolicy) -> None:
        self.app = app
        self.policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if headers.get("host", "").lower() not in self.policy.allowed_hosts:
            await PlainTextResponse("Invalid Host header", status_code=421)(scope, receive, send)
            return
        origin = headers.get("origin")
        if origin is not None and origin not in self.policy.allowed_origins:
            await PlainTextResponse("Cross-origin request blocked", status_code=403)(
                scope, receive, send
            )
            return

        path: str = scope["path"]
        if path == "/api" or path.startswith("/api/"):
            if path not in self.policy.public_paths and not self._authorized(scope, headers):
                response = JSONResponse(
                    {"detail": "Missing or invalid session token"}, status_code=401
                )
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        await self.app(scope, receive, self._maybe_set_cookie(scope, send))

    def _authorized(self, scope: Scope, headers: Headers) -> bool:
        if self.policy.token_matches(headers.get(TOKEN_HEADER)):
            return True
        method = scope.get("method", "GET")
        if method in SAFE_METHODS or scope["type"] == "websocket":
            cookies = cookie_parser(headers.get("cookie", ""))
            return self.policy.token_matches(cookies.get(TOKEN_COOKIE))
        return False

    def _maybe_set_cookie(self, scope: Scope, send: Send) -> Send:
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        if not self.policy.token_matches(next(iter(query.get(TOKEN_QUERY, [])), None)):
            return send
        cookie = f"{TOKEN_COOKIE}={self.policy.token}; HttpOnly; SameSite=Strict; Path=/"

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [*message.get("headers", []), (b"set-cookie", cookie.encode())],
                }
            await send(message)

        return send_with_cookie
