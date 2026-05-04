"""I/O round-trip tests: csv ↔ dta ↔ parquet preserve the data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from solarstata.io import read_dataset, sniff_format, write_dataset
from solarstata.session.models import Frame


@pytest.fixture
def tiny_frame() -> Frame:
    df = pd.DataFrame({
        "id":   [1, 2, 3, 4],
        "name": ["alpha", "beta", "gamma", "delta"],
        "val":  [1.1, 2.2, 3.3, 4.4],
    })
    return Frame(name="default", df=df, source_filename="tiny.csv")


def test_sniff_format_known_extensions() -> None:
    assert sniff_format("a.csv") == "csv"
    assert sniff_format("a.xlsx") == "xlsx"
    assert sniff_format("a.dta") == "dta"
    assert sniff_format("a.parquet") == "parquet"
    assert sniff_format("a.txt") == "tsv"


def test_sniff_format_unknown_raises() -> None:
    with pytest.raises(ValueError):
        sniff_format("a.docx")


@pytest.mark.parametrize("ext", ["csv", "parquet", "dta"])
def test_round_trip_preserves_values(tiny_frame: Frame, tmp_path: Path, ext: str) -> None:
    out = tmp_path / f"tiny.{ext}"
    write_dataset(tiny_frame, out)
    assert out.exists()

    loaded = read_dataset(out)
    pd.testing.assert_frame_equal(
        loaded.df.reset_index(drop=True),
        tiny_frame.df.reset_index(drop=True),
        check_dtype=False,  # dta promotes ints; csv may lose float exactness
    )


def test_dta_preserves_column_labels(tiny_frame: Frame, tmp_path: Path) -> None:
    tiny_frame.column_labels = {"id": "Identifier", "val": "Value"}
    out = tmp_path / "tiny.dta"
    write_dataset(tiny_frame, out)
    loaded = read_dataset(out)
    assert loaded.column_labels.get("id") == "Identifier"
    assert loaded.column_labels.get("val") == "Value"


def test_clinic_csv_loads_correctly(clinic_csv_path: Path) -> None:
    f = read_dataset(clinic_csv_path)
    assert f.n_obs == 406
    assert f.n_vars == 13
    assert "patient_id" in f.df.columns
    assert f.storage_types["patient_id"] == "long"


def test_clinic_dta_loads_with_labels(clinic_dta_path: Path) -> None:
    f = read_dataset(clinic_dta_path)
    assert f.n_obs == 406
    assert f.n_vars == 13
    # Generator wrote column labels into the .dta — they should round-trip
    assert f.column_labels.get("patient_id", "").startswith("Anonymized")
    assert f.column_labels.get("plaque_index", "").startswith("Silness")
