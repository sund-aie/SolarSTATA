"""Workspace persistence — download / upload session as a single JSON.

The download captures: the active frame's data (rows + dtypes), the
last estimation summary (sans the in-memory model object), and the
command history. Upload restores all three.

This is the user's escape hatch from the cookie-keyed session model:
serialize and reattach across machines or browser cleanings without
needing server-side persistence.
"""

from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..session.models import Frame, Session
from ._jsonsafe import safe
from .deps import get_session

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/download")
def download_workspace(session: Session = Depends(get_session)) -> StreamingResponse:
    frame = session.current_frame
    payload = {
        "format": "solarstata.workspace.v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "frame": _serialize_frame(frame) if frame else None,
        "e_results": safe(session.e_results or {}),
        "command_history": list(session.command_history or []),
    }
    body = json.dumps(safe(payload)).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(body),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="solarstata.workspace.json"'
        },
    )


@router.post("/upload")
async def upload_workspace(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    contents = await file.read()
    try:
        payload = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"workspace JSON malformed: {exc}")

    if payload.get("format") != "solarstata.workspace.v1":
        raise HTTPException(status_code=400, detail="unrecognised workspace format")

    frame_dict = payload.get("frame")
    if frame_dict:
        frame = _deserialize_frame(frame_dict)
        session.set_frame(frame, make_current=True)

    session.e_results = dict(payload.get("e_results") or {})
    session.command_history = list(payload.get("command_history") or [])

    frame = session.current_frame
    return safe({
        "frame": frame.name if frame else None,
        "filename": frame.source_filename if frame else None,
        "n_obs": frame.n_obs if frame else 0,
        "n_vars": frame.n_vars if frame else 0,
        "columns": frame.df.columns.tolist() if frame else [],
        "storage_types": frame.storage_types if frame else {},
        "column_labels": frame.column_labels if frame else {},
        "preview": _preview(frame.df, 10) if frame else [],
        "n_commands_restored": len(session.command_history),
    })


# ===================================================================
# Helpers
# ===================================================================

def _serialize_frame(frame: Frame) -> dict:
    df = frame.df
    return {
        "name": frame.name,
        "source_filename": frame.source_filename,
        "columns": df.columns.tolist(),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "storage_types": frame.storage_types,
        "column_labels": frame.column_labels,
        "value_labels": frame.value_labels,
        "records": df.where(pd.notna(df), None).to_dict(orient="records"),
    }


def _deserialize_frame(d: dict) -> Frame:
    records = d.get("records") or []
    df = pd.DataFrame.from_records(records)
    if d.get("columns"):
        df = df[[c for c in d["columns"] if c in df.columns]]
    return Frame(
        name=d.get("name") or "default",
        df=df,
        column_labels=d.get("column_labels") or {},
        value_labels=d.get("value_labels") or {},
        storage_types=d.get("storage_types") or {},
        source_filename=d.get("source_filename"),
    )


def _preview(df: pd.DataFrame, n: int) -> list[dict]:
    head = df.head(n).where(pd.notna(df.head(n)), None)
    return head.to_dict(orient="records")
