"""Dataset writers."""

from __future__ import annotations

from pathlib import Path

import pyreadstat

from ..session.models import Frame
from .readers import sniff_format


def write_dataset(frame: Frame, path: str | Path) -> Path:
    """Persist a Frame to disk in the format implied by the filename suffix."""
    path = Path(path)
    fmt = sniff_format(path.name)

    if fmt == "csv":
        frame.df.to_csv(path, index=False)
    elif fmt == "tsv":
        frame.df.to_csv(path, sep="\t", index=False)
    elif fmt == "xlsx":
        frame.df.to_excel(path, index=False)
    elif fmt == "parquet":
        frame.df.to_parquet(path, index=False)
    elif fmt == "dta":
        pyreadstat.write_dta(
            frame.df,
            str(path),
            column_labels=[frame.column_labels.get(c, "") for c in frame.df.columns]
            if frame.column_labels else None,
            variable_value_labels=frame.value_labels or None,
        )
    else:  # pragma: no cover
        raise ValueError(f"Unhandled format: {fmt}")

    return path
