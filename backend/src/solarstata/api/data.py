"""Data routes: upload (with optional staging for multi-sheet xlsx),
preview, columns, histogram, sheets, upload/finalize.

Staged uploads (the intermediate state between accepting an xlsx
and committing a chosen sheet to a frame) live in a process-wide
store keyed by file_id — see `..session.staging`. This makes the
upload→finalize handshake robust under the Electron desktop shell,
where cross-host cookies don't ride along reliably.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..config import settings
from ..engine import compute_bins
from ..io import list_xlsx_sheets, read_dataset, sniff_format
from ..session import staging
from ..session.models import Session, StagedUpload
from ._jsonsafe import safe
from .deps import get_session

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    frame_name: str = Query("default", min_length=1, max_length=64),
    sheet: str | None = Form(None),
    header_row: int | None = Form(None),
    session: Session = Depends(get_session),
) -> dict:
    """Accept a multipart upload and load it into the named frame.

    For .xlsx files where the user hasn't yet supplied `header_row`, the
    file is staged on disk and a `requires_choice` payload is returned so
    the frontend can offer a sheet picker + header-row picker. The
    follow-up call goes to `/upload/finalize`.

    Replaces an existing frame with the same name. Returns frame metadata
    on success.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    contents = await file.read()
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB limit",
        )

    fmt = sniff_format(file.filename)
    suffix = Path(file.filename).suffix
    fd, tmp_str = tempfile.mkstemp(suffix=suffix)
    os.write(fd, contents)
    os.close(fd)
    tmp_path = Path(tmp_str)

    # XLSX path: stage and ask for sheet/header choice unless header_row was set.
    if fmt == "xlsx" and header_row is None:
        try:
            sheets = list_xlsx_sheets(tmp_path, n_preview_rows=10)
        except Exception as exc:  # noqa: BLE001 — corrupt workbook, etc.
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Could not read workbook: {exc}")

        file_id = uuid.uuid4().hex
        staging.put(StagedUpload(
            file_id=file_id,
            path=str(tmp_path),
            original_filename=file.filename,
            format=fmt,
            sheets=sheets,
        ))
        return safe({
            "requires_choice": True,
            "file_id": file_id,
            "format": fmt,
            "original_filename": file.filename,
            "sheets": sheets,
        })

    try:
        frame = read_dataset(
            tmp_path,
            name=frame_name,
            sheet=sheet,
            header_row=header_row or 1,
        )
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")

    tmp_path.unlink(missing_ok=True)
    frame.source_filename = file.filename
    session.set_frame(frame, make_current=True)
    session.append_history(f'use "{file.filename}", clear')
    return _materialized_response(frame)


@router.get("/sheets")
def staged_sheets(
    file_id: str = Query(..., min_length=1),
) -> dict:
    """Return the sheet metadata for a previously staged xlsx upload.

    Lookups are by file_id from the process-wide staging store; no
    session cookie required (which matters for the Electron shell).
    """
    staged = staging.get(file_id)
    if staged is None:
        raise HTTPException(status_code=404, detail=f"Unknown staged file: {file_id}")
    return safe({
        "file_id": staged.file_id,
        "format": staged.format,
        "original_filename": staged.original_filename,
        "sheets": staged.sheets,
    })


class FinalizeRequest(BaseModel):
    file_id: str = Field(..., min_length=1)
    sheet: str | None = None
    header_row: int = Field(1, ge=1, le=1000)
    frame_name: str = "default"


@router.post("/upload/finalize")
def finalize_upload(
    req: FinalizeRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Finalize a staged upload using a chosen sheet and header row.

    The staged file is looked up by file_id alone (process-wide store),
    so this call doesn't depend on the upload-side session cookie
    surviving the round-trip. The committed frame still lands on the
    caller's session for the rest of the analysis flow.
    """
    staged = staging.get(req.file_id)
    if staged is None:
        raise HTTPException(status_code=404, detail=f"Unknown staged file: {req.file_id}")

    tmp_path = Path(staged.path)
    try:
        frame = read_dataset(
            tmp_path,
            name=req.frame_name,
            sheet=req.sheet,
            header_row=req.header_row,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)
        staging.pop(req.file_id)

    frame.source_filename = staged.original_filename
    session.set_frame(frame, make_current=True)
    label = f'use "{staged.original_filename}"'
    if req.sheet:
        label += f', sheet("{req.sheet}")'
    if req.header_row != 1:
        label += f", firstrow({req.header_row})"
    session.append_history(label + ", clear")
    return _materialized_response(frame)


def _materialized_response(frame) -> dict:
    return safe({
        "frame": frame.name,
        "filename": frame.source_filename,
        "n_obs": frame.n_obs,
        "n_vars": frame.n_vars,
        "columns": frame.df.columns.tolist(),
        "storage_types": frame.storage_types,
        "column_labels": frame.column_labels,
        "preview": _preview(frame.df, n=10),
    })


@router.get("/preview")
def preview(
    frame: str = Query("default"),
    n: int = Query(100, ge=1, le=10_000),
    session: Session = Depends(get_session),
) -> dict:
    f = _require_frame(session, frame)
    return safe({
        "frame": f.name,
        "n_obs": f.n_obs,
        "n_vars": f.n_vars,
        "columns": f.df.columns.tolist(),
        "rows": _preview(f.df, n=n),
        "shown": min(n, f.n_obs),
    })


@router.get("/columns")
def columns(
    frame: str = Query("default"),
    sparkline_bins: int = Query(12, ge=2, le=64),
    session: Session = Depends(get_session),
) -> dict:
    f = _require_frame(session, frame)
    info = []
    for col in f.df.columns:
        s = f.df[col]
        n_missing = int(s.isna().sum())
        spark = compute_bins(s, n_bins=sparkline_bins)
        info.append({
            "name": col,
            "dtype": str(s.dtype),
            "stata_type": f.storage_types.get(col),
            "label": f.column_labels.get(col, ""),
            "kind": _classify_kind(s, spark.kind),
            "n": int(s.notna().sum()),
            "n_missing": n_missing,
            "missing_pct": round(n_missing / max(len(s), 1) * 100, 2),
            "n_unique": int(s.nunique(dropna=True)),
            "value_labels": f.value_labels.get(col, {}),
            "sparkline": spark.bins,
            "sparkline_kind": spark.kind,
        })
    return safe({"frame": f.name, "columns": info})


@router.get("/histogram")
def histogram(
    var: str = Query(..., min_length=1),
    bins: int = Query(15, ge=3, le=100),
    frame: str = Query("default"),
    session: Session = Depends(get_session),
) -> dict:
    """Larger histogram for the inspect panel. Same binning rules as the
    sparkline but with more bars and bin edges returned for axis labels."""
    f = _require_frame(session, frame)
    if var not in f.df.columns:
        raise HTTPException(status_code=404, detail=f"Variable not found: {var}")
    s = f.df[var]
    result = compute_bins(s, n_bins=bins)
    s_clean = s.dropna()
    return safe({
        "variable": var,
        "kind": result.kind,
        "bins": result.bins,
        "edges": result.edges,
        "labels": result.labels,
        "n": int(s_clean.notna().sum()),
        "n_missing": int(s.isna().sum()),
        "min": float(s_clean.min()) if not s_clean.empty and pd.api.types.is_numeric_dtype(s_clean) else None,
        "max": float(s_clean.max()) if not s_clean.empty and pd.api.types.is_numeric_dtype(s_clean) else None,
        "mean": float(s_clean.mean()) if not s_clean.empty and pd.api.types.is_numeric_dtype(s_clean) else None,
    })


def _classify_kind(series: pd.Series, fallback: str) -> str:
    """Map a column to the chip categories used by the frontend var card.

    Returns one of: 'id', 'binary', 'categorical', 'numeric', 'string'.
    """
    name = str(series.name).lower()
    n_unique = int(series.nunique(dropna=True))
    n_total = int(len(series.dropna()))

    if name.endswith("_id") or name == "id":
        return "id"
    if pd.api.types.is_bool_dtype(series):
        return "binary"
    if pd.api.types.is_numeric_dtype(series):
        if n_unique == 2:
            return "binary"
        if n_unique <= 10 and n_unique < max(n_total, 1):
            return "categorical"
        return "numeric"
    # object / string
    if n_unique <= 20:
        return "categorical"
    return "string"


def _require_frame(session: Session, name: str):
    frame = session.frames.get(name)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame not loaded: {name}")
    return frame


def _preview(df: pd.DataFrame, n: int) -> list[dict]:
    head = df.head(n).where(pd.notna(df.head(n)), None)
    return head.to_dict(orient="records")
