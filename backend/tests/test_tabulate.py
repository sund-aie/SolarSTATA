"""Unit tests for tabulate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine import tabulate


@pytest.fixture
def df_categorical() -> pd.DataFrame:
    return pd.DataFrame({
        "group":   ["a", "a", "b", "b", "b", "c", "c", "c", "c"],
        "outcome": [0,   1,   0,   1,   1,   0,   0,   1,   1],
    })


def test_tabulate_oneway_counts_correct(df_categorical: pd.DataFrame) -> None:
    res = tabulate(df_categorical, "group")
    rows = res.structured["rows"]
    counts = {r["value"]: r["freq"] for r in rows}
    assert counts == {"a": 2, "b": 3, "c": 4}
    assert res.structured["n"] == 9
    assert res.structured["n_categories"] == 3


def test_tabulate_oneway_percent_and_cumulative_sum_to_100(df_categorical: pd.DataFrame) -> None:
    rows = tabulate(df_categorical, "group").structured["rows"]
    # Sum of per-cell rounded percents may lose ~0.01 to display rounding (Stata does the same:
    # 2/9 + 3/9 + 4/9 = 22.22 + 33.33 + 44.44 = 99.99). The cumulative total — which we
    # carry at full precision — must hit 100 exactly.
    assert pytest.approx(rows[-1]["cum"], abs=0.01) == 100.0
    total_pct = sum(r["percent"] for r in rows)
    assert pytest.approx(total_pct, abs=0.05) == 100.0


def test_tabulate_twoway_returns_matrix(df_categorical: pd.DataFrame) -> None:
    res = tabulate(df_categorical, "group", "outcome")
    p = res.structured
    assert p["var1"] == "group"
    assert p["var2"] == "outcome"
    assert sorted(p["row_categories"]) == ["a", "b", "c"]
    assert len(p["matrix"]) == len(p["row_categories"])
    assert all(len(row) == len(p["col_categories"]) for row in p["matrix"])
    assert sum(p["row_totals"]) == p["n"] == 9
    assert sum(p["col_totals"]) == p["n"]


def test_tabulate_drops_missing_in_oneway() -> None:
    df = pd.DataFrame({"x": ["a", "b", None, "a", None]})
    res = tabulate(df, "x")
    assert res.structured["n"] == 3


def test_tabulate_unknown_variable_raises() -> None:
    df = pd.DataFrame({"x": [1, 2]})
    with pytest.raises(KeyError):
        tabulate(df, "nope")


def test_tabulate_command_string(df_categorical: pd.DataFrame) -> None:
    assert tabulate(df_categorical, "group").command == "tabulate group"
    assert tabulate(df_categorical, "group", "outcome").command == "tabulate group outcome"


def test_tabulate_oneway_text_has_total_line(df_categorical: pd.DataFrame) -> None:
    text = tabulate(df_categorical, "group").text
    assert "Total" in text
    assert "Freq." in text


def test_tabulate_handles_numeric_codes() -> None:
    df = pd.DataFrame({"x": [0, 1, 1, 0, 1]})
    res = tabulate(df, "x")
    counts = {r["value"]: r["freq"] for r in res.structured["rows"]}
    assert counts == {0: 2, 1: 3}
    # Numeric codes returned as native Python ints (not numpy)
    assert all(isinstance(k, int) for k in counts.keys())


def test_tabulate_empty_frame() -> None:
    df = pd.DataFrame({"x": pd.Series([], dtype=object)})
    res = tabulate(df, "x")
    assert res.structured["n"] == 0
    assert res.structured["rows"] == []
