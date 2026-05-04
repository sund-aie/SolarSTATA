"""Dataset readers.

Returns a Frame with as much metadata preserved as the source format
allows. .dta retains variable labels and value labels via pyreadstat;
csv/xlsx/parquet have no native equivalent so those fields stay empty.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyreadstat

from ..session.models import Frame

SUPPORTED_FORMATS = ("csv", "tsv", "xlsx", "xls", "dta", "parquet")


def sniff_format(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in ("csv",):
        return "csv"
    if suffix in ("tsv", "txt"):
        return "tsv"
    if suffix in ("xlsx", "xls"):
        return "xlsx"
    if suffix in ("dta",):
        return "dta"
    if suffix in ("parquet", "pq"):
        return "parquet"
    raise ValueError(
        f"Unsupported file format: .{suffix}. Supported: {', '.join(SUPPORTED_FORMATS)}"
    )


def read_dataset(path: str | Path, *, name: str = "default") -> Frame:
    """Read a file off disk into a Frame, preserving labels where possible."""
    path = Path(path)
    fmt = sniff_format(path.name)

    column_labels: dict[str, str] = {}
    value_labels: dict[str, dict] = {}

    if fmt == "csv":
        df = pd.read_csv(path)
    elif fmt == "tsv":
        df = pd.read_csv(path, sep="\t")
    elif fmt == "xlsx":
        df = pd.read_excel(path)
    elif fmt == "parquet":
        df = pd.read_parquet(path)
    elif fmt == "dta":
        df, meta = pyreadstat.read_dta(path)
        column_labels = dict(zip(meta.column_names, meta.column_labels)) if meta.column_labels else {}
        column_labels = {k: v for k, v in column_labels.items() if v}
        value_labels = dict(meta.variable_value_labels or {})
    else:  # pragma: no cover — sniff_format already rejected unknowns
        raise ValueError(f"Unhandled format: {fmt}")

    df.columns = [str(c) for c in df.columns]
    df = _dedupe_columns(df)

    storage_types = {col: _stata_storage_type(df[col]) for col in df.columns}

    return Frame(
        name=name,
        df=df,
        column_labels=column_labels,
        value_labels=value_labels,
        storage_types=storage_types,
        source_filename=path.name,
    )


def _dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """If a CSV/Excel has repeated headers, suffix later ones with _1, _2, ..."""
    seen: dict[str, int] = {}
    new_cols = []
    for col in df.columns:
        if col not in seen:
            seen[col] = 0
            new_cols.append(col)
        else:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
    df.columns = new_cols
    return df


def _stata_storage_type(series: pd.Series) -> str:
    """Map a pandas dtype to its Stata storage-type name.

    This is an approximation — Stata's compress would pick the smallest
    integer type that fits, but for Phase 1 we just classify int vs
    float vs string. Phase 1.1 will add a real `compress` routine that
    inspects observed value ranges.
    """
    dtype = series.dtype
    if pd.api.types.is_integer_dtype(dtype):
        return "long"
    if pd.api.types.is_float_dtype(dtype):
        return "double"
    if pd.api.types.is_bool_dtype(dtype):
        return "byte"
    return "str"
