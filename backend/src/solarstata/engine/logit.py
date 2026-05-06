"""Logistic regression — Stata `logit depvar indepvars [if exp] [in range], options`.

Same factor-variable + qualifier story as `regress`. Adds:
  - `or` option to display odds ratios (exp(coef)) instead of raw coefficients

When `or=True`, the rendered table shows OR / SE / z / P>|z| / 95% CI for
the OR. Significance test is the same z = coef/se on the original scale.

Returns (Result, Estimation) for the same reason as regress.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
import statsmodels.api as sm

from ..session.models import Estimation
from .factor import build_design, parse_indepvars
from .formatters import render_logit_table
from .qualifiers import apply_if, apply_in
from .regress import _all_referenced_vars, _safe
from .results import Result

VceKind = Literal["mle", "robust", "cluster"]


def logit(
    df: pd.DataFrame,
    depvar: str,
    indepvars: list[str],
    *,
    odds_ratios: bool = False,
    vce: VceKind = "mle",
    cluster: str | None = None,
    if_expr: str | None = None,
    in_range: str | None = None,
    frame_name: str = "default",
) -> tuple[Result, Estimation]:
    if depvar not in df.columns:
        raise KeyError(f"depvar {depvar!r} not in dataset")
    if vce == "cluster" and not cluster:
        raise ValueError("vce(cluster ...) requires a cluster variable name")

    sub = apply_in(apply_if(df, if_expr), in_range)
    needed = {depvar} | _all_referenced_vars(indepvars)
    if cluster:
        needed.add(cluster)
    sub = sub.dropna(subset=[c for c in needed if c in sub.columns])
    if sub.empty:
        raise ValueError("no observations remain after if / missing handling")

    y_raw = sub[depvar]
    y = pd.to_numeric(y_raw, errors="coerce").to_numpy(dtype=float)
    uniq = np.unique(y[~np.isnan(y)])
    if not set(uniq.tolist()).issubset({0.0, 1.0}):
        raise ValueError(
            f"logit requires a 0/1 outcome; {depvar!r} contains values {sorted(uniq.tolist())}"
        )

    terms = parse_indepvars(indepvars)
    design = build_design(sub, terms, add_constant=True)
    X = design.X.to_numpy(dtype=float)

    fit_kwargs: dict = {"disp": False}
    if vce == "robust":
        fit_kwargs["cov_type"] = "HC1"
    elif vce == "cluster":
        fit_kwargs["cov_type"] = "cluster"
        fit_kwargs["cov_kwds"] = {"groups": sub[cluster].to_numpy()}

    model = sm.Logit(y, X).fit(**fit_kwargs)

    coef_table = _build_logit_table(design.column_names, model, odds_ratios=odds_ratios)

    n = int(model.nobs)
    df_m = int(model.df_model)
    ll = float(model.llf)
    ll_0 = float(model.llnull) if hasattr(model, "llnull") else None
    pseudo_r2 = float(model.prsquared) if hasattr(model, "prsquared") else None
    chi2 = None
    chi2_p = None
    try:
        chi2 = float(model.llr)
        chi2_p = float(model.llr_pvalue)
    except Exception:  # noqa: BLE001
        pass

    header = {
        "N": n,
        "df_m": df_m,
        "LR_chi2": _safe(chi2),
        "Prob_chi2": _safe(chi2_p),
        "Pseudo_R2": _safe(pseudo_r2),
        "log_likelihood": _safe(ll),
        "log_likelihood_null": _safe(ll_0),
        "vce": vce,
        "cluster": cluster,
        "odds_ratios": odds_ratios,
    }

    structured = {
        "command": _format_command(depvar, indepvars, odds_ratios, vce, cluster, if_expr, in_range),
        "kind": "logit",
        "depvar": depvar,
        "indepvars": indepvars,
        "header": header,
        "coefficients": coef_table,
        "design_columns": design.column_names,
    }

    title = "Logistic regression" + (" (odds ratios)" if odds_ratios else "")
    text = render_logit_table(
        title=title,
        depvar=depvar,
        header=header,
        coef_rows=coef_table,
        odds_ratios=odds_ratios,
    )

    e_update = {
        "cmd": "logit",
        "depvar": depvar,
        "N": n,
        "df_m": df_m,
        "ll": _safe(ll),
        "ll_0": _safe(ll_0),
        "chi2": _safe(chi2),
        "p": _safe(chi2_p),
        "r2_p": _safe(pseudo_r2),
        "vce": vce,
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
        cmd_kind="logit",
        depvar=depvar,
        indepvars=list(indepvars),
        design_columns=design.column_names,
        frame_name=frame_name,
        n_obs=n,
        if_expr=if_expr,
        in_range=in_range,
        cluster=cluster,
        model=model,
        extra={"odds_ratios": odds_ratios},
    )
    return result, estimation


# ===================================================================
# Helpers
# ===================================================================

def _build_logit_table(names: list[str], model, *, odds_ratios: bool) -> list[dict]:
    params = model.params
    bse = model.bse
    zvals = model.tvalues  # statsmodels reports z under MLE
    pvals = model.pvalues
    ci = np.asarray(model.conf_int(alpha=0.05))

    rows: list[dict] = []
    for i, name in enumerate(names):
        coef = float(params[i])
        se = float(bse[i])
        z = float(zvals[i])
        p = float(pvals[i])
        lo, hi = float(ci[i, 0]), float(ci[i, 1])

        display_coef = np.exp(coef) if odds_ratios else coef
        display_se = display_coef * se if odds_ratios else se  # delta-method SE for OR
        display_lo = np.exp(lo) if odds_ratios else lo
        display_hi = np.exp(hi) if odds_ratios else hi

        rows.append({
            "name":        name,
            "coef":        _safe(display_coef),
            "se":          _safe(display_se),
            "z":           _safe(z),
            "p":           _safe(p),
            "ci_low":      _safe(display_lo),
            "ci_high":     _safe(display_hi),
            "raw_coef":    _safe(coef),
            "raw_se":      _safe(se),
            "significant": bool(p < 0.05),
        })
    return rows


def _format_command(
    depvar: str,
    indepvars: list[str],
    odds_ratios: bool,
    vce: str,
    cluster: str | None,
    if_expr: str | None,
    in_range: str | None,
) -> str:
    cmd = "logistic" if odds_ratios else "logit"
    parts = [cmd, depvar, *indepvars]
    if if_expr:
        parts.append(f"if {if_expr}")
    if in_range:
        parts.append(f"in {in_range}")
    options: list[str] = []
    if vce == "robust":
        options.append("vce(robust)")
    elif vce == "cluster":
        options.append(f"vce(cluster {cluster})")
    out = " ".join(parts)
    if options:
        out += ", " + " ".join(options)
    return out
