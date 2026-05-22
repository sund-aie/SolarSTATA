"""ASGI middleware that attaches a Session to every request.

The session id lives in a signed cookie. If the cookie is missing or
the signature fails, we mint a fresh session. The Session object is
attached to `request.state.session` so route handlers can use the
`get_session` dependency.

In desktop mode (SOLARSTATA_DESKTOP=1, set by the Electron sidecar
spawn) every request resolves to the same singleton session
regardless of cookie. This protects state continuity inside the
Electron shell, where cross-host cookies between renderer and
sidecar can be blocked by browser policy.
"""

from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..config import settings
from .store import session_store


DESKTOP_SESSION_ID = "__desktop__"


class SessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, secret: str | None = None, cookie_name: str | None = None):
        super().__init__(app)
        self._serializer = URLSafeSerializer(secret or settings.session_secret, salt="solarstata")
        self._cookie_name = cookie_name or settings.session_cookie_name

    async def dispatch(self, request: Request, call_next):
        if settings.desktop_mode:
            # Single-user shell: one session, no cookie negotiation.
            session = session_store.get(DESKTOP_SESSION_ID)
            if session is None:
                session = session_store.create_with_id(DESKTOP_SESSION_ID)
            request.state.session = session
            return await call_next(request)

        cookie_value = request.cookies.get(self._cookie_name)
        session = None

        if cookie_value:
            try:
                session_id = self._serializer.loads(cookie_value)
                session = session_store.get(session_id)
            except BadSignature:
                session = None

        is_new = session is None
        if session is None:
            session = session_store.create()

        request.state.session = session

        response = await call_next(request)

        if is_new:
            signed = self._serializer.dumps(session.session_id)
            response.set_cookie(
                key=self._cookie_name,
                value=signed,
                httponly=True,
                samesite="lax",
                max_age=settings.session_idle_timeout_seconds,
            )

        return response
