"""Liveness probe."""

from fastapi.testclient import TestClient


def test_healthz_returns_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["name"] == "SolarSTATA"
    assert body["phase"] == 1
    assert isinstance(body["version"], str)
    assert isinstance(body["active_sessions"], int)
