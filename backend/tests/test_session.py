"""Session middleware + store tests."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from solarstata.session.store import SessionStore, session_store


def test_first_request_sets_cookie(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert "solarstata_session" in resp.cookies


def test_subsequent_requests_reuse_cookie(client: TestClient) -> None:
    client.get("/healthz")  # mints cookie
    before = len(session_store)
    client.get("/healthz")
    client.get("/healthz")
    assert len(session_store) == before  # no new sessions


def test_two_clients_get_separate_sessions() -> None:
    from solarstata.main import app
    a = TestClient(app)
    b = TestClient(app)
    a.get("/healthz")
    b.get("/healthz")
    assert len(session_store) == 2


def test_evict_idle_removes_stale_sessions() -> None:
    s = SessionStore()
    sess = s.create()
    # Force last_activity to "long ago"
    sess.last_activity = time.time() - 10_000
    evicted = s.evict_idle(idle_timeout_seconds=1)
    assert evicted == 1
    assert len(s) == 0


def test_evict_idle_keeps_active_sessions() -> None:
    s = SessionStore()
    s.create()
    s.create()
    evicted = s.evict_idle(idle_timeout_seconds=10_000)
    assert evicted == 0
    assert len(s) == 2


def test_get_unknown_session_returns_none() -> None:
    s = SessionStore()
    assert s.get("does-not-exist") is None


def test_session_isolation_between_clients(clinic_csv_path) -> None:
    """Client A's uploaded data must not be visible to client B."""
    from solarstata.main import app
    a = TestClient(app)
    b = TestClient(app)

    with clinic_csv_path.open("rb") as f:
        a.post("/api/data/upload", files={"file": (clinic_csv_path.name, f, "text/csv")})

    a_resp = a.get("/api/data/preview").json()
    b_resp = b.get("/api/data/preview")
    assert "n_obs" in a_resp
    assert b_resp.status_code == 404  # no frame loaded for b
