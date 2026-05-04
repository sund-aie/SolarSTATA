"""ASGI middleware that attaches a Session to every request.

The session id lives in a signed cookie. If the cookie is missing or
the signature fails, we mint a fresh session. The Session object is
attached to `request.state.session` so route handlers can use the
`get_session` dependency.
"""

from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..config import settings
from .store import session_store


class SessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, secret: str | None = None, cookie_name: str | None = None):
        super().__init__(app)
        self._serializer = URLSafeSerializer(secret or settings.session_secret, salt="solarstata")
        self._cookie_name = cookie_name or settings.session_cookie_name

    async def dispatch(self, request: Request, call_next):
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
