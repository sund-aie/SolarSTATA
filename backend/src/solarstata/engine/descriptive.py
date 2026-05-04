"""Descriptive statistics — Stata `summarize`."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sp

from .formatters import render_summarize
from .results import Result


def _round(value, ndigits: int = 6):
    if value is None:
        return None
    f = float(value)
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, ndigits)


def summarize(
    df: pd.DataFrame,
    variables: list[str] | None = None,
    *,
    detail: bool = False,
) -> Result:
    """Stata `summarize [varlist] [, detail]`.

    Defaults to all numeric variables in the frame. Each row in the
    returned structured payload has Obs/Mean/SD/Min/Max; with detail=True
    we also report variance, skewness, kurtosis, and 1/5/10/25/50/75/90/95/99
    percentiles.

    Mirrors `archive/v1-v2/stats_engine.py:descriptive` for math parity;
    rewritten here against the new Result contract.
    """
    if variables is None:
        variables = df.select_dtypes(include=[np.number]).columns.tolist()

    rows: list[dict] = []
    for var in variables:
        if var not in df.columns:
            continue
        col = pd.to_numeric(df[var], errors="coerce").dropna()
        if col.empty:
            rows.append({"Variable": var, "Obs": 0})
            continue
        row = {
            "Variable": var,
            "Obs": int(len(col)),
            "Mean": _round(col.mean()),
            "SD": _round(col.std(ddof=1)),
            "Min": _round(col.min()),
            "Max": _round(col.max()),
        }
        if detail:
            row.update({
                "Variance": _round(col.var(ddof=1)),
                "Skewness": _round(sp.skew(col, bias=False)),
                "Kurtosis": _round(sp.kurtosis(col, bias=False, fisher=False)),
                "p1": _round(np.percentile(col, 1)),
                "p5": _round(np.percentile(col, 5)),
                "p10": _round(np.percentile(col, 10)),
                "p25": _round(np.percentile(col, 25)),
                "p50": _round(np.percentile(col, 50)),
                "p75": _round(np.percentile(col, 75)),
                "p90": _round(np.percentile(col, 90)),
                "p95": _round(np.percentile(col, 95)),
                "p99": _round(np.percentile(col, 99)),
            })
        rows.append(row)

    text = render_summarize(rows, detail=detail)

    # Stata's summarize sets r(N), r(mean), r(Var), r(min), r(max) for the
    # last variable processed. Mirror that contract.
    r_update: dict = {}
    if rows and rows[-1].get("Obs", 0) > 0:
        last = rows[-1]
        r_update = {
            "N": last["Obs"],
            "mean": last["Mean"],
            "Var": last.get("Variance"),
            "sd": last["SD"],
            "min": last["Min"],
            "max": last["Max"],
        }

    cmd = "summarize " + " ".join(variables) + (", detail" if detail else "")
    return Result(
        command=cmd.strip(),
        structured={"variables": rows, "detail": detail},
        text=text,
        r_update=r_update,
    )
