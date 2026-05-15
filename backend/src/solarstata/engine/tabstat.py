"""Stata `tabstat` — by-group descriptives matrix.

This is the single most-requested feature for clinical-paper Table 2.
Rows are variables, columns are stats (or group × stats when `by` is
set). Output is a structured matrix + a Stata-style ASCII table.

The supported stat names mirror Stata's own:
    n / N      — non-missing observations
    mean       — arithmetic mean
    sd         — standard deviation (ddof=1)
    min / max
    median     — 50th percentile
    p25 / p75  — 25th / 75th percentiles
    sum        — sum of values
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from .results import Result


STAT_ALIASES = {
    "n":      "n",
    "N":      "n",
    "count":  "n",
    "mean":   "mean",
    "sd":     "sd",
    "std":    "sd",
    "min":    "min",
    "max":    "max",
    "median": "median",
    "p50":    "median",
    "p25":    "p25",
    "p75":    "p75",
    "sum":    "sum",
}

DEFAULT_STATS = ["n", "mean", "sd", "min", "median", "max"]


def _round(v):
    if v is None:
        return None
    f = float(v)
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 6)


def _compute(series: pd.Series, stat: str):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    if stat == "n":      return int(len(s))
    if stat == "mean":   return _round(s.mean())
    if stat == "sd":     return _round(s.std(ddof=1)) if len(s) > 1 else None
    if stat == "min":    return _round(s.min())
    if stat == "max":    return _round(s.max())
    if stat == "median": return _round(np.percentile(s, 50))
    if stat == "p25":    return _round(np.percentile(s, 25))
    if stat == "p75":    return _round(np.percentile(s, 75))
    if stat == "sum":    return _round(s.sum())
    return None


def tabstat(
    df: pd.DataFrame,
    variables: Sequence[str],
    *,
    by: str | None = None,
    stats: Sequence[str] | None = None,
    missing: bool = False,
) -> Result:
    """Stata `tabstat varlist [, by(group) stats(...) missing]`.

    Output shape
    ------------
      No `by`:
        structured.matrix is a dict {var: {stat: value}}.

      With `by`:
        structured.matrix is a dict {group_value: {var: {stat: value}}}
        with a "Total" key holding the overall row.
    """
    if not variables:
        raise ValueError("tabstat requires at least one variable")
    for v in variables:
        if v not in df.columns:
            raise KeyError(f"variable {v!r} not in dataset")
    if by is not None and by not in df.columns:
        raise KeyError(f"by variable {by!r} not in dataset")

    canonical_stats: list[str] = []
    for s in (stats or DEFAULT_STATS):
        cs = STAT_ALIASES.get(s)
        if cs is None:
            raise ValueError(f"unknown stat: {s!r}")
        if cs not in canonical_stats:
            canonical_stats.append(cs)

    if by is None:
        matrix: dict[str, dict[str, object]] = {}
        for v in variables:
            matrix[v] = {st: _compute(df[v], st) for st in canonical_stats}
        text = _render_no_by(variables, canonical_stats, matrix)
        structured = {
            "kind": "tabstat",
            "variables": list(variables),
            "stats": canonical_stats,
            "groups": None,
            "matrix": matrix,
        }
    else:
        groups: list = list(df[by].dropna().unique())
        try:
            groups.sort()
        except TypeError:
            groups.sort(key=str)
        if missing and df[by].isna().any():
            groups.append(None)

        per_group: dict[str, dict[str, dict[str, object]]] = {}
        for g in groups:
            sub = df[df[by].isna()] if g is None else df[df[by] == g]
            label = "(missing)" if g is None else str(g)
            per_group[label] = {
                v: {st: _compute(sub[v], st) for st in canonical_stats}
                for v in variables
            }
        per_group["Total"] = {
            v: {st: _compute(df[v], st) for st in canonical_stats}
            for v in variables
        }
        text = _render_with_by(variables, canonical_stats, by, per_group)
        structured = {
            "kind": "tabstat",
            "variables": list(variables),
            "stats": canonical_stats,
            "groups": list(per_group.keys()),
            "by": by,
            "matrix": per_group,
        }

    cmd_head = " ".join(["tabstat", *variables])
    options: list[str] = []
    if by:
        options.append(f"by({by})")
    options.append(f"stats({' '.join(canonical_stats)})")
    if missing:
        options.append("missing")
    command = cmd_head + ", " + " ".join(options)

    return Result(command=command, structured=structured, text=text)


# ---------- ASCII renderers ----------

def _fnum(v) -> str:
    if v is None:
        return "."
    if isinstance(v, int):
        return f"{v:d}"
    return f"{v:.4f}"


def _render_no_by(variables, stats, matrix) -> str:
    name_w = max(8, max(len(v) for v in variables))
    col_w = 10
    header = f"{'variable':>{name_w}} | " + "".join(f"{s:>{col_w}}" for s in stats)
    sep = "-" * name_w + "-+-" + "-" * (len(stats) * col_w)
    rows = []
    for v in variables:
        row = f"{v:>{name_w}} | "
        row += "".join(f"{_fnum(matrix[v][s]):>{col_w}}" for s in stats)
        rows.append(row)
    return "\n".join([header, sep, *rows])


def _render_with_by(variables, stats, by, per_group) -> str:
    # Tall format: one block per group (Stata also does this for many stats).
    blocks: list[str] = []
    for group_label, group_block in per_group.items():
        blocks.append(f"\n  {by} = {group_label}")
        blocks.append(_render_no_by(variables, stats, group_block))
    return "\n".join(blocks)
