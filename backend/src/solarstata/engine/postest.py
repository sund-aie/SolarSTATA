"""Postestimation: predict, margins, test, lincom, estat ic, estat vif.

Reads the most recent estimation off the session, never the dataset
metadata directly. The fitted statsmodels Results object is the source
of truth for params, vcov, residuals, and predictions.
"""

from __future__ import annotations

import re
from typing import Any, Literal

import numpy as np
import pandas as pd
from statsmodels.stats.outliers_influence import variance_inflation_factor

from .factor import build_design, parse_indepvars
from .qualifiers import apply_if, apply_in
from .results import Result


# ===================================================================
# predict
# ===================================================================

PredictKind = Literal["xb", "resid", "pr", "stdp"]


def predict(
    df: pd.DataFrame,
    estimation: Any,                 # session.last_estimation
    *,
    kind: PredictKind = "xb",
    new_var: str = "fitted_values",
) -> tuple[Result, pd.Series]:
    """Generate predictions and return (Result, new_column).

    Caller is responsible for assigning the returned Series back into the
    frame's DataFrame as `df[new_var] = series` (mirrors Stata's behavior:
    missings fill where predictors were missing).
    """
    if estimation is None:
        raise ValueError("no estimates stored — run regress or logit first")

    cmd = estimation.cmd_kind

    if kind == "pr" and cmd != "logit":
        raise ValueError("option 'pr' is only valid after logit")
    if kind == "resid" and cmd != "regress":
        raise ValueError("option 'resid' is only valid after regress")

    indepvars = estimation.indepvars
    needed = _all_referenced_vars(indepvars)
    # Replay the fit-time qualifiers so factor levels match exactly.
    sub = apply_in(apply_if(df, estimation.if_expr), estimation.in_range)
    available_rows = sub.dropna(subset=[c for c in needed if c in sub.columns])

    if available_rows.empty:
        out = pd.Series([np.nan] * len(df), index=df.index, name=new_var)
        return _predict_result(estimation, kind, new_var, n_filled=0), out

    terms = parse_indepvars(indepvars)
    design = build_design(available_rows, terms, add_constant=True)
    X = design.X.to_numpy(dtype=float)

    model = estimation.model
    if cmd == "regress":
        if kind == "xb":
            preds = model.predict(X)
        elif kind == "resid":
            yhat = model.predict(X)
            y = pd.to_numeric(available_rows[estimation.depvar], errors="coerce").to_numpy(dtype=float)
            preds = y - yhat
        else:
            raise ValueError(f"predict kind {kind!r} not supported after regress")
    elif cmd == "logit":
        if kind == "pr":
            preds = model.predict(X)               # probabilities by default
        elif kind == "xb":
            preds = X @ model.params               # linear predictor
        else:
            raise ValueError(f"predict kind {kind!r} not supported after logit")
    else:
        raise ValueError(f"predict not implemented for {cmd!r}")

    out = pd.Series([np.nan] * len(df), index=df.index, name=new_var, dtype=float)
    out.loc[available_rows.index] = preds

    return _predict_result(estimation, kind, new_var, n_filled=int(len(available_rows))), out


def _predict_result(estimation, kind: str, new_var: str, *, n_filled: int) -> Result:
    label = {"xb": "linear predictor", "resid": "residuals", "pr": "Pr(y=1)", "stdp": "SE of xb"}[kind]
    cmd = f"predict {new_var}" + (f", {kind}" if kind != "xb" else "")
    text = f"({n_filled} non-missing predictions written to {new_var}: {label})"
    return Result(
        command=cmd,
        structured={
            "kind": "predict",
            "new_var": new_var,
            "predict_kind": kind,
            "label": label,
            "n_filled": n_filled,
        },
        text=text,
    )


# ===================================================================
# margins (Average Marginal Effects)
# ===================================================================

def margins(
    df: pd.DataFrame,
    estimation: Any,
    *,
    at_means: bool = False,
) -> Result:
    """AME by default; `at_means=True` switches to MEM.

    Returns rows for the *original* indepvar tokens (not expanded design
    columns) — that's what users expect from Stata's `margins, dydx(*)`.
    """
    if estimation is None:
        raise ValueError("no estimates stored — run regress or logit first")

    indepvars = estimation.indepvars
    needed = _all_referenced_vars(indepvars)
    sub = apply_in(apply_if(df, estimation.if_expr), estimation.in_range)
    sub = sub.dropna(subset=[c for c in needed if c in sub.columns])
    if sub.empty:
        raise ValueError("no observations available for margins")

    model = estimation.model
    cmd = estimation.cmd_kind

    rows: list[dict] = []
    design_cols = [c for c in estimation.design_columns if c != "_cons"]

    if cmd == "logit":
        # Logit gets proper AMEs via statsmodels' delta-method machinery.
        margeff = model.get_margeff(at="overall" if not at_means else "mean")
        summary = margeff.summary_frame()
        for i, name in enumerate(design_cols):
            if i >= len(summary):
                break
            row = summary.iloc[i]
            rows.append({
                "name": name,
                "dy_dx": _safe(float(row.iloc[0])),
                "se":    _safe(float(row.iloc[1])),
                "z":     _safe(float(row.iloc[2])),
                "p":     _safe(float(row.iloc[3])),
                "ci_low": _safe(float(row.iloc[4])),
                "ci_high": _safe(float(row.iloc[5])),
                "significant": bool(float(row.iloc[3]) < 0.05),
            })
    elif cmd == "regress":
        # Linear regression: AME of a main-effect predictor IS the coefficient
        # itself (with its own SE). For interaction terms this approximation
        # breaks; Phase 3 doesn't try to disentangle ## / # interactions.
        for i, name in enumerate(estimation.design_columns):
            if name == "_cons":
                continue
            coef = float(model.params[i])
            se = float(model.bse[i])
            z = float(model.tvalues[i])
            p = float(model.pvalues[i])
            ci = np.asarray(model.conf_int(alpha=0.05))[i]
            rows.append({
                "name": name,
                "dy_dx": _safe(coef),
                "se":    _safe(se),
                "z":     _safe(z),
                "p":     _safe(p),
                "ci_low": _safe(float(ci[0])),
                "ci_high": _safe(float(ci[1])),
                "significant": bool(p < 0.05),
            })
    else:
        raise ValueError(f"margins not implemented for {cmd!r}")

    text_lines = ["", "Average marginal effects" if not at_means else "Marginal effects at means", ""]
    text_lines.append(f"{'Variable':>20}  {'dy/dx':>10}  {'Std. err.':>10}  {'z':>7}  {'P>|z|':>8}")
    text_lines.append("-" * 60)
    for r in rows:
        text_lines.append(
            f"{r['name']:>20}  {_fmt(r['dy_dx'], 10)}  {_fmt(r['se'], 10)}  "
            f"{_fmt(r['z'], 7, 2)}  {_fmt(r['p'], 8, 4)}"
        )

    cmd = "margins" + (", atmeans" if at_means else "")
    return Result(
        command=cmd,
        structured={
            "kind": "margins",
            "at_means": at_means,
            "rows": rows,
            "depvar": estimation.depvar,
            "for_command": estimation.cmd_kind,
        },
        text="\n".join(text_lines),
    )


# ===================================================================
# test (Wald)
# ===================================================================

def wald_test(estimation: Any, restrictions: list[str]) -> Result:
    """`test x1 = 0`, `test x1 = x2`, `test x1 x2` (joint = 0).

    We build the contrast matrix R directly against the fitted model's
    coefficient ordering so we don't depend on name-aware parsing
    (statsmodels models built from raw ndarrays have no column names for
    patsy to bind against).
    """
    if estimation is None:
        raise ValueError("no estimates stored — run regress or logit first")
    if not restrictions:
        raise ValueError("test requires at least one restriction")

    normalized: list[str] = []
    bare_names: list[str] = []
    for r in restrictions:
        r = r.strip()
        if "=" in r:
            normalized.append(r)
        else:
            bare_names.append(r)
    if bare_names and not normalized:
        normalized = [f"{n} = 0" for n in bare_names]
    elif bare_names:
        normalized.extend(f"{n} = 0" for n in bare_names)

    model = estimation.model
    cols = estimation.design_columns
    name_to_idx = {name: i for i, name in enumerate(cols)}

    R_rows: list[np.ndarray] = []
    q_rows: list[float] = []
    for r in normalized:
        lhs, rhs = (s.strip() for s in r.split("=", 1))
        if rhs not in ("0", "0.0"):
            # equality between two coefs: lhs - rhs = 0
            row = np.zeros(len(cols))
            if lhs not in name_to_idx or rhs not in name_to_idx:
                raise ValueError(f"unknown coefficient in restriction {r!r}")
            row[name_to_idx[lhs]] = 1.0
            row[name_to_idx[rhs]] = -1.0
            q_rows.append(0.0)
        else:
            if lhs not in name_to_idx:
                raise ValueError(f"unknown coefficient: {lhs!r}")
            row = np.zeros(len(cols))
            row[name_to_idx[lhs]] = 1.0
            q_rows.append(0.0)
        R_rows.append(row)

    R = np.vstack(R_rows)
    test_obj = model.wald_test(R, scalar=True)

    fval = float(test_obj.fvalue) if hasattr(test_obj, "fvalue") and test_obj.fvalue is not None else None
    chi2 = float(test_obj.statistic) if hasattr(test_obj, "statistic") else None
    pval = float(test_obj.pvalue) if hasattr(test_obj, "pvalue") else None
    df_num = int(test_obj.df_num) if hasattr(test_obj, "df_num") and test_obj.df_num is not None else None
    df_denom = int(test_obj.df_denom) if hasattr(test_obj, "df_denom") and test_obj.df_denom is not None else None

    text = ["", " ( 1)  " + " = 0\n ( 1)  ".join(normalized)]
    if fval is not None and df_num is not None and df_denom is not None:
        text.append(f"\n       F( {df_num}, {df_denom}) = {fval:>9.4f}")
    if pval is not None:
        text.append(f"          Prob > F = {pval:.4f}")
    text_str = "\n".join(text)

    return Result(
        command=f"test {' '.join(restrictions)}",
        structured={
            "kind": "test",
            "restrictions": normalized,
            "F": _safe(fval),
            "chi2": _safe(chi2),
            "p": _safe(pval),
            "df_num": df_num,
            "df_denom": df_denom,
        },
        text=text_str,
    )


# ===================================================================
# lincom
# ===================================================================

def lincom(estimation: Any, expression: str) -> Result:
    """`lincom x1 + 0.5*x2` etc. — returns point estimate, SE, t, p, CI."""
    if estimation is None:
        raise ValueError("no estimates stored")
    expr = expression.strip()
    if not expr:
        raise ValueError("lincom requires an expression")

    model = estimation.model

    cols = estimation.design_columns
    name_to_idx = {name: i for i, name in enumerate(cols)}

    # Parse `expr` as a linear combination: sum of `coef * varname` terms with
    # optional sign. Phase 3 supports `x`, `2*x`, `x + y`, `x - y`, `2*x - 3*y`.
    contrast = np.zeros(len(cols))
    cleaned = expr.replace(" ", "")
    # Split on + / - while keeping the sign.
    tokens: list[tuple[float, str]] = []
    current_sign = 1.0
    buf = ""
    for ch in cleaned:
        if ch in "+-" and buf:
            coef, name = _parse_lincom_term(buf, current_sign)
            tokens.append((coef, name))
            buf = ""
            current_sign = 1.0 if ch == "+" else -1.0
        elif ch == "-" and not buf:
            current_sign = -current_sign
        else:
            buf += ch
    if buf:
        coef, name = _parse_lincom_term(buf, current_sign)
        tokens.append((coef, name))

    for coef, name in tokens:
        if name not in name_to_idx:
            raise ValueError(f"unknown coefficient {name!r} in lincom expression")
        contrast[name_to_idx[name]] += coef

    test_obj = model.t_test(contrast)

    eff = float(np.asarray(test_obj.effect).flatten()[0])
    se = float(np.asarray(test_obj.sd).flatten()[0])
    t = float(np.asarray(test_obj.tvalue).flatten()[0])
    p = float(np.asarray(test_obj.pvalue).flatten()[0])
    ci = np.asarray(test_obj.conf_int(alpha=0.05)).flatten()
    ci_lo, ci_hi = float(ci[0]), float(ci[1])

    rows = [{
        "label": "(1)",
        "expression": expr,
        "estimate": _safe(eff),
        "se": _safe(se),
        "t": _safe(t),
        "p": _safe(p),
        "ci_low": _safe(ci_lo),
        "ci_high": _safe(ci_hi),
    }]
    text = (
        f"\n ( 1)  {expr}\n\n"
        f"{'Coefficient':>12}{'Std. err.':>11}{'t':>8}{'P>|t|':>9}     [95% conf. interval]\n"
        + "-" * 64
        + f"\n{eff:>12.6f}{se:>11.6f}{t:>8.2f}{p:>9.4f}{ci_lo:>14.6f}{ci_hi:>12.6f}"
    )

    return Result(
        command=f"lincom {expr}",
        structured={"kind": "lincom", "rows": rows},
        text=text,
    )


# ===================================================================
# estat ic / estat vif
# ===================================================================

def estat_ic(estimation: Any) -> Result:
    if estimation is None:
        raise ValueError("no estimates stored")
    model = estimation.model
    n = int(model.nobs)
    df_m = int(model.df_model) + 1  # +1 for the constant
    ll = float(getattr(model, "llf", np.nan))
    aic = float(getattr(model, "aic", np.nan))
    bic = float(getattr(model, "bic", np.nan))

    structured = {
        "kind": "estat_ic",
        "rows": [{
            "model": estimation.cmd_kind,
            "N": n,
            "df": df_m,
            "ll": _safe(ll),
            "AIC": _safe(aic),
            "BIC": _safe(bic),
        }],
    }
    text = (
        "\nAkaike's information criterion and Bayesian information criterion\n\n"
        f"     Model |  Obs    df       ll(null)         ll       AIC         BIC\n"
        f"-----------+----------------------------------------------------------\n"
        f"  {estimation.cmd_kind:>8}  {n:>5}  {df_m:>4}        .      {ll:>10.4f}  {aic:>10.4f}  {bic:>10.4f}"
    )
    return Result(command="estat ic", structured=structured, text=text)


def estat_vif(df: pd.DataFrame, estimation: Any) -> Result:
    if estimation is None:
        raise ValueError("no estimates stored")
    if estimation.cmd_kind != "regress":
        raise ValueError("estat vif only follows regress")

    needed = _all_referenced_vars(estimation.indepvars)
    sub = apply_in(apply_if(df, estimation.if_expr), estimation.in_range)
    sub = sub.dropna(subset=[c for c in needed if c in sub.columns])
    terms = parse_indepvars(estimation.indepvars)
    design = build_design(sub, terms, add_constant=True)
    X = design.X.to_numpy(dtype=float)
    cols = design.column_names

    rows: list[dict] = []
    for i, name in enumerate(cols):
        if name == "_cons":
            continue
        try:
            v = float(variance_inflation_factor(X, i))
        except Exception:  # noqa: BLE001 — singular matrices, etc.
            v = float("nan")
        rows.append({"name": name, "vif": _safe(v), "tolerance": _safe(1.0 / v) if v else None})

    mean_vif = (sum((r["vif"] or 0.0) for r in rows) / len(rows)) if rows else 0.0

    text_lines = ["", "    Variable |       VIF       1/VIF", "-------------+----------------------"]
    for r in rows:
        text_lines.append(f"  {r['name']:>10} |  {(r['vif'] or 0):>8.2f}    {(r['tolerance'] or 0):>8.4f}")
    text_lines.append("-------------+----------------------")
    text_lines.append(f"    Mean VIF |  {mean_vif:>8.2f}")
    return Result(
        command="estat vif",
        structured={"kind": "estat_vif", "rows": rows, "mean_vif": _safe(mean_vif)},
        text="\n".join(text_lines),
    )


# ===================================================================
# Helpers
# ===================================================================

def _parse_lincom_term(buf: str, sign: float) -> tuple[float, str]:
    """`2*x` -> (2, 'x'); `x` -> (1, 'x'); honours sign from caller."""
    if "*" in buf:
        coef_str, name = buf.split("*", 1)
        try:
            coef = float(coef_str) * sign
        except ValueError:
            raise ValueError(f"could not parse coefficient {coef_str!r}")
        return coef, name
    return sign, buf


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


def _fmt(v, w: int = 10, prec: int = 4) -> str:
    if v is None:
        return f"{'.':>{w}}"
    return f"{v:>{w}.{prec}f}"
