"""Liveness and version probes."""

from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..session.store import session_store

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    """Liveness check + version. Used by Docker HEALTHCHECK and the smoke test."""
    return {
        "status": "ok",
        "name": "SolarSTATA",
        "version": __version__,
        "phase": 1,
        "active_sessions": len(session_store),
    }
