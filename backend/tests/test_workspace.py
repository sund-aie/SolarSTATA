"""Workspace download/upload round-trip."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_workspace_download_and_restore(client: TestClient, clinic_csv_path: Path) -> None:
    # Load clinic_patients into the first session.
    with clinic_csv_path.open("rb") as f:
        upload = client.post("/api/data/upload", files={"file": ("clinic_patients.csv", f, "text/csv")})
    assert upload.status_code == 200
    assert upload.json()["n_obs"] == 406

    # Run a couple of commands so the history has content.
    client.post("/api/stats/summarize", json={"variables": ["age", "plaque_index"]})
    client.post("/api/stats/regress",
                json={"depvar": "plaque_index", "indepvars": ["age", "brushing_freq"],
                      "vce": "robust", "if_expr": "patient_id < 9000"})

    # Download workspace.
    dump = client.get("/api/workspace/download")
    assert dump.status_code == 200
    payload = json.loads(dump.content)
    assert payload["format"] == "solarstata.workspace.v1"
    assert payload["frame"]["name"] == "default"
    assert len(payload["frame"]["records"]) == 406
    assert len(payload["command_history"]) >= 3  # use + summarize + regress

    # Restore into a fresh session by spinning a second TestClient.
    from solarstata.main import app
    from solarstata.session.store import session_store
    session_store._sessions.clear()
    fresh = TestClient(app)
    body = json.dumps(payload).encode()
    upload2 = fresh.post(
        "/api/workspace/upload",
        files={"file": ("solarstata.workspace.json", body, "application/json")},
    )
    assert upload2.status_code == 200
    restored = upload2.json()
    assert restored["frame"] == "default"
    assert restored["n_obs"] == 406
    assert restored["n_vars"] == 13
    assert restored["n_commands_restored"] == len(payload["command_history"])

    # The restored frame should be queryable like any other.
    cols = fresh.get("/api/data/columns").json()
    names = [c["name"] for c in cols["columns"]]
    assert "plaque_index" in names and "patient_id" in names


def test_workspace_rejects_unknown_format(client: TestClient) -> None:
    body = json.dumps({"format": "not-a-real-format"}).encode()
    resp = client.post(
        "/api/workspace/upload",
        files={"file": ("bogus.json", body, "application/json")},
    )
    assert resp.status_code == 400
    assert "unrecognised" in resp.json()["detail"].lower()


def test_workspace_rejects_malformed_json(client: TestClient) -> None:
    resp = client.post(
        "/api/workspace/upload",
        files={"file": ("bad.json", b"not json{", "application/json")},
    )
    assert resp.status_code == 400
