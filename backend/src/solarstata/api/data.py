"""Data routes: upload, preview, columns, histogram."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..config import settings
from ..engine import compute_bins
from ..io import read_dataset
from ..session.models import Session
from ._jsonsafe import safe
from .deps import get_session

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    frame_name: str = Query("default", min_length=1, max_length=64),
    session: Session = Depends(get_session),
) -> dict:
    """Accept a multipart upload and load it into the named frame.

    Replaces an existing frame with the same name. Returns frame metadata.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    contents = await file.read()
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_bytes // (1024*1024)} MB limit",
        )

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        frame = read_dataset(tmp_path, name=frame_name)
        frame.source_filename = file.filename
        session.set_frame(frame, make_current=True)
        session.append_history(f'use "{file.filename}", clear')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — surface parse errors to user
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

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
