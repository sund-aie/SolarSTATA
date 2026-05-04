"""Unit tests for the summarize engine function."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp

from solarstata.engine import summarize


@pytest.fixture
def df_simple() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "x": rng.normal(10, 2, size=200),
        "y": rng.normal(0, 1, size=200),
        "cat": rng.choice(["a", "b", "c"], size=200),
    })


def test_summarize_defaults_to_numeric_only(df_simple: pd.DataFrame) -> None:
    res = summarize(df_simple)
    names = [r["Variable"] for r in res.structured["variables"]]
    assert "x" in names and "y" in names
    assert "cat" not in names  # categorical excluded


def test_summarize_basic_stats_match_numpy(df_simple: pd.DataFrame) -> None:
    res = summarize(df_simple, ["x"])
    row = res.structured["variables"][0]
    assert row["Obs"] == 200
    assert pytest.approx(row["Mean"], rel=1e-5) == float(df_simple["x"].mean())
    assert pytest.approx(row["SD"], rel=1e-5) == float(df_simple["x"].std(ddof=1))
    assert pytest.approx(row["Min"], rel=1e-5) == float(df_simple["x"].min())
    assert pytest.approx(row["Max"], rel=1e-5) == float(df_simple["x"].max())


def test_summarize_detail_includes_percentiles_and_higher_moments(df_simple: pd.DataFrame) -> None:
    res = summarize(df_simple, ["x"], detail=True)
    row = res.structured["variables"][0]
    expected_skew = float(sp.skew(df_simple["x"], bias=False))
    expected_kurt = float(sp.kurtosis(df_simple["x"], bias=False, fisher=False))
    assert pytest.approx(row["Skewness"], rel=1e-5) == expected_skew
    assert pytest.approx(row["Kurtosis"], rel=1e-5) == expected_kurt
    for q, key in [(1, "p1"), (25, "p25"), (50, "p50"), (75, "p75"), (99, "p99")]:
        assert pytest.approx(row[key], rel=1e-5) == float(np.percentile(df_simple["x"], q))


def test_summarize_handles_missing_values() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, np.nan, 4.0, np.nan]})
    res = summarize(df)
    row = res.structured["variables"][0]
    assert row["Obs"] == 3
    assert pytest.approx(row["Mean"], rel=1e-5) == 7 / 3


def test_summarize_handles_all_missing() -> None:
    df = pd.DataFrame({"x": [np.nan, np.nan, np.nan]})
    res = summarize(df, ["x"])
    row = res.structured["variables"][0]
    assert row["Obs"] == 0
    assert "Mean" not in row  # no stats computed for an empty series


def test_summarize_command_string_round_trip(df_simple: pd.DataFrame) -> None:
    assert summarize(df_simple, ["x"]).command == "summarize x"
    assert summarize(df_simple, ["x", "y"]).command == "summarize x y"
    assert summarize(df_simple, ["x"], detail=True).command == "summarize x, detail"


def test_summarize_text_rendering_has_header_and_rows(df_simple: pd.DataFrame) -> None:
    text = summarize(df_simple, ["x", "y"]).text
    assert "Variable" in text
    assert "Obs" in text
    assert text.count("\n") >= 2  # header + sep + at least one row
