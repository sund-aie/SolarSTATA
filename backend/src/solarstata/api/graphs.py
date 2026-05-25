"""Plotly graph routes. Each endpoint returns a {data, layout} payload
ready for `react-plotly.js`.

All routes operate on the session's current frame by default; pass
`frame` to target another. Residuals-vs-fitted and marginsplot consult
the most-recent estimation on the session.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..engine import (
    bar_with_ci,
    box,
    histogram,
    line,
    marginsplot,
    margins as margins_engine,
    residuals_vs_fitted,
    scatter,
)
from ..session.models import Session
from ._jsonsafe import safe
from .deps import get_session

router = APIRouter(prefix="/graphs", tags=["graphs"])


class HistogramRequest(BaseModel):
    frame: str = "default"
    var: str = Field(..., min_length=1)
    bins: int = Field(20, ge=2, le=200)
    group: str | None = None


class ScatterRequest(BaseModel):
    frame: str = "default"
    x: str = Field(..., min_length=1)
    y: str = Field(..., min_length=1)
    group: str | None = None


class BoxRequest(BaseModel):
    frame: str = "default"
    var: str = Field(..., min_length=1)
    group: str | None = None


class BarRequest(BaseModel):
    frame: str = "default"
    var: str = Field(..., min_length=1)
    group: str | None = None
    subgroup: str | None = None
    # `err` picks the error-bar source. Default ci95 preserves the
    # pre-3.2 visual; the UI selector exposes sd / sem / none.
    err: Literal["none", "sd", "sem", "ci95"] = "ci95"
    ci: float = Field(0.95, ge=0.5, le=0.999)


class LineRequest(BaseModel):
    frame: str = "default"
    x: str
    y: str
    group: str | None = None
    # Default "none" preserves the raw (x, y) trace behaviour. When
    # the caller picks sd / sem / ci95 we aggregate per x-level and
    # render symmetric error bars.
    err: Literal["none", "sd", "sem", "ci95"] = "none"
    ci: float = Field(0.95, ge=0.5, le=0.999)


@router.post("/histogram")
def stats_histogram(req: HistogramRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        fig = histogram(frame.df, req.var, bins=req.bins, group=req.group,
                        value_labels=frame.value_labels)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _packed(fig, command=_cmd("histogram", req.var, group=req.group, bins=req.bins))


@router.post("/scatter")
def stats_scatter(req: ScatterRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        fig = scatter(frame.df, req.x, req.y, group=req.group,
                      value_labels=frame.value_labels)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _packed(fig, command=_cmd("scatter", f"{req.y} {req.x}", group=req.group))


@router.post("/box")
def stats_box(req: BoxRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        fig = box(frame.df, req.var, group=req.group,
                  value_labels=frame.value_labels)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _packed(fig, command=_cmd("graph box", req.var, group=req.group, over=True))


@router.post("/bar")
def stats_bar(req: BarRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        fig = bar_with_ci(frame.df, req.var, group=req.group, subgroup=req.subgroup,
                          err=req.err, ci=req.ci, value_labels=frame.value_labels)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Stata grouped-bar syntax: graph bar (mean) y, over(sub) over(group) asyvars
    if req.subgroup and req.group:
        command = f"graph bar (mean) {req.var}, over({req.subgroup}) over({req.group}) asyvars"
    else:
        command = _cmd("graph bar", f"(mean) {req.var}", group=req.group, over=True)
    return _packed(fig, command=command)


@router.post("/line")
def stats_line(req: LineRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        fig = line(frame.df, req.x, req.y, group=req.group,
                   err=req.err, ci=req.ci, value_labels=frame.value_labels)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _packed(fig, command=_cmd("twoway line", f"{req.y} {req.x}", group=req.group))


@router.post("/residuals")
def stats_residuals(session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, "default")
    try:
        fig = residuals_vs_fitted(frame.df, session.last_estimation)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _packed(fig, command="rvfplot")


@router.post("/marginsplot")
def stats_marginsplot(session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, "default")
    if session.last_estimation is None:
        raise HTTPException(status_code=400, detail="no estimates stored — run regress or logit first")
    try:
        m = margins_engine(frame.df, session.last_estimation, at_means=False)
        fig = marginsplot(m.structured)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _packed(fig, command="marginsplot")


# ===================================================================
# Helpers
# ===================================================================

def _require_frame(session: Session, name: str):
    frame = session.frames.get(name)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame not loaded: {name}")
    return frame


def _packed(fig: dict, *, command: str) -> dict:
    return safe({"command": command, "kind": "graph", "figure": fig})


def _cmd(stub: str, vars_: str, *, group: str | None = None, bins: int | None = None,
         over: bool = False) -> str:
    parts = [stub, vars_]
    options: list[str] = []
    if bins:
        options.append(f"bin({bins})")
    if group:
        options.append(f"by({group})" if not over else f"over({group})")
    out = " ".join(parts)
    if options:
        out += ", " + " ".join(options)
    return out
