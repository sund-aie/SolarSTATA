"""Normality + homogeneity-of-variance diagnostics.

Wraps scipy.stats.shapiro and scipy.stats.levene with friendlier
return shapes for the Guided result cards. Stata equivalents:
    swilk var [, by(group)]
    robvar var, by(group) [center(median|mean)]
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats as sp

from .results import Result


def _safe(v) -> float | None:
    if v is None:
        return None
    f = float(v)
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 6)


# =====================================================================
# Shapiro-Wilk
# =====================================================================

def shapiro(df: pd.DataFrame, var: str, *, by: str | None = None) -> Result:
    """Test normality of `var` overall, or per level of `by`."""
    if var not in df.columns:
        raise KeyError(f"variable {var!r} not in dataset")
    if by is not None and by not in df.columns:
        raise KeyError(f"variable {by!r} not in dataset")

    if by is None:
        s = pd.to_numeric(df[var], errors="coerce").dropna()
        rows = [_one_shapiro(s, group_label=None)]
    else:
        rows = []
        groups = list(df[by].dropna().unique())
        try:
            groups.sort()
        except TypeError:
            groups.sort(key=str)
        for g in groups:
            sub = pd.to_numeric(df.loc[df[by] == g, var], errors="coerce").dropna()
            rows.append(_one_shapiro(sub, group_label=str(g)))

    text = _render_shapiro(var, by, rows)
    command = f"swilk {var}" + (f", by({by})" if by else "")
    return Result(
        command=command,
        structured={"kind": "shapiro", "variable": var, "by": by, "rows": rows},
        text=text,
    )


def _one_shapiro(s: pd.Series, *, group_label: str | None) -> dict:
    n = int(len(s))
    if n < 3:
        return {"group": group_label, "n": n, "W": None, "p": None,
                "note": "need at least 3 non-missing observations"}
    if n > 5000:
        # Shapiro-Wilk's distribution is unstable above ~5000; sample.
        rng = np.random.default_rng(7)
        sample = s.sample(n=5000, random_state=int(rng.integers(0, 2**31 - 1))).to_numpy()
        W, p = sp.shapiro(sample)
        note = f"sampled to n=5000 (population n={n})"
    else:
        W, p = sp.shapiro(s.to_numpy())
        note = None
    return {"group": group_label, "n": n, "W": _safe(W), "p": _safe(p), "note": note}


def _render_shapiro(var: str, by: str | None, rows: list[dict]) -> str:
    lines = ["", f"  Shapiro-Wilk W test for normal data — {var}"]
    if by:
        lines.append(f"  By: {by}")
    lines.append("")
    header = f"  {'group':>14}  {'Obs':>6}  {'W':>10}  {'Prob>W':>10}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for r in rows:
        g = r.get("group") or "(all)"
        lines.append(f"  {g:>14}  {r.get('n', 0):>6d}  "
                     f"{(_fmt(r.get('W'))):>10}  {(_fmt(r.get('p'))):>10}")
        if r.get("note"):
            lines.append(f"  {'':>14}  {r['note']}")
    lines.append("")
    lines.append("  p < 0.05 ⇒ reject normality. Consider non-parametric tests "
                 "(Mann-Whitney, Kruskal-Wallis, Friedman) when normality is violated.")
    return "\n".join(lines)


def _fmt(v) -> str:
    if v is None:
        return "."
    return f"{v:.4f}"


# =====================================================================
# Levene (with robvar-style mean/median center)
# =====================================================================

def levene(
    df: pd.DataFrame,
    depvar: str,
    groupvar: str,
    *,
    center: Literal["median", "mean", "trimmed"] = "median",
) -> Result:
    """Levene's test for equality of variance across groups.

    Stata's `robvar` defaults to center='median', which is the
    robust Brown-Forsythe variant.
    """
    if depvar not in df.columns:
        raise KeyError(f"variable {depvar!r} not in dataset")
    if groupvar not in df.columns:
        raise KeyError(f"variable {groupvar!r} not in dataset")

    samples = []
    group_rows = []
    groups = list(df[groupvar].dropna().unique())
    try:
        groups.sort()
    except TypeError:
        groups.sort(key=str)

    for g in groups:
        sub = pd.to_numeric(df.loc[df[groupvar] == g, depvar], errors="coerce").dropna()
        if len(sub) < 2:
            continue
        samples.append(sub.to_numpy())
        group_rows.append({
            "group": str(g),
            "n": int(len(sub)),
            "mean": _safe(sub.mean()),
            "sd": _safe(sub.std(ddof=1)),
        })

    if len(samples) < 2:
        raise ValueError("Levene's test needs at least two non-empty groups")

    W, p = sp.levene(*samples, center=center)
    text = _render_levene(depvar, groupvar, center, group_rows, _safe(W), _safe(p))
    command = f"robvar {depvar}, by({groupvar})"
    if center != "median":
        command += f" center({center})"
    return Result(
        command=command,
        structured={
            "kind": "levene",
            "depvar": depvar,
            "groupvar": groupvar,
            "center": center,
            "groups": group_rows,
            "W": _safe(W),
            "df1": len(samples) - 1,
            "df2": int(sum(len(s) for s in samples) - len(samples)),
            "p": _safe(p),
        },
        text=text,
    )


def _render_levene(depvar, groupvar, center, group_rows, W, p) -> str:
    lines = ["", f"  Levene's test for equal variances — {depvar} by {groupvar}"]
    lines.append(f"  Center: {center}")
    lines.append("")
    header = f"  {groupvar:>14}  {'Obs':>6}  {'Mean':>10}  {'Std. dev.':>12}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for r in group_rows:
        lines.append(f"  {r['group']:>14}  {r['n']:>6d}  "
                     f"{_fmt(r.get('mean')):>10}  {_fmt(r.get('sd')):>12}")
    lines.append("")
    df1 = len(group_rows) - 1
    df2 = sum(r["n"] for r in group_rows) - len(group_rows)
    lines.append(f"  W0 = {_fmt(W)}  with df = ({df1}, {df2})")
    lines.append(f"  Prob > F = {_fmt(p)}")
    lines.append("")
    lines.append("  p < 0.05 ⇒ variances differ across groups. Consider "
                 "Welch's correction, or a non-parametric alternative.")
    return "\n".join(lines)
