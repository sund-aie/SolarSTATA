"""Plotly figure builders.

Every function returns a Plotly JSON-shaped dict ({data, layout}) ready
for `react-plotly.js` to render. We keep the figure layouts minimal —
just the warm-gold accent, transparent background, and a stable title
shape — and let the frontend's Plot wrapper apply theme-specific tweaks
(font color, axis grid color, paper background) when the user toggles
light mode.

Chart types
-----------
  histogram(df, var, *, bins=20, group=None)
  scatter(df, x, y, *, group=None)
  box(df, var, *, group=None)
  bar_with_ci(df, var, *, group=None, ci=0.95)
  line(df, x, y, *, group=None)
  residuals_vs_fitted(df, estimation)
  marginsplot(margins_result)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp

ACCENT = "#D4B36A"
ACCENT_SOFT = "rgba(212, 179, 106, 0.55)"
INFO = "#8FA8C4"
GOOD = "#8FAA88"
WARN = "#D89B7E"

# Color cycle for grouped plots — gold first, then info/good/warn shades.
PALETTE = [ACCENT, INFO, GOOD, WARN, "#B4A0D2", "#8FAA88", "#D89B7E"]


def _layout(title: str, x_title: str = "", y_title: str = "") -> dict[str, Any]:
    """Minimal-styled layout. Frontend Plot wrapper overlays theme colors."""
    return {
        "title": {"text": title, "font": {"family": "Instrument Serif, serif", "size": 18}},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Geist, sans-serif", "size": 12},
        "margin": {"l": 50, "r": 20, "t": 50, "b": 50},
        "xaxis": {"title": {"text": x_title}, "gridcolor": "#3A3529", "zerolinecolor": "#3A3529"},
        "yaxis": {"title": {"text": y_title}, "gridcolor": "#3A3529", "zerolinecolor": "#3A3529"},
        "legend": {"bgcolor": "rgba(0,0,0,0)"},
    }


def _color_for(i: int) -> str:
    return PALETTE[i % len(PALETTE)]


# ===================================================================
# histogram
# ===================================================================

def histogram(df: pd.DataFrame, var: str, *, bins: int = 20, group: str | None = None) -> dict:
    if var not in df.columns:
        raise KeyError(f"variable {var!r} not in dataset")
    series = pd.to_numeric(df[var], errors="coerce").dropna()

    if group and group in df.columns:
        data = []
        for i, (lvl, sub) in enumerate(df.groupby(group, dropna=True)):
            s = pd.to_numeric(sub[var], errors="coerce").dropna()
            data.append({
                "type": "histogram",
                "x": s.tolist(),
                "nbinsx": bins,
                "name": str(lvl),
                "marker": {"color": _color_for(i)},
                "opacity": 0.65,
            })
        layout = _layout(f"{var} by {group}", x_title=var, y_title="Frequency")
        layout["barmode"] = "overlay"
        return {"data": data, "layout": layout}

    return {
        "data": [{
            "type": "histogram",
            "x": series.tolist(),
            "nbinsx": bins,
            "marker": {"color": ACCENT, "line": {"color": ACCENT_SOFT, "width": 1}},
        }],
        "layout": _layout(f"Distribution of {var}", x_title=var, y_title="Frequency"),
    }


# ===================================================================
# scatter
# ===================================================================

def scatter(df: pd.DataFrame, x: str, y: str, *, group: str | None = None) -> dict:
    for v in (x, y):
        if v not in df.columns:
            raise KeyError(f"variable {v!r} not in dataset")

    if group and group in df.columns:
        traces = []
        for i, (lvl, sub) in enumerate(df.dropna(subset=[x, y]).groupby(group, dropna=True)):
            traces.append({
                "type": "scatter",
                "mode": "markers",
                "x": pd.to_numeric(sub[x], errors="coerce").tolist(),
                "y": pd.to_numeric(sub[y], errors="coerce").tolist(),
                "name": str(lvl),
                "marker": {"color": _color_for(i), "size": 6, "opacity": 0.75,
                           "line": {"width": 0}},
            })
        return {"data": traces, "layout": _layout(f"{y} vs {x} by {group}", x, y)}

    sub = df[[x, y]].dropna()
    return {
        "data": [{
            "type": "scatter",
            "mode": "markers",
            "x": pd.to_numeric(sub[x], errors="coerce").tolist(),
            "y": pd.to_numeric(sub[y], errors="coerce").tolist(),
            "marker": {"color": ACCENT, "size": 6, "opacity": 0.75, "line": {"width": 0}},
        }],
        "layout": _layout(f"{y} vs {x}", x, y),
    }


# ===================================================================
# box
# ===================================================================

def box(df: pd.DataFrame, var: str, *, group: str | None = None) -> dict:
    if var not in df.columns:
        raise KeyError(f"variable {var!r} not in dataset")

    if group and group in df.columns:
        traces = []
        for i, (lvl, sub) in enumerate(df.groupby(group, dropna=True)):
            s = pd.to_numeric(sub[var], errors="coerce").dropna()
            traces.append({
                "type": "box",
                "y": s.tolist(),
                "name": str(lvl),
                "marker": {"color": _color_for(i)},
                "boxmean": True,
            })
        return {"data": traces, "layout": _layout(f"{var} by {group}", group, var)}

    s = pd.to_numeric(df[var], errors="coerce").dropna()
    return {
        "data": [{
            "type": "box",
            "y": s.tolist(),
            "name": var,
            "marker": {"color": ACCENT},
            "boxmean": True,
        }],
        "layout": _layout(f"Box plot — {var}", "", var),
    }


# ===================================================================
# bar with CI
# ===================================================================

def bar_with_ci(df: pd.DataFrame, var: str, *, group: str | None = None, ci: float = 0.95) -> dict:
    if var not in df.columns:
        raise KeyError(f"variable {var!r} not in dataset")
    if not group or group not in df.columns:
        s = pd.to_numeric(df[var], errors="coerce").dropna()
        m, se = float(s.mean()), float(sp.sem(s)) if len(s) > 1 else 0.0
        half = sp.t.ppf((1 + ci) / 2, df=max(1, len(s) - 1)) * se if len(s) > 1 else 0.0
        return {
            "data": [{
                "type": "bar",
                "x": [var],
                "y": [m],
                "error_y": {"type": "data", "array": [half], "visible": True,
                            "color": INFO, "thickness": 1.5, "width": 8},
                "marker": {"color": ACCENT},
            }],
            "layout": _layout(f"Mean of {var} (95% CI)", "", f"mean {var}"),
        }

    xs: list[str] = []
    ys: list[float] = []
    errs: list[float] = []
    for lvl, sub in df.groupby(group, dropna=True):
        s = pd.to_numeric(sub[var], errors="coerce").dropna()
        if len(s) < 1:
            continue
        m = float(s.mean())
        se = float(sp.sem(s)) if len(s) > 1 else 0.0
        half = sp.t.ppf((1 + ci) / 2, df=max(1, len(s) - 1)) * se if len(s) > 1 else 0.0
        xs.append(str(lvl))
        ys.append(m)
        errs.append(half)

    return {
        "data": [{
            "type": "bar",
            "x": xs,
            "y": ys,
            "error_y": {"type": "data", "array": errs, "visible": True,
                        "color": INFO, "thickness": 1.5, "width": 8},
            "marker": {"color": ACCENT},
        }],
        "layout": _layout(f"Mean {var} by {group} (95% CI)", group, f"mean {var}"),
    }


# ===================================================================
# line
# ===================================================================

def line(df: pd.DataFrame, x: str, y: str, *, group: str | None = None) -> dict:
    for v in (x, y):
        if v not in df.columns:
            raise KeyError(f"variable {v!r} not in dataset")

    def _trace(sub: pd.DataFrame, color: str, name: str) -> dict:
        sub = sub.sort_values(x)
        return {
            "type": "scatter",
            "mode": "lines+markers",
            "x": pd.to_numeric(sub[x], errors="coerce").tolist(),
            "y": pd.to_numeric(sub[y], errors="coerce").tolist(),
            "name": name,
            "line": {"color": color, "width": 2},
            "marker": {"color": color, "size": 5},
        }

    if group and group in df.columns:
        traces = []
        for i, (lvl, sub) in enumerate(df.dropna(subset=[x, y]).groupby(group, dropna=True)):
            traces.append(_trace(sub, _color_for(i), str(lvl)))
        return {"data": traces, "layout": _layout(f"{y} over {x} by {group}", x, y)}

    return {
        "data": [_trace(df.dropna(subset=[x, y]), ACCENT, y)],
        "layout": _layout(f"{y} over {x}", x, y),
    }


# ===================================================================
# residuals vs fitted (after regress)
# ===================================================================

def residuals_vs_fitted(df: pd.DataFrame, estimation: Any) -> dict:
    """Diagnostic plot for OLS: residuals on the y-axis vs fitted values on x."""
    if estimation is None:
        raise ValueError("no estimates stored — run regress first")
    if estimation.cmd_kind != "regress":
        raise ValueError("residuals-vs-fitted plot only follows regress")

    from .factor import build_design, parse_indepvars
    from .qualifiers import apply_if, apply_in
    from .postest import _all_referenced_vars

    needed = _all_referenced_vars(estimation.indepvars)
    sub = apply_in(apply_if(df, estimation.if_expr), estimation.in_range)
    sub = sub.dropna(subset=[c for c in needed | {estimation.depvar} if c in sub.columns])
    terms = parse_indepvars(estimation.indepvars)
    design = build_design(sub, terms, add_constant=True)
    X = design.X.to_numpy(dtype=float)
    y = pd.to_numeric(sub[estimation.depvar], errors="coerce").to_numpy(dtype=float)

    yhat = estimation.model.predict(X)
    resid = y - yhat

    layout = _layout("Residuals vs fitted values",
                     x_title=f"Fitted {estimation.depvar}",
                     y_title="Residual")
    return {
        "data": [
            {
                "type": "scatter",
                "mode": "markers",
                "x": yhat.tolist(),
                "y": resid.tolist(),
                "marker": {"color": ACCENT, "size": 6, "opacity": 0.7, "line": {"width": 0}},
                "name": "residual",
            },
            {
                "type": "scatter",
                "mode": "lines",
                "x": [float(yhat.min()), float(yhat.max())],
                "y": [0, 0],
                "line": {"color": INFO, "width": 1, "dash": "dash"},
                "name": "y = 0",
                "hoverinfo": "skip",
            },
        ],
        "layout": layout,
    }


# ===================================================================
# marginsplot
# ===================================================================

def marginsplot(margins_result: dict) -> dict:
    """Render the per-predictor AME bars with 95% CI from a margins result."""
    rows = margins_result.get("rows") or []
    if not rows:
        raise ValueError("margins result has no rows to plot")

    names = [r["name"] for r in rows]
    effects = [r["dy_dx"] for r in rows]
    los = [r["ci_low"] for r in rows]
    his = [r["ci_high"] for r in rows]
    half = [
        (h - e) if (h is not None and e is not None) else 0
        for e, h in zip(effects, his)
    ]
    half_lo = [
        (e - l) if (l is not None and e is not None) else 0
        for e, l in zip(effects, los)
    ]
    layout = _layout("Average marginal effects", "Variable", "dy/dx")
    return {
        "data": [{
            "type": "scatter",
            "mode": "markers",
            "x": names,
            "y": effects,
            "error_y": {
                "type": "data",
                "symmetric": False,
                "array": half,
                "arrayminus": half_lo,
                "color": INFO,
                "thickness": 1.5,
                "width": 8,
            },
            "marker": {"color": ACCENT, "size": 10, "line": {"width": 0}},
        }],
        "layout": layout,
    }
