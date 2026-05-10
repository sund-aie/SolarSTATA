"""Multi-sheet xlsx upload + header-row picker."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _write_workbook(path: Path) -> None:
    """A workbook that mimics the user's real-world failure case.

    Sheet 1 ("Notes"):  garbage / metadata only — should NOT be the default.
    Sheet 2 ("Tidy"):   the actual data, but with title text rows above the
                        real headers (the "TIDY LONG FORMAT" pattern).
    """
    wb = openpyxl.Workbook()
    notes = wb.active
    notes.title = "Notes"
    notes.append(["This sheet is just metadata."])
    notes.append(["Created on 2024-01-01"])

    tidy = wb.create_sheet("Tidy")
    tidy.append(["TIDY LONG FORMAT"])
    tidy.append(["Anonymized clinical extract"])
    tidy.append([])  # blank row
    tidy.append([])  # blank row
    tidy.append(["patient_id", "age", "sex"])
    tidy.append([1001, 23, "F"])
    tidy.append([1002, 45, "M"])
    tidy.append([1003, 31, "F"])

    wb.save(str(path))


@pytest.fixture
def quirky_workbook(tmp_path: Path) -> Path:
    p = tmp_path / "research.xlsx"
    _write_workbook(p)
    return p


def test_multisheet_upload_returns_choice_payload(client: TestClient, quirky_workbook: Path) -> None:
    with quirky_workbook.open("rb") as fh:
        resp = client.post(
            "/api/data/upload",
            files={"file": ("research.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requires_choice"] is True
    assert body["format"] == "xlsx"
    assert body["original_filename"] == "research.xlsx"
    sheet_names = [s["name"] for s in body["sheets"]]
    assert sheet_names == ["Notes", "Tidy"]

    tidy = next(s for s in body["sheets"] if s["name"] == "Tidy")
    assert tidy["preview_rows"][0][0] == "TIDY LONG FORMAT"
    # Row 5 (1-based) holds the headers
    assert tidy["preview_rows"][4][:3] == ["patient_id", "age", "sex"]


def test_finalize_with_chosen_sheet_and_header(client: TestClient, quirky_workbook: Path) -> None:
    with quirky_workbook.open("rb") as fh:
        stage = client.post(
            "/api/data/upload",
            files={"file": ("research.xlsx", fh, "application/octet-stream")},
        ).json()

    finalize = client.post(
        "/api/data/upload/finalize",
        json={"file_id": stage["file_id"], "sheet": "Tidy", "header_row": 5},
    )
    assert finalize.status_code == 200, finalize.text
    body = finalize.json()
    assert body["columns"] == ["patient_id", "age", "sex"]
    assert body["n_obs"] == 3
    assert body["n_vars"] == 3


def test_finalize_unknown_file_id(client: TestClient) -> None:
    resp = client.post(
        "/api/data/upload/finalize",
        json={"file_id": "doesnotexist", "sheet": "x", "header_row": 1},
    )
    assert resp.status_code == 404


def test_get_sheets_after_staging(client: TestClient, quirky_workbook: Path) -> None:
    with quirky_workbook.open("rb") as fh:
        stage = client.post("/api/data/upload",
                            files={"file": ("research.xlsx", fh, "application/octet-stream")}).json()
    listing = client.get(f"/api/data/sheets?file_id={stage['file_id']}").json()
    assert {s["name"] for s in listing["sheets"]} == {"Notes", "Tidy"}


def test_xlsx_with_explicit_header_row_skips_staging(client: TestClient, quirky_workbook: Path) -> None:
    """Power-user path: caller knows exactly which sheet+header to use."""
    with quirky_workbook.open("rb") as fh:
        resp = client.post(
            "/api/data/upload",
            data={"sheet": "Tidy", "header_row": "5"},
            files={"file": ("research.xlsx", fh, "application/octet-stream")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "requires_choice" not in body
    assert body["columns"] == ["patient_id", "age", "sex"]
    assert body["n_obs"] == 3


def test_csv_path_unaffected_by_new_logic(client: TestClient, tmp_path: Path) -> None:
    csv = tmp_path / "tiny.csv"
    pd.DataFrame({"x": [1, 2, 3]}).to_csv(csv, index=False)
    with csv.open("rb") as fh:
        resp = client.post("/api/data/upload", files={"file": ("tiny.csv", fh, "text/csv")})
    assert resp.status_code == 200
    assert "requires_choice" not in resp.json()
