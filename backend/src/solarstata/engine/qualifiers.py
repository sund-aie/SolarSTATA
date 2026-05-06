"""`if expr` and `in range` qualifiers, plus `by varlist:` group iteration.

`if` translates Stata's syntax into pandas `DataFrame.query()`:

    age > 40 & sex == "M"     → df.query("age > 40 and sex == 'M'")
    !smoking | diabetes==1    → df.query("not smoking or diabetes == 1")

`in` accepts Stata-style 1-based ranges:

    in 1/100      rows 1..100 (1-based, inclusive)
    in f/200      first row through row 200
    in 50/l       row 50 through last
    in -10/l      last 10 rows  (Stata interprets negative offsets from end)

`by`/`bysort` runs a callable on each unique combination of the prefix
varlist and returns the concatenated result. Used by the dispatcher in
the do-file engine, not by individual stat functions.
"""

from __future__ import annotations

import re
from typing import Any, Callable

import pandas as pd


# ===================================================================
# IF
# ===================================================================

def apply_if(df: pd.DataFrame, expr: str | None) -> pd.DataFrame:
    if not expr or not expr.strip():
        return df
    pandas_expr = _stata_to_pandas_expr(expr)
    try:
        return df.query(pandas_expr).copy()
    except Exception as e:  # noqa: BLE001 — surface the original expr in the message
        raise ValueError(f"could not parse if expression {expr!r}: {e}")


_OP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Order matters: longer ops first so & does not eat &&.
    (re.compile(r"&&"), " and "),
    (re.compile(r"\|\|"), " or "),
    (re.compile(r"(?<![<>!=])&"), " and "),
    (re.compile(r"(?<![<>!=])\|"), " or "),
]


def _stata_to_pandas_expr(expr: str) -> str:
    out = expr
    for pattern, repl in _OP_PATTERNS:
        out = pattern.sub(repl, out)
    # Replace bare `!ident` with `not ident` (don't touch !=).
    out = re.sub(r"(?<!\w)!(?!=)\s*", " not ", out)
    # Normalize double quotes to single quotes for pandas.
    out = out.replace('"', "'")
    return out.strip()


# ===================================================================
# IN
# ===================================================================

def apply_in(df: pd.DataFrame, range_expr: str | None) -> pd.DataFrame:
    if not range_expr or not range_expr.strip():
        return df
    n = len(df)
    if n == 0:
        return df

    expr = range_expr.strip().lower()
    if "/" not in expr:
        # Single row: `in 5`
        idx = _resolve_in_index(expr, n)
        return df.iloc[[idx - 1]].copy()

    a_str, b_str = expr.split("/", 1)
    a = _resolve_in_index(a_str.strip(), n)
    b = _resolve_in_index(b_str.strip(), n)
    if a < 1 or b < 1 or a > n or b > n:
        raise ValueError(f"in range {range_expr!r} out of bounds for {n} obs")
    if a > b:
        return df.iloc[0:0].copy()
    return df.iloc[a - 1 : b].copy()


def _resolve_in_index(token: str, n: int) -> int:
    """Convert Stata index tokens (`f`, `l`, `1`, `-3`) to a 1-based row number."""
    if token in ("f", "first"):
        return 1
    if token in ("l", "last"):
        return n
    if token.startswith("-"):
        offset = int(token[1:])
        return max(1, n - offset + 1)
    return int(token)


# ===================================================================
# BY / BYSORT
# ===================================================================

def for_groups(
    df: pd.DataFrame,
    by_varlist: list[str],
    fn: Callable[[pd.DataFrame, dict[str, Any]], Any],
    *,
    sort: bool = False,
) -> list[tuple[dict[str, Any], Any]]:
    """Run `fn` for each (sorted) combination of `by_varlist` values.

    Returns a list of (group_key_dict, fn_result) pairs in group order.
    The caller decides how to merge — typically by stacking result rows
    or rendering one Stata block per group.
    """
    if not by_varlist:
        return [({}, fn(df, {}))]

    work = df.sort_values(list(by_varlist)).copy() if sort else df.copy()
    grouped = work.groupby(list(by_varlist), sort=False, dropna=False)
    out: list[tuple[dict[str, Any], Any]] = []
    for key, sub in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        keymap = dict(zip(by_varlist, key))
        out.append((keymap, fn(sub, keymap)))
    return out
