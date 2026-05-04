"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from solarstata.main import app
from solarstata.session.store import session_store
from solarstata.walkthroughs.datasets import CLINIC_PATIENTS_CSV, CLINIC_PATIENTS_DTA


@pytest.fixture(autouse=True)
def _reset_session_store():
    """Each test gets a clean store."""
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


@pytest.fixture
def client() -> TestClient:
    """TestClient with cookie persistence so the session middleware works."""
    return TestClient(app)


@pytest.fixture
def clinic_csv_path() -> Path:
    assert CLINIC_PATIENTS_CSV.exists(), (
        f"Bundled dataset missing at {CLINIC_PATIENTS_CSV}. "
        "Run: python -m solarstata.walkthroughs.datasets.generate"
    )
    return CLINIC_PATIENTS_CSV


@pytest.fixture
def clinic_dta_path() -> Path:
    assert CLINIC_PATIENTS_DTA.exists()
    return CLINIC_PATIENTS_DTA


@pytest.fixture
def clinic_df(clinic_csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(clinic_csv_path)


@pytest.fixture
def loaded_client(client: TestClient, clinic_csv_path: Path) -> TestClient:
    """A TestClient with the bundled CSV already uploaded."""
    with clinic_csv_path.open("rb") as f:
        resp = client.post(
            "/api/data/upload",
            files={"file": (clinic_csv_path.name, f, "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    return client
