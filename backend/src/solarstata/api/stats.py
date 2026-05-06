"""Statistics routes: summarize, tabulate, regress, logit, postest/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..engine import (
    estat_ic,
    estat_vif,
    lincom,
    logit as logit_engine,
    margins,
    predict,
    regress as regress_engine,
    summarize,
    tabulate,
    wald_test,
)
from ..session.models import Session
from ._jsonsafe import safe
from .deps import get_session

router = APIRouter(prefix="/stats", tags=["stats"])


# ===================================================================
# Request schemas
# ===================================================================

class SummarizeRequest(BaseModel):
    frame: str = "default"
    variables: list[str] | None = None
    detail: bool = False


class TabulateRequest(BaseModel):
    frame: str = "default"
    var1: str = Field(..., min_length=1)
    var2: str | None = None


class RegressRequest(BaseModel):
    frame: str = "default"
    depvar: str
    indepvars: list[str]
    vce: str = "ols"           # "ols" | "robust" | "hc3" | "cluster"
    cluster: str | None = None
    if_expr: str | None = None
    in_range: str | None = None


class LogitRequest(BaseModel):
    frame: str = "default"
    depvar: str
    indepvars: list[str]
    odds_ratios: bool = False
    vce: str = "mle"           # "mle" | "robust" | "cluster"
    cluster: str | None = None
    if_expr: str | None = None
    in_range: str | None = None


class PredictRequest(BaseModel):
    frame: str = "default"
    new_var: str = "fitted_values"
    kind: str = "xb"           # "xb" | "resid" | "pr"


class MarginsRequest(BaseModel):
    frame: str = "default"
    at_means: bool = False


class TestRequest(BaseModel):
    restrictions: list[str] = Field(..., min_length=1)


class LincomRequest(BaseModel):
    expression: str = Field(..., min_length=1)


# ===================================================================
# Existing endpoints
# ===================================================================

@router.post("/summarize")
def stats_summarize(req: SummarizeRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        result = summarize(frame.df, req.variables, detail=req.detail)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.r_results = dict(result.r_update)
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/tabulate")
def stats_tabulate(req: TabulateRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        result = tabulate(frame.df, req.var1, req.var2)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.r_results = dict(result.r_update)
    session.append_history(result.command)
    return safe(result.to_response())


# ===================================================================
# Phase 3 — regression family
# ===================================================================

@router.post("/regress")
def stats_regress(req: RegressRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        result, estimation = regress_engine(
            frame.df,
            req.depvar,
            req.indepvars,
            vce=req.vce,                       # type: ignore[arg-type]
            cluster=req.cluster,
            if_expr=req.if_expr,
            in_range=req.in_range,
            frame_name=frame.name,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.last_estimation = estimation
    session.e_results = dict(result.e_update or {})
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/logit")
def stats_logit(req: LogitRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        result, estimation = logit_engine(
            frame.df,
            req.depvar,
            req.indepvars,
            odds_ratios=req.odds_ratios,
            vce=req.vce,                       # type: ignore[arg-type]
            cluster=req.cluster,
            if_expr=req.if_expr,
            in_range=req.in_range,
            frame_name=frame.name,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.last_estimation = estimation
    session.e_results = dict(result.e_update or {})
    session.append_history(result.command)
    return safe(result.to_response())


# ===================================================================
# Phase 3 — postestimation
# ===================================================================

@router.post("/postest/predict")
def stats_predict(req: PredictRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        result, col = predict(frame.df, session.last_estimation, kind=req.kind, new_var=req.new_var)  # type: ignore[arg-type]
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    frame.df[req.new_var] = col
    frame.storage_types[req.new_var] = "double"
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/postest/margins")
def stats_margins(req: MarginsRequest, session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, req.frame)
    try:
        result = margins(frame.df, session.last_estimation, at_means=req.at_means)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/postest/test")
def stats_test(req: TestRequest, session: Session = Depends(get_session)) -> dict:
    try:
        result = wald_test(session.last_estimation, req.restrictions)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/postest/lincom")
def stats_lincom(req: LincomRequest, session: Session = Depends(get_session)) -> dict:
    try:
        result = lincom(session.last_estimation, req.expression)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/postest/estatic")
def stats_estat_ic(session: Session = Depends(get_session)) -> dict:
    try:
        result = estat_ic(session.last_estimation)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.append_history(result.command)
    return safe(result.to_response())


@router.post("/postest/estatvif")
def stats_estat_vif(session: Session = Depends(get_session)) -> dict:
    frame = _require_frame(session, "default")
    try:
        result = estat_vif(frame.df, session.last_estimation)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.append_history(result.command)
    return safe(result.to_response())


# ===================================================================
# Helpers
# ===================================================================

def _require_frame(session: Session, name: str):
    frame = session.frames.get(name)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Frame not loaded: {name}")
    return frame
