"""OLS regression — Stata `regress depvar indepvars [if exp] [in range], options`.

Implements:
  - Factor-variable expansion (i./c./#/##) via engine.factor
  - if/in qualifiers via engine.qualifiers
  - vce(robust) using HC1 (Stata's default for `, robust`)
  - vce(hc3) for the bias-corrected sandwich
  - vce(cluster id) for cluster-robust standard errors

Returns (Result, Estimation). The Estimation captures the fitted
statsmodels object plus the qualifiers used at fit time so postestimation
commands (predict, margins, …) can replay them faithfully.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
import statsmodels.api as sm

from ..session.models import Estimation
from .factor import build_design, parse_indepvars
from .formatters import render_regress_table
from .qualifiers import apply_if, apply_in
from .results import Result

VceKind = Literal["ols", "robust", "hc3", "cluster"]


def regress(
    df: pd.DataFrame,
    depvar: str,
    indepvars: list[str],
    *,
    vce: VceKind = "ols",
    cluster: str | None = None,
    if_expr: str | None = None,
    in_range: str | None = None,
    frame_name: str = "default",
) -> tuple[Result, Estimation]:
    """Fit OLS. Returns (Result, Estimation) so the caller can stash the
    fitted model on the session for postestimation."""
    if vce == "cluster" and not cluster:
        raise ValueError("vce(cluster ...) requires a cluster variable name")

    if depvar not in df.columns:
        raise KeyError(f"depvar {depvar!r} not in dataset")

    sub = apply_in(apply_if(df, if_expr), in_range)
    needed = {depvar} | _all_referenced_vars(indepvars)
    if cluster:
        needed.add(cluster)
    sub = sub.dropna(subset=[c for c in needed if c in sub.columns])
    if sub.empty:
        raise ValueError("no observations remain after if / missing handling")

    terms = parse_indepvars(indepvars)
    design = build_design(sub, terms, add_constant=True)

    y = pd.to_numeric(sub[depvar], errors="coerce").to_numpy(dtype=float)
    X = design.X.to_numpy(dtype=float)

    fit_kwargs: dict = {}
    if vce == "robust":
        fit_kwargs = {"cov_type": "HC1"}
    elif vce == "hc3":
        fit_kwargs = {"cov_type": "HC3"}
    elif vce == "cluster":
        groups = sub[cluster].to_numpy()
        fit_kwargs = {"cov_type": "cluster", "cov_kwds": {"groups": groups}}

    model = sm.OLS(y, X).fit(**fit_kwargs)

    coef_table = _build_coef_table(design.column_names, model)

    n = int(model.nobs)
    df_m = int(model.df_model)
    df_r = int(model.df_resid)
    rmse = float(np.sqrt(model.mse_resid)) if hasattr(model, "mse_resid") else None
    r2 = float(model.rsquared)
    r2_a = float(model.rsquared_adj)

    # F or Wald depending on cov_type
    f_stat: float | None = None
    f_p: float | None = None
    try:
        f_stat = float(model.fvalue)
        f_p = float(model.f_pvalue)
    except Exception:  # noqa: BLE001
        pass

    header = {
        "N": n,
        "df_m": df_m,
        "df_r": df_r,
        "F": _safe(f_stat),
        "Prob_F": _safe(f_p),
        "R2": _safe(r2),
        "R2_adj": _safe(r2_a),
        "RMSE": _safe(rmse),
        "vce": vce,
        "cluster": cluster,
    }

    structured = {
        "command": _format_command(depvar, indepvars, vce, cluster, if_expr, in_range),
        "kind": "regress",
        "depvar": depvar,
        "indepvars": indepvars,
        "header": header,
        "coefficients": coef_table,
        "design_columns": design.column_names,
    }

    text = render_regress_table(
        title=f"Linear regression",
        depvar=depvar,
        header=header,
        coef_rows=coef_table,
    )

    e_update = {
        "cmd": "regress",
        "depvar": depvar,
        "N": n,
        "df_m": df_m,
        "df_r": df_r,
        "r2": _safe(r2),
        "r2_a": _safe(r2_a),
        "rmse": _safe(rmse),
        "F": _safe(f_stat),
        "p": _safe(f_p),
        "vce": vce,
        "rank": int(np.linalg.matrix_rank(X)),
    }

    result = Result(
        command=structured["command"],
        structured=structured,
        text=text,
        r_update={},
        e_update=e_update,
    )
    estimation = Estimation(
        command=structured["command"],
        cmd_kind="regress",
        depvar=depvar,
        indepvars=list(indepvars),
        design_columns=design.column_names,
        frame_name=frame_name,
        n_obs=n,
        if_expr=if_expr,
        in_range=in_range,
        cluster=cluster,
        model=model,
    )
    return result, estimation


# ===================================================================
# Helpers
# ===================================================================

def _build_coef_table(names: list[str], model) -> list[dict]:
    params = model.params
    bse = model.bse
    tvals = model.tvalues
    pvals = model.pvalues
    ci = model.conf_int(alpha=0.05)
    # statsmodels returns numpy array OR DataFrame depending on call site —
    # normalize to a 2-column ndarray.
    ci_arr = np.asarray(ci)

    rows: list[dict] = []
    for i, name in enumerate(names):
        rows.append({
            "name":       name,
            "coef":       _safe(params[i]),
            "se":         _safe(bse[i]),
            "t":          _safe(tvals[i]),
            "p":          _safe(pvals[i]),
            "ci_low":     _safe(ci_arr[i, 0]),
            "ci_high":    _safe(ci_arr[i, 1]),
            "significant": bool(pvals[i] < 0.05),
        })
    return rows


def _all_referenced_vars(tokens: list[str]) -> set[str]:
    out: set[str] = set()
    for tok in tokens:
        for piece in tok.replace("##", "#").split("#"):
            piece = piece.strip()
            if piece.startswith("i.") or piece.startswith("c."):
                piece = piece[2:]
            if piece:
                out.add(piece)
    return out


def _format_command(
    depvar: str,
    indepvars: list[str],
    vce: str,
    cluster: str | None,
    if_expr: str | None,
    in_range: str | None,
) -> str:
    parts = ["regress", depvar, *indepvars]
    if if_expr:
        parts.append(f"if {if_expr}")
    if in_range:
        parts.append(f"in {in_range}")
    options: list[str] = []
    if vce == "robust":
        options.append("vce(robust)")
    elif vce == "hc3":
        options.append("vce(hc3)")
    elif vce == "cluster":
        options.append(f"vce(cluster {cluster})")
    cmd = " ".join(parts)
    if options:
        cmd += ", " + " ".join(options)
    return cmd


def _safe(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 7)
