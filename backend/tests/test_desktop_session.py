"""Desktop-mode session continuity.

When SOLARSTATA_DESKTOP=1 (set by the Electron sidecar spawn), every
request must resolve to the same singleton session — even from
distinct TestClient instances that don't share cookies. This mirrors
the Electron renderer's cross-host behaviour, where the session
cookie set by the backend on 127.0.0.1 isn't always carried by the
fetch() call back through Electron's session.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from solarstata.config import settings
from solarstata.main import app
from solarstata.session.store import session_store


@pytest.fixture
def desktop_mode():
    """Flip desktop_mode on for the duration of the test."""
    previous = settings.desktop_mode
    settings.desktop_mode = True
    session_store._sessions.clear()
    yield
    settings.desktop_mode = previous
    session_store._sessions.clear()


def test_two_clients_share_session_in_desktop_mode(desktop_mode, tmp_path):
    """Upload from one client; query columns from another. Same singleton."""
    csv = tmp_path / "tiny.csv"
    pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}).to_csv(csv, index=False)

    uploader = TestClient(app)
    queryer = TestClient(app)

    with csv.open("rb") as fh:
        resp = uploader.post(
            "/api/data/upload",
            files={"file": ("tiny.csv", fh, "text/csv")},
        )
    assert resp.status_code == 200, resp.text

    # In cookie mode this would 404 — queryer has no session cookie
    # from the upload — but desktop mode routes everything to the
    # same singleton.
    cols = queryer.get("/api/data/columns?frame=default")
    assert cols.status_code == 200, cols.text
    assert [c["name"] for c in cols.json()["columns"]] == ["x", "y"]


def test_desktop_mode_off_isolates_clients(tmp_path):
    """Sanity: with desktop_mode off, distinct clients still isolate."""
    # Don't touch settings — default is False
    assert settings.desktop_mode is False

    csv = tmp_path / "tiny.csv"
    pd.DataFrame({"x": [1, 2]}).to_csv(csv, index=False)

    uploader = TestClient(app)
    queryer = TestClient(app)

    with csv.open("rb") as fh:
        uploader.post(
            "/api/data/upload",
            files={"file": ("tiny.csv", fh, "text/csv")},
        )

    resp = queryer.get("/api/data/columns?frame=default")
    # Different session → no frame → 404
    assert resp.status_code == 404
