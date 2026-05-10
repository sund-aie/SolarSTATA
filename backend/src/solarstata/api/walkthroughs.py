"""Walkthrough resources: serves the bundled clinic_patients dataset so
the Help-panel walkthroughs can auto-load it without the user dragging
a file in.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..walkthroughs.datasets import CLINIC_PATIENTS_CSV

router = APIRouter(prefix="/walkthroughs", tags=["walkthroughs"])


@router.get("/datasets/clinic_patients.csv")
def clinic_patients_csv() -> FileResponse:
    if not CLINIC_PATIENTS_CSV.exists():
        raise HTTPException(
            status_code=500,
            detail="Bundled dataset missing — run "
                   "`python -m solarstata.walkthroughs.datasets.generate`.",
        )
    return FileResponse(
        CLINIC_PATIENTS_CSV,
        media_type="text/csv",
        filename="clinic_patients.csv",
    )
