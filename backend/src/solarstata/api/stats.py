"""Statistics routes: summarize, tabulate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..engine import summarize, tabulate
from ..session.models import Session
from ._jsonsafe import safe
from .deps import get_session

router = APIRouter(prefix="/stats", tags=["stats"])


class SummarizeRequest(BaseModel):
    frame: str = "default"
    variables: list[str] | None = None
    detail: bool = False


class TabulateRequest(BaseModel):
    frame: str = "default"
    var1: str = Field(..., min_length=1)
    var2: str | None = None


@router.post("/summarize")
def stats_summarize(req: SummarizeRequest, session: Session = Depends(get_session)) -> dict:
    frame = session.frames.get(req.frame)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame not loaded: {req.frame}")

    try:
        result = summarize(frame.df, req.variables, detail=req.detail)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    session.r_results = dict(result.r_update)
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/tabulate")
def stats_tabulate(req: TabulateRequest, session: Session = Depends(get_session)) -> dict:
    frame = session.frames.get(req.frame)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame not loaded: {req.frame}")

    try:
        result = tabulate(frame.df, req.var1, req.var2)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    session.r_results = dict(result.r_update)
    session.append_history(result.command)
    return safe(result.to_response())
