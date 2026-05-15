"""tabstat — by-group descriptives matrix."""

from __future__ import annotations

import pandas as pd
import pytest

from solarstata.engine import tabstat


@pytest.fixture
def tiny() -> pd.DataFrame:
    return pd.DataFrame({
        "y":     [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
        "z":     [0.5, 0.5, 0.5, 2.0, 2.0, 2.0],
        "group": ["a", "a", "a", "b", "b", "b"],
    })


def test_tabstat_no_by(tiny: pd.DataFrame) -> None:
    res = tabstat(tiny, ["y", "z"])
    s = res.structured
    assert s["kind"] == "tabstat"
    assert s["by"] is None if "by" in s else True
    assert s["groups"] is None
    assert s["stats"] == ["n", "mean", "sd", "min", "median", "max"]
    assert s["matrix"]["y"]["n"] == 6
    assert s["matrix"]["y"]["mean"] == pytest.approx(11.0)
    assert s["matrix"]["z"]["sd"] is not None and s["matrix"]["z"]["sd"] > 0


def test_tabstat_with_by(tiny: pd.DataFrame) -> None:
    res = tabstat(tiny, ["y"], by="group")
    s = res.structured
    assert s["by"] == "group"
    assert "Total" in s["groups"]
    assert "a" in s["groups"] and "b" in s["groups"]
    assert s["matrix"]["a"]["y"]["mean"] == pytest.approx(2.0)
    assert s["matrix"]["b"]["y"]["mean"] == pytest.approx(20.0)


def test_tabstat_custom_stats(tiny: pd.DataFrame) -> None:
    res = tabstat(tiny, ["y"], stats=["n", "mean", "median"])
    assert res.structured["stats"] == ["n", "mean", "median"]
    assert res.structured["matrix"]["y"]["median"] == pytest.approx(6.5)


def test_tabstat_command_round_trip(tiny: pd.DataFrame) -> None:
    assert tabstat(tiny, ["y"]).command.startswith("tabstat y,")
    assert "by(group)" in tabstat(tiny, ["y"], by="group").command


def test_tabstat_text_renders(tiny: pd.DataFrame) -> None:
    text = tabstat(tiny, ["y", "z"], by="group").text
    assert "y" in text
    assert "z" in text
    assert "a" in text
    assert "b" in text
    assert "Total" in text


def test_tabstat_unknown_variable(tiny: pd.DataFrame) -> None:
    with pytest.raises(KeyError):
        tabstat(tiny, ["missing"])


def test_tabstat_unknown_stat(tiny: pd.DataFrame) -> None:
    with pytest.raises(ValueError):
        tabstat(tiny, ["y"], stats=["mean", "zzzbogus"])
