"""Stata-style `compress` — pick the smallest storage type per column.

Stata's storage hierarchy (least → most expensive):

  byte    1 byte    -127 .. 100
  int     2 bytes   -32 767 .. 32 740
  long    4 bytes   -2 147 483 647 .. 2 147 483 620
  float   4 bytes   ~7 significant decimal digits
  double  8 bytes   ~15 significant decimal digits

Integer types are picked based on observed min/max. Float vs double is
picked based on whether round-trip through float32 loses precision
relative to the source values.

We don't actually mutate pandas dtypes here — pandas keeps its own
representation regardless. We only update `Frame.storage_types` so the
.dta writer chooses correctly and the UI can display the Stata type.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..session.models import Frame

BYTE_MIN, BYTE_MAX = -127, 100
INT_MIN, INT_MAX = -32_767, 32_740
LONG_MIN, LONG_MAX = -2_147_483_647, 2_147_483_620


@dataclass
class CompressChange:
    column: str
    before: str | None
    after: str
    bytes_saved: int  # per-row delta


def compress(frame: Frame) -> list[CompressChange]:
    """Recompute storage types for every column. Returns the changes made."""
    changes: list[CompressChange] = []
    for col in frame.df.columns:
        s = frame.df[col]
        before = frame.storage_types.get(col)
        after = _pick_type(s)
        if after != before:
            changes.append(
                CompressChange(
                    column=str(col),
                    before=before,
                    after=after,
                    bytes_saved=_size(before) - _size(after),
                )
            )
            frame.storage_types[col] = after
    return changes


def _pick_type(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return _stringy(series)

    if pd.api.types.is_bool_dtype(series):
        return "byte"

    if pd.api.types.is_integer_dtype(series) or _all_integral(s):
        lo, hi = float(s.min()), float(s.max())
        if BYTE_MIN <= lo and hi <= BYTE_MAX:
            return "byte"
        if INT_MIN <= lo and hi <= INT_MAX:
            return "int"
        if LONG_MIN <= lo and hi <= LONG_MAX:
            return "long"
        # Out of long range: fall through to double to avoid silent precision loss.
        return "double"

    if pd.api.types.is_float_dtype(series):
        return "float" if _fits_float32(s) else "double"

    return _stringy(series)


def _all_integral(s: pd.Series) -> bool:
    """True if every non-NaN value equals its rounded form (so we can store as int)."""
    arr = s.to_numpy()
    if not np.issubdtype(arr.dtype, np.number):
        return False
    return np.all(np.isfinite(arr) & (np.modf(arr)[0] == 0))


def _fits_float32(s: pd.Series) -> bool:
    """True if all values round-trip through float32 without loss.

    Mirrors Stata's rule of thumb: float (single-precision IEEE 754) gives
    ~7 decimal digits, so values requiring more (e.g. large IDs stored as
    decimals) need double.
    """
    arr = s.to_numpy(dtype=np.float64)
    rt = arr.astype(np.float32).astype(np.float64)
    return bool(np.allclose(arr, rt, equal_nan=True, rtol=1e-7, atol=0))


def _stringy(series: pd.Series) -> str:
    """Pick a string storage type based on observed length."""
    s = series.dropna().astype(str)
    if s.empty:
        return "str1"
    longest = int(s.map(len).max())
    if longest <= 2_045:
        return f"str{longest}"
    return "strL"


def _size(t: str | None) -> int:
    if t is None:
        return 8
    if t == "byte":
        return 1
    if t == "int":
        return 2
    if t in ("long", "float"):
        return 4
    if t == "double":
        return 8
    if t.startswith("str"):
        suffix = t[3:]
        try:
            return int(suffix)
        except ValueError:
            return 8
    return 8
