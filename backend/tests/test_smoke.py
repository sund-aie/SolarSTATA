"""End-to-end smoke test (Phase 1 acceptance gate).

Uploads the bundled clinic_patients.csv, runs summarize and tabulate,
and asserts the JSON shape against the contract the frontend will rely
on. If this passes, the backend works end-to-end.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_smoke_upload_summarize_tabulate(client: TestClient, clinic_csv_path: Path) -> None:
    # 1. healthz first to confirm the app is up
    health = client.get("/healthz").json()
    assert health["status"] == "ok"

    # 2. upload the bundled CSV
    with clinic_csv_path.open("rb") as f:
        upload = client.post(
            "/api/data/upload",
            files={"file": (clinic_csv_path.name, f, "text/csv")},
        )
    assert upload.status_code == 200, upload.text
    up = upload.json()
    assert up["frame"] == "default"
    assert up["filename"] == "clinic_patients.csv"
    assert up["n_obs"] == 406
    assert up["n_vars"] == 13
    assert "patient_id" in up["columns"]
    assert "plaque_index" in up["columns"]
    assert isinstance(up["preview"], list) and len(up["preview"]) == 10
    assert up["storage_types"]["age"] in ("long", "double")  # int → long

    # 3. summarize on a few numeric columns
    summ = client.post(
        "/api/stats/summarize",
        json={"variables": ["age", "plaque_index", "periodontal_pocket_depth_mm"], "detail": False},
    )
    assert summ.status_code == 200, summ.text
    s = summ.json()
    assert s["command"].startswith("summarize age plaque_index")
    assert "result" in s and "variables" in s["result"]
    rows = s["result"]["variables"]
    assert {r["Variable"] for r in rows} == {"age", "plaque_index", "periodontal_pocket_depth_mm"}
    age_row = next(r for r in rows if r["Variable"] == "age")
    assert age_row["Obs"] == 406
    assert age_row["Mean"] is not None
    assert age_row["SD"] is not None
    assert age_row["Min"] is not None
    assert age_row["Max"] is not None
    # Pro-mode text rendering
    assert "Variable" in s["text"] and "Obs" in s["text"]
    # r() macros set
    assert "N" in s["r_set"] and "mean" in s["r_set"]
    # No e() update (summarize is not an estimation command)
    assert s["e_set"] is None

    # 4. summarize, detail — percentiles + skew/kurtosis present
    detail = client.post(
        "/api/stats/summarize",
        json={"variables": ["plaque_index"], "detail": True},
    ).json()
    drow = detail["result"]["variables"][0]
    for k in ("p1", "p25", "p50", "p75", "p99", "Skewness", "Kurtosis", "Variance"):
        assert k in drow, f"detail summarize missing {k}"

    # 5. tabulate (one-way) on a categorical
    one = client.post("/api/stats/tabulate", json={"var1": "education_level"}).json()
    assert one["command"] == "tabulate education_level"
    assert one["result"]["variable"] == "education_level"
    cats = {row["value"] for row in one["result"]["rows"]}
    # 4 real categories + 1 dirty "unknown"
    assert {"primary", "secondary", "university", "postgrad", "unknown"}.issubset(cats)
    assert one["result"]["n"] == 406
    assert "Freq." in one["text"]

    # 6. tabulate (two-way) crosstab smoking × caries
    two = client.post(
        "/api/stats/tabulate",
        json={"var1": "smoking", "var2": "caries"},
    ).json()
    assert two["command"] == "tabulate smoking caries"
    payload = two["result"]
    assert payload["var1"] == "smoking" and payload["var2"] == "caries"
    assert isinstance(payload["matrix"], list)
    assert len(payload["matrix"]) == len(payload["row_categories"])
    assert all(len(row) == len(payload["col_categories"]) for row in payload["matrix"])
    assert sum(payload["row_totals"]) == sum(payload["col_totals"]) == payload["n"]
