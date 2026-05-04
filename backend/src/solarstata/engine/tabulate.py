"""One-way and two-way frequency tables — Stata `tabulate`."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .formatters import render_tabulate_oneway, render_tabulate_twoway
from .results import Result


def tabulate(
    df: pd.DataFrame,
    var1: str,
    var2: str | None = None,
) -> Result:
    """Stata `tabulate var1 [var2]`.

    One-way: returns counts, percent, cumulative percent.
    Two-way: returns the contingency table with row/column totals.
    """
    if var1 not in df.columns:
        raise KeyError(f"Variable not found: {var1}")
    if var2 is not None and var2 not in df.columns:
        raise KeyError(f"Variable not found: {var2}")

    if var2 is None:
        return _tabulate_oneway(df, var1)
    return _tabulate_twoway(df, var1, var2)


def _tabulate_oneway(df: pd.DataFrame, var: str) -> Result:
    s = df[var].dropna()
    counts = s.value_counts(sort=False).sort_index()
    total = int(counts.sum())
    if total == 0:
        return Result(
            command=f"tabulate {var}",
            structured={"variable": var, "rows": [], "n": 0},
            text="no observations\n",
            r_update={"r": 0, "N": 0},
        )

    # Keep full precision through cum-sum to avoid 99.99 totals; round once per cell at the end.
    raw_pct = counts.values / total * 100.0
    raw_cum = np.cumsum(raw_pct)

    rows_payload = []
    for value, freq, pct, cum in zip(counts.index, counts.values, raw_pct, raw_cum):
        rows_payload.append({
            "value": _native(value),
            "freq": int(freq),
            "percent": round(float(pct), 2),
            "cum": round(float(cum), 2),
        })

    table = pd.DataFrame({
        var: counts.index.tolist(),
        "Freq.": counts.values.astype(int),
        "Percent": np.round(raw_pct, 2),
        "Cum.": np.round(raw_cum, 2),
    })
    text = render_tabulate_oneway(var, table)

    return Result(
        command=f"tabulate {var}",
        structured={
            "variable": var,
            "n": total,
            "n_categories": int(len(counts)),
            "rows": rows_payload,
        },
        text=text,
        r_update={"r": int(len(counts)), "N": total},
    )


def _tabulate_twoway(df: pd.DataFrame, var1: str, var2: str) -> Result:
    sub = df[[var1, var2]].dropna()
    if sub.empty:
        return Result(
            command=f"tabulate {var1} {var2}",
            structured={"var1": var1, "var2": var2, "rows": [], "n": 0},
            text="no observations\n",
            r_update={"N": 0},
        )
    ct = pd.crosstab(sub[var1], sub[var2])
    total = int(ct.values.sum())

    text = render_tabulate_twoway(var1, var2, ct)

    payload = {
        "var1": var1,
        "var2": var2,
        "n": total,
        "row_categories": [str(x) for x in ct.index.tolist()],
        "col_categories": [str(x) for x in ct.columns.tolist()],
        "matrix": ct.astype(int).values.tolist(),
        "row_totals": ct.sum(axis=1).astype(int).tolist(),
        "col_totals": ct.sum(axis=0).astype(int).tolist(),
    }
    return Result(
        command=f"tabulate {var1} {var2}",
        structured=payload,
        text=text,
        r_update={"N": total},
    )


def _native(value):
    """Convert numpy scalar types to plain Python so JSON serialization works."""
    # Catch numpy generics first (handles int8/16/32/64, float32/64, etc.)
    if isinstance(value, np.generic):
        py = value.item()
        if isinstance(py, float) and (np.isnan(py) or np.isinf(py)):
            return None
        return py
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value
