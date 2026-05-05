"""Histogram / sparkline bin computation.

A single helper that produces a list of bin counts for a pandas Series,
used by both the variable-card sparkline (n=12) and the inspect-panel
histogram (n=15+). Behaviour depends on the column type:

  - numeric, many uniques  : equal-width bins via numpy.histogram
  - numeric, few uniques   : one bar per unique value (sorted)
  - binary / categorical   : one bar per category (top-n by count)
  - id-like / string       : flat (counts are uninformative)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BinResult:
    bins: list[int]
    edges: list[float] | None         # bin edges for numeric histograms; None otherwise
    labels: list[str] | None          # category labels for categorical/binary; None otherwise
    kind: str                         # 'numeric' | 'categorical' | 'binary' | 'flat'


def compute_bins(series: pd.Series, n_bins: int = 12) -> BinResult:
    s = series.dropna()
    if s.empty:
        return BinResult(bins=[0] * n_bins, edges=None, labels=None, kind="flat")

    if pd.api.types.is_bool_dtype(s):
        counts = s.astype(int).value_counts().reindex([0, 1], fill_value=0)
        return BinResult(
            bins=counts.tolist(),
            edges=None,
            labels=["0", "1"],
            kind="binary",
        )

    if pd.api.types.is_numeric_dtype(s):
        n_unique = s.nunique()
        # Treat as binary when only two unique values (typical 0/1 columns)
        if n_unique == 2:
            counts = s.value_counts().sort_index()
            return BinResult(
                bins=counts.tolist(),
                edges=None,
                labels=[str(v) for v in counts.index.tolist()],
                kind="binary",
            )
        if n_unique <= n_bins:
            # one bar per distinct value
            counts = s.value_counts().sort_index()
            padded = counts.tolist() + [0] * (n_bins - len(counts))
            return BinResult(
                bins=padded,
                edges=None,
                labels=[str(v) for v in counts.index.tolist()],
                kind="categorical",
            )
        try:
            arr, edges = np.histogram(s, bins=n_bins)
        except ValueError:
            return BinResult(bins=[0] * n_bins, edges=None, labels=None, kind="flat")
        return BinResult(
            bins=arr.astype(int).tolist(),
            edges=[float(e) for e in edges.tolist()],
            labels=None,
            kind="numeric",
        )

    # Object / string-ish: treat as categorical
    counts = s.value_counts().head(n_bins)
    bins = counts.tolist()
    bins += [0] * (n_bins - len(bins))
    return BinResult(
        bins=bins,
        edges=None,
        labels=[str(v) for v in counts.index.tolist()],
        kind="categorical",
    )
