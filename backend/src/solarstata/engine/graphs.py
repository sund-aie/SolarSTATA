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
  bar_with_ci(df, var, *, group=None, err="ci95", ci=0.95)
  line(df, x, y, *, group=None, err="none", ci=0.95)
  residuals_vs_fitted(df, estimation)
  marginsplot(margins_result)

Error-bar source control (v3.2): `err` picks between
  "none" — no error bars (the only backward-compat option for line)
  "sd"   — sample standard deviation
  "sem"  — standard error of the mean (sd / sqrt(n))
  "ci95" — half-width of the 95% confidence interval (t-based)
The chosen indicator is appended to the y-axis label as
"mean VHN ± SD" / "± SEM" / "± 95% CI" so the figure self-labels.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats as sp


ErrSource = Literal["none", "sd", "sem", "ci95"]


def _half_spread(s: pd.Series, *, err: ErrSource, ci: float) -> float:
    """Return the half-width to use for Plotly's symmetric error_y bars.

    SD: sample standard deviation. SEM: std / sqrt(n). CI95: t-based
    half-interval at the chosen confidence level (default 0.95).
    None or n < 2: zero.
    """
    if err == "none" or len(s) < 2:
        return 0.0
    if err == "sd":
        return float(s.std(ddof=1))
    if err == "sem":
        return float(sp.sem(s))
    # ci95 (and any future "ci99" etc.) routes through t.ppf
    se = float(sp.sem(s))
    return float(sp.t.ppf((1 + ci) / 2, df=max(1, len(s) - 1)) * se)


def _err_suffix(err: ErrSource) -> str:
    """Human-readable indicator appended to the y-axis label."""
    if err == "sd":
        return " ± SD"
    if err == "sem":
        return " ± SEM"
    if err == "ci95":
        return " ± 95% CI"
    return ""


def _stars_tier(p_adj: float) -> str | None:
    """Significance-star tier — publication convention.

    *** = p < .001, ** = p < .01, * = p < .05. Strict inequalities;
    p = .05 (or above) returns None (no bracket).
    """
    if p_adj < 0.001:
        return "***"
    if p_adj < 0.01:
        return "**"
    if p_adj < 0.05:
        return "*"
    return None


def _emit_brackets(
    raw_keys: list[str],
    xs: list[str],
    ys: list[float],
    errs: list[float],
    pairwise: dict,
) -> tuple[list[dict], list[dict]]:
    """Build Plotly shapes + annotations for significance brackets.

    Reads the pairwise matrix produced by oneway's _pairwise (we do
    not recompute anything). Only pairs with `p_adj < 0.05` get a
    bracket. Brackets stack above the tallest bar/error-bar tip:
    tightest spans drawn lowest, wider spans stacked above.

    `raw_keys` are the engine's stringified group values (what the
    pairwise comparisons key off); `xs` are the corresponding axis
    labels (what Plotly draws). They line up index-for-index.
    """
    if not pairwise or not isinstance(pairwise.get("comparisons"), list):
        return [], []

    index: dict[str, int] = {name: i for i, name in enumerate(raw_keys)}
    if len(index) < 2:
        return [], []

    # Bracket base sits above the tallest error-bar tip; step size
    # scales with the overall y-range so brackets stay legible
    # regardless of measurement units.
    tops = [(ys[i] + errs[i]) for i in range(len(xs))]
    overall_top = max(tops) if tops else 0.0
    overall_bottom = min(min(ys), 0.0) if ys else 0.0
    span = max(overall_top - overall_bottom, abs(overall_top), 1.0)
    step = span * 0.08
    base = overall_top + step * 0.6

    # Collect significant pairs that both name a bar in the chart.
    sig: list[tuple[int, int, str]] = []
    for cmp in pairwise["comparisons"]:
        a = cmp.get("a")
        b = cmp.get("b")
        p_adj = cmp.get("p_adj")
        if a is None or b is None or p_adj is None:
            continue
        if a not in index or b not in index:
            continue
        stars = _stars_tier(float(p_adj))
        if stars is None:
            continue
        i_a, i_b = index[a], index[b]
        if i_a == i_b:
            continue
        if i_a > i_b:
            i_a, i_b = i_b, i_a
        sig.append((i_a, i_b, stars))

    # Stack: tightest spans on the bottom, wider above. Tie-break by
    # leftmost endpoint so output is deterministic.
    sig.sort(key=lambda t: (t[1] - t[0], t[0]))

    shapes: list[dict] = []
    annotations: list[dict] = []
    line_style = {"color": "rgba(0,0,0,0.55)", "width": 1}
    tick_height = step * 0.30

    for level, (i_a, i_b, stars) in enumerate(sig):
        h = base + level * step
        x_a, x_b = xs[i_a], xs[i_b]
        # Left tick, top connector, right tick — three line shapes
        # so we can use category names on the x-axis (paths require
        # numeric coords).
        shapes.append({
            "type": "line", "xref": "x", "yref": "y",
            "x0": x_a, "x1": x_a, "y0": h - tick_height, "y1": h,
            "line": line_style,
        })
        shapes.append({
            "type": "line", "xref": "x", "yref": "y",
            "x0": x_a, "x1": x_b, "y0": h, "y1": h,
            "line": line_style,
        })
        shapes.append({
            "type": "line", "xref": "x", "yref": "y",
            "x0": x_b, "x1": x_b, "y0": h - tick_height, "y1": h,
            "line": line_style,
        })
        # Stars centered on the bracket midpoint. Plotly's category
        # axis accepts fractional numeric x for interpolation between
        # categories — that's how we land in the middle.
        annotations.append({
            "x": (i_a + i_b) / 2.0, "y": h + step * 0.18,
            "xref": "x", "yref": "y",
            "text": stars,
            "showarrow": False,
            "font": {"family": "Geist Mono, monospace", "size": 13,
                     "color": "rgba(0,0,0,0.75)"},
            "xanchor": "center",
            "yanchor": "bottom",
        })

    return shapes, annotations

ACCENT = "#D4B36A"
ACCENT_SOFT = "rgba(212, 179, 106, 0.55)"
INFO = "#8FA8C4"
GOOD = "#8FAA88"
WARN = "#D89B7E"

# Color cycle for grouped plots — gold first, then info/good/warn shades.
PALETTE = [ACCENT, INFO, GOOD, WARN, "#B4A0D2", "#8FAA88", "#D89B7E"]


def _label_for(value, labels_for_var: dict | None) -> str:
    """Look up a Stata-style value label, falling back to str(value).

    `labels_for_var` is the {code: label} dict produced by pyreadstat for
    a single variable (e.g. {1: "Baseline", 2: "5-day"}). Keys can arrive
    as ints, floats, or strings depending on the original .dta, so we
    probe a few coercions before giving up.
    """
    if not labels_for_var:
        return str(value)
    for key in (value, str(value)):
        if key in labels_for_var:
            return str(labels_for_var[key])
    # Numeric-typed key dict, string value — try the round-trip.
    try:
        as_int = int(value)
        if as_int in labels_for_var:
            return str(labels_for_var[as_int])
    except (TypeError, ValueError):
        pass
    return str(value)


def _groupby_preserve_order(df: pd.DataFrame, group: str):
    """Yield (level, sub) pairs in first-encounter order.

    Default pandas groupby sorts groups alphabetically, which breaks
    intuitive ordering (Baseline < 5-day < 10-day comes out 10-day,
    5-day, Baseline). Callers who pre-sorted their data should see
    their order respected.
    """
    return df.groupby(group, dropna=True, sort=False)


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

def histogram(
    df: pd.DataFrame,
    var: str,
    *,
    bins: int = 20,
    group: str | None = None,
    value_labels: dict[str, dict] | None = None,
) -> dict:
    if var not in df.columns:
        raise KeyError(f"variable {var!r} not in dataset")
    series = pd.to_numeric(df[var], errors="coerce").dropna()

    if group and group in df.columns:
        labels = (value_labels or {}).get(group)
        data = []
        for i, (lvl, sub) in enumerate(_groupby_preserve_order(df, group)):
            s = pd.to_numeric(sub[var], errors="coerce").dropna()
            data.append({
                "type": "histogram",
                "x": s.tolist(),
                "nbinsx": bins,
                "name": _label_for(lvl, labels),
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

def scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    *,
    group: str | None = None,
    value_labels: dict[str, dict] | None = None,
) -> dict:
    for v in (x, y):
        if v not in df.columns:
            raise KeyError(f"variable {v!r} not in dataset")

    if group and group in df.columns:
        labels = (value_labels or {}).get(group)
        sub_df = df.dropna(subset=[x, y])
        traces = []
        for i, (lvl, sub) in enumerate(_groupby_preserve_order(sub_df, group)):
            traces.append({
                "type": "scatter",
                "mode": "markers",
                "x": pd.to_numeric(sub[x], errors="coerce").tolist(),
                "y": pd.to_numeric(sub[y], errors="coerce").tolist(),
                "name": _label_for(lvl, labels),
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

def box(
    df: pd.DataFrame,
    var: str,
    *,
    group: str | None = None,
    value_labels: dict[str, dict] | None = None,
) -> dict:
    if var not in df.columns:
        raise KeyError(f"variable {var!r} not in dataset")

    if group and group in df.columns:
        labels = (value_labels or {}).get(group)
        traces = []
        for i, (lvl, sub) in enumerate(_groupby_preserve_order(df, group)):
            s = pd.to_numeric(sub[var], errors="coerce").dropna()
            traces.append({
                "type": "box",
                "y": s.tolist(),
                "name": _label_for(lvl, labels),
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

def bar_with_ci(
    df: pd.DataFrame,
    var: str,
    *,
    group: str | None = None,
    subgroup: str | None = None,
    err: ErrSource = "ci95",
    ci: float = 0.95,
    pairwise: dict | None = None,
    value_labels: dict[str, dict] | None = None,
) -> dict:
    """Bar chart of mean(`var`) per group, with optional sub-grouping.

    `err` picks the error-bar source ("none" / "sd" / "sem" / "ci95");
    `ci` is the confidence level when err == "ci95". When `subgroup` is
    set the chart produces one trace per subgroup level with
    `barmode='group'` so bars cluster by `group`. Both axes preserve
    data-encounter order via Plotly's `categoryorder: array`. This is
    the canonical "8 milks × 3 timepoints" figure.

    `pairwise` is an optional posthoc_block (the dict shape produced by
    oneway's _pairwise). When provided, significance brackets are
    overlaid above the bars for any pair with `p_adj < 0.05`. Grouped
    bars (subgroup set) skip brackets — the UI disables the toggle
    there with an explanation; we also guard at the engine level.
    """
    if var not in df.columns:
        raise KeyError(f"variable {var!r} not in dataset")
    if subgroup and subgroup not in df.columns:
        raise KeyError(f"subgroup variable {subgroup!r} not in dataset")
    if subgroup and group and group in df.columns:
        # pairwise dropped here on purpose — brackets aren't meaningful
        # over a two-factor clustered layout.
        return _bar_grouped(df, var, group, subgroup, err, ci, value_labels)
    y_title = f"mean {var}{_err_suffix(err)}"
    show_err = err != "none"
    if not group or group not in df.columns:
        s = pd.to_numeric(df[var], errors="coerce").dropna()
        m = float(s.mean()) if len(s) > 0 else 0.0
        half = _half_spread(s, err=err, ci=ci)
        return {
            "data": [{
                "type": "bar",
                "x": [var],
                "y": [m],
                "error_y": {"type": "data", "array": [half], "visible": show_err,
                            "color": INFO, "thickness": 1.5, "width": 8},
                "marker": {"color": ACCENT},
            }],
            "layout": _layout(f"Mean of {var}", "", y_title),
        }

    labels = (value_labels or {}).get(group)
    raw_keys: list[str] = []
    xs: list[str] = []
    ys: list[float] = []
    errs: list[float] = []
    for lvl, sub in _groupby_preserve_order(df, group):
        s = pd.to_numeric(sub[var], errors="coerce").dropna()
        if len(s) < 1:
            continue
        # _pairwise keys comparisons by str(group_value); keep the
        # raw side in parallel with the labelled xs for the bracket
        # lookup to work with value-labelled groups too.
        raw_keys.append(str(lvl))
        xs.append(_label_for(lvl, labels))
        ys.append(float(s.mean()))
        errs.append(_half_spread(s, err=err, ci=ci))

    layout = _layout(f"Mean {var} by {group}", group, y_title)
    # Lock the axis to our explicit ordering — without this Plotly
    # re-sorts categorical axes alphabetically by default.
    layout["xaxis"] = {**layout["xaxis"], "type": "category", "categoryorder": "array",
                       "categoryarray": xs}
    if pairwise:
        shapes, annotations = _emit_brackets(raw_keys, xs, ys, errs, pairwise)
        if shapes:
            layout["shapes"] = shapes
        if annotations:
            layout["annotations"] = annotations
    return {
        "data": [{
            "type": "bar",
            "x": xs,
            "y": ys,
            "error_y": {"type": "data", "array": errs, "visible": show_err,
                        "color": INFO, "thickness": 1.5, "width": 8},
            # One PALETTE color per category — Plotly accepts a color
            # array matching the bars, same cycle the grouped traces use.
            "marker": {"color": [_color_for(i) for i in range(len(xs))]},
        }],
        "layout": layout,
    }


def _bar_grouped(df, var, group, subgroup, err, ci, value_labels):
    """Grouped bar: one trace per subgroup-level. X axis is grouped categories."""
    sub_labels = (value_labels or {}).get(subgroup)
    group_labels = (value_labels or {}).get(group)
    show_err = err != "none"

    sub_levels: list = []
    for lvl in df[subgroup].dropna().unique():
        if lvl not in sub_levels:
            sub_levels.append(lvl)
    group_levels: list = []
    for lvl in df[group].dropna().unique():
        if lvl not in group_levels:
            group_levels.append(lvl)

    traces = []
    for i, sub_lvl in enumerate(sub_levels):
        sub_df = df[df[subgroup] == sub_lvl]
        xs: list[str] = []
        ys: list[float] = []
        errs: list[float] = []
        for grp_lvl in group_levels:
            cell = pd.to_numeric(
                sub_df.loc[sub_df[group] == grp_lvl, var],
                errors="coerce",
            ).dropna()
            if cell.empty:
                xs.append(_label_for(grp_lvl, group_labels))
                ys.append(float("nan"))
                errs.append(0.0)
                continue
            xs.append(_label_for(grp_lvl, group_labels))
            ys.append(float(cell.mean()))
            errs.append(_half_spread(cell, err=err, ci=ci))
        traces.append({
            "type": "bar",
            "name": _label_for(sub_lvl, sub_labels),
            "x": xs,
            "y": ys,
            "error_y": {"type": "data", "array": errs, "visible": show_err,
                        "color": "rgba(0,0,0,0.45)", "thickness": 1.2, "width": 6},
            "marker": {"color": _color_for(i)},
        })

    layout = _layout(
        f"Mean {var} by {group} × {subgroup}",
        group,
        f"mean {var}{_err_suffix(err)}",
    )
    layout["barmode"] = "group"
    layout["xaxis"] = {**layout["xaxis"], "type": "category", "categoryorder": "array",
                       "categoryarray": [_label_for(g, group_labels) for g in group_levels]}
    return {"data": traces, "layout": layout}


# ===================================================================
# line
# ===================================================================

def line(
    df: pd.DataFrame,
    x: str,
    y: str,
    *,
    group: str | None = None,
    err: ErrSource = "none",
    ci: float = 0.95,
    value_labels: dict[str, dict] | None = None,
) -> dict:
    """Line chart of `y` over `x`, optionally one line per group level.

    `err="none"` plots raw (x, y) pairs as today. Switching to "sd" /
    "sem" / "ci95" aggregates: at each unique x-level (per group, if
    grouping), we plot the mean(y) and add a symmetric error bar of
    the chosen spread. The y-axis label gains "± SD" / "± SEM" /
    "± 95% CI" so the figure self-labels.
    """
    for v in (x, y):
        if v not in df.columns:
            raise KeyError(f"variable {v!r} not in dataset")

    show_err = err != "none"
    y_title = f"{y}{_err_suffix(err)}" if show_err else y

    def _raw_trace(sub: pd.DataFrame, color: str, name: str) -> dict:
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

    def _aggregated_trace(sub: pd.DataFrame, color: str, name: str) -> dict:
        sub = sub.dropna(subset=[x, y]).copy()
        sub[x] = pd.to_numeric(sub[x], errors="coerce")
        sub[y] = pd.to_numeric(sub[y], errors="coerce")
        sub = sub.dropna(subset=[x, y])
        # Aggregate at each x-level. groupby(sort=True) is fine here —
        # we want x ordered along the axis, not by encounter order.
        xs: list[float] = []
        ys: list[float] = []
        errs: list[float] = []
        for x_val, cell in sub.groupby(x, sort=True):
            ys_cell = cell[y]
            if len(ys_cell) < 1:
                continue
            xs.append(float(x_val))
            ys.append(float(ys_cell.mean()))
            errs.append(_half_spread(ys_cell, err=err, ci=ci))
        return {
            "type": "scatter",
            "mode": "lines+markers",
            "x": xs,
            "y": ys,
            "name": name,
            "line": {"color": color, "width": 2},
            "marker": {"color": color, "size": 5},
            "error_y": {"type": "data", "array": errs, "visible": True,
                        "color": INFO, "thickness": 1.2, "width": 6},
        }

    trace_fn = _aggregated_trace if show_err else _raw_trace

    if group and group in df.columns:
        labels = (value_labels or {}).get(group)
        sub_df = df.dropna(subset=[x, y])
        traces = []
        for i, (lvl, sub) in enumerate(_groupby_preserve_order(sub_df, group)):
            traces.append(trace_fn(sub, _color_for(i), _label_for(lvl, labels)))
        return {"data": traces, "layout": _layout(f"{y} over {x} by {group}", x, y_title)}

    return {
        "data": [trace_fn(df.dropna(subset=[x, y]), ACCENT, y)],
        "layout": _layout(f"{y} over {x}", x, y_title),
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


# ===================================================================
# counts (v3.3 — categorical-data bar chart)
# ===================================================================

CountsMode = Literal["count", "percent"]
CountsNormalize = Literal["total", "within_group", "within_x"]


def counts(
    df: pd.DataFrame,
    x: str,
    *,
    group: str | None = None,
    mode: CountsMode = "count",
    normalize: CountsNormalize = "total",
    value_labels: dict[str, dict] | None = None,
) -> dict:
    """Frequency bar chart of `x` (and optionally `group`).

    The categorical-data counterpart to `bar_with_ci`. When `mode` is
    "count" the y-axis is raw cell counts; when "percent" each cell is
    divided by the chosen normalization scope and multiplied by 100.

    `normalize` is consulted only when `mode == "percent"`:
      - "total"        each cell / total N of the chart
      - "within_group" each cell / total N of its group level
      - "within_x"     each cell / total N of its x level

    For the ungrouped case all three normalisations collapse to "total"
    (the "within" scopes have no group dimension to slice along), so
    the engine just falls back to that mathematically.

    NaN values in `x` (and `group`, if set) are dropped — same default
    as pandas `value_counts`.
    """
    if x not in df.columns:
        raise KeyError(f"variable {x!r} not in dataset")
    if group is not None and group not in df.columns:
        raise KeyError(f"group variable {group!r} not in dataset")

    x_labels = (value_labels or {}).get(x)
    group_labels = (value_labels or {}).get(group) if group else None

    # Drop NaN rows up front so the cells reflect what's actually
    # plottable. Honour the same dropna behaviour as pandas
    # `value_counts(dropna=True)` does in single-column form.
    cols = [x] + ([group] if group else [])
    sub = df.dropna(subset=cols).copy()

    # Encounter-order preservation: walk the column once to pin the
    # axis order, mirroring how _bar_grouped does it for bar charts.
    x_levels = _unique_preserve_order(sub[x])
    x_axis_labels = [_label_for(lvl, x_labels) for lvl in x_levels]

    if group is None:
        # Single-trace path. All three normalisations collapse to
        # "total" since there's no group dimension to slice along.
        counts_series = sub[x].value_counts(dropna=True)
        ys: list[float] = []
        for lvl in x_levels:
            ys.append(float(counts_series.get(lvl, 0)))
        n_total = float(sum(ys))
        if mode == "percent" and n_total > 0:
            ys = [(v / n_total) * 100.0 for v in ys]

        y_title = "percent" if mode == "percent" else "count"
        title_prefix = "Percent" if mode == "percent" else "Count"
        layout = _layout(f"{title_prefix} of {x}", x, y_title)
        layout["xaxis"] = {
            **layout["xaxis"],
            "type": "category",
            "categoryorder": "array",
            "categoryarray": x_axis_labels,
        }
        return {
            "data": [{
                "type": "bar",
                "x": x_axis_labels,
                "y": ys,
                # Same per-category color cycle as the single-group bar
                # chart — categorical levels are distinct, not one series.
                "marker": {"color": [_color_for(i) for i in range(len(x_axis_labels))]},
            }],
            "layout": layout,
        }

    # Grouped path — one trace per group level (clustered bars).
    group_levels = _unique_preserve_order(sub[group])

    # Compute the raw cell-count grid first. cells[gi][xi] = count.
    grid: list[list[float]] = []
    for grp in group_levels:
        per_group = sub.loc[sub[group] == grp, x].value_counts(dropna=True)
        row: list[float] = []
        for lvl in x_levels:
            row.append(float(per_group.get(lvl, 0)))
        grid.append(row)

    if mode == "percent":
        n_total = sum(sum(row) for row in grid)
        if normalize == "total":
            divisors = [[n_total or 1.0] * len(x_levels) for _ in group_levels]
        elif normalize == "within_group":
            divisors = []
            for row in grid:
                row_total = sum(row) or 1.0
                divisors.append([row_total] * len(x_levels))
        else:  # within_x
            col_totals = [
                sum(grid[gi][xi] for gi in range(len(group_levels))) or 1.0
                for xi in range(len(x_levels))
            ]
            divisors = [[col_totals[xi] for xi in range(len(x_levels))]
                        for _ in group_levels]
        grid = [
            [(grid[gi][xi] / divisors[gi][xi]) * 100.0 for xi in range(len(x_levels))]
            for gi in range(len(group_levels))
        ]

    traces = []
    for gi, grp in enumerate(group_levels):
        traces.append({
            "type": "bar",
            "name": _label_for(grp, group_labels),
            "x": x_axis_labels,
            "y": grid[gi],
            "marker": {"color": _color_for(gi)},
        })

    y_title = "percent" if mode == "percent" else "count"
    title_prefix = "Percent" if mode == "percent" else "Count"
    layout = _layout(f"{title_prefix} of {x} by {group}", x, y_title)
    layout["barmode"] = "group"
    layout["xaxis"] = {
        **layout["xaxis"],
        "type": "category",
        "categoryorder": "array",
        "categoryarray": x_axis_labels,
    }
    return {"data": traces, "layout": layout}


def _unique_preserve_order(series: pd.Series) -> list:
    """First-encounter unique values, NaN excluded.

    pandas `Series.unique()` preserves encounter order but includes
    NaN; we strip it here for the counts path where dropna has
    already filtered the dataframe but we still want clean keys.
    """
    out: list = []
    seen: set = set()
    for v in series:
        if pd.isna(v):
            continue
        # Hashable check — fall back to a list lookup for unhashable
        # cell values (rare; defensive).
        try:
            if v in seen:
                continue
            seen.add(v)
        except TypeError:
            if v in out:
                continue
        out.append(v)
    return out
