"""In-memory session store with idle-eviction loop.

Anonymous, single-process, no external dependencies. Suitable for the
current single-server deployment. If we ever need multi-worker, swap
this out for Redis without touching the rest of the codebase — the
public surface is just `get`, `create`, and `delete`.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
import time
from typing import Optional

from .models import Session


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    def create(self) -> Session:
        with self._lock:
            session_id = secrets.token_urlsafe(32)
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def evict_idle(self, idle_timeout_seconds: int) -> int:
        """Remove sessions idle for longer than the threshold. Returns count evicted."""
        now = time.time()
        evicted = 0
        with self._lock:
            stale = [
                sid for sid, sess in self._sessions.items()
                if now - sess.last_activity > idle_timeout_seconds
            ]
            for sid in stale:
                del self._sessions[sid]
                evicted += 1
        return evicted

    async def start_eviction_loop(
        self,
        interval_seconds: int,
        idle_timeout_seconds: int,
    ) -> asyncio.Task:
        async def _loop() -> None:
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    self.evict_idle(idle_timeout_seconds)
                except asyncio.CancelledError:
                    raise

        return asyncio.create_task(_loop(), name="session-eviction")


# Module-level singleton. Tests can monkey-patch or reset via .clear().
session_store = SessionStore()
