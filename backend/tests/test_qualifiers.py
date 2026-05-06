"""if/in qualifiers + by-group iteration."""

from __future__ import annotations

import pandas as pd
import pytest

from solarstata.engine import apply_if, apply_in, for_groups


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame({
        "id":     [1, 2, 3, 4, 5, 6],
        "age":    [20, 30, 40, 50, 60, 70],
        "sex":    ["M", "F", "F", "M", "F", "M"],
        "smoker": [0, 1, 0, 1, 0, 1],
    })


# IF -----------------------------------------------------------------

def test_if_simple_numeric(df: pd.DataFrame) -> None:
    out = apply_if(df, "age > 40")
    assert list(out["age"]) == [50, 60, 70]


def test_if_string_equality(df: pd.DataFrame) -> None:
    out = apply_if(df, 'sex == "M"')
    assert list(out["id"]) == [1, 4, 6]


def test_if_compound_and(df: pd.DataFrame) -> None:
    out = apply_if(df, 'sex == "F" & smoker == 1')
    assert list(out["id"]) == [2]


def test_if_compound_or(df: pd.DataFrame) -> None:
    out = apply_if(df, "age > 60 | smoker == 0")
    assert sorted(out["id"]) == [1, 3, 5, 6]


def test_if_passes_through_when_blank(df: pd.DataFrame) -> None:
    assert len(apply_if(df, None)) == len(df)
    assert len(apply_if(df, "")) == len(df)


# IN -----------------------------------------------------------------

def test_in_range(df: pd.DataFrame) -> None:
    out = apply_in(df, "1/3")
    assert list(out["id"]) == [1, 2, 3]


def test_in_first_to_n(df: pd.DataFrame) -> None:
    assert list(apply_in(df, "f/2")["id"]) == [1, 2]


def test_in_n_to_last(df: pd.DataFrame) -> None:
    assert list(apply_in(df, "5/l")["id"]) == [5, 6]


def test_in_negative_offset_from_end(df: pd.DataFrame) -> None:
    """`-2/l` should grab the last two rows."""
    assert list(apply_in(df, "-2/l")["id"]) == [5, 6]


# BY -----------------------------------------------------------------

def test_for_groups_partitions(df: pd.DataFrame) -> None:
    results = for_groups(df, ["sex"], lambda sub, key: len(sub))
    pairs = {tuple(k.values()): v for k, v in results}
    assert pairs == {("F",): 3, ("M",): 3}


def test_for_groups_no_keys_runs_once(df: pd.DataFrame) -> None:
    results = for_groups(df, [], lambda sub, key: sub.shape)
    assert len(results) == 1
    assert results[0][1] == df.shape
