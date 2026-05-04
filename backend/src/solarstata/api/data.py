"""Data routes: upload, preview, columns."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..config import settings
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
    session: Session = Depends(get_session),
) -> dict:
    f = _require_frame(session, frame)
    info = []
    for col in f.df.columns:
        s = f.df[col]
        n_missing = int(s.isna().sum())
        info.append({
            "name": col,
            "dtype": str(s.dtype),
            "stata_type": f.storage_types.get(col),
            "label": f.column_labels.get(col, ""),
            "n": int(s.notna().sum()),
            "n_missing": n_missing,
            "missing_pct": round(n_missing / max(len(s), 1) * 100, 2),
            "n_unique": int(s.nunique(dropna=True)),
            "value_labels": f.value_labels.get(col, {}),
        })
    return safe({"frame": f.name, "columns": info})


def _require_frame(session: Session, name: str):
    frame = session.frames.get(name)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame not loaded: {name}")
    return frame


def _preview(df: pd.DataFrame, n: int) -> list[dict]:
    head = df.head(n).where(pd.notna(df.head(n)), None)
    return head.to_dict(orient="records")
