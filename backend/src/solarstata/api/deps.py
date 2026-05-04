"""FastAPI dependencies — primarily session injection."""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..session.models import Session


def get_session(request: Request) -> Session:
    """Pull the session attached by SessionMiddleware."""
    session = getattr(request.state, "session", None)
    if session is None:
        raise HTTPException(status_code=500, detail="Session middleware did not run")
    return session
