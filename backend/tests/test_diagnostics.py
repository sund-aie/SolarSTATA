"""Shapiro-Wilk normality and Levene's variance-homogeneity tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine import levene, shapiro


@pytest.fixture
def normal_data() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    return pd.DataFrame({
        "y": rng.normal(0, 1, 200),
        "g": (["a"] * 100 + ["b"] * 100),
    })


@pytest.fixture
def skewed_data() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    return pd.DataFrame({
        "y": rng.exponential(1, 200),
        "g": (["a"] * 100 + ["b"] * 100),
    })


def test_shapiro_overall_normal_passes(normal_data: pd.DataFrame) -> None:
    res = shapiro(normal_data, "y")
    row = res.structured["rows"][0]
    assert row["group"] is None
    assert row["n"] == 200
    assert row["W"] is not None
    # Mild noise: SW p should be well above 0.01 for clean normal draws.
    assert row["p"] is not None and row["p"] > 0.01


def test_shapiro_detects_skew(skewed_data: pd.DataFrame) -> None:
    res = shapiro(skewed_data, "y")
    row = res.structured["rows"][0]
    assert row["p"] is not None and row["p"] < 0.01


def test_shapiro_by_group(normal_data: pd.DataFrame) -> None:
    res = shapiro(normal_data, "y", by="g")
    groups = {r["group"] for r in res.structured["rows"]}
    assert groups == {"a", "b"}


def test_shapiro_command(normal_data: pd.DataFrame) -> None:
    assert shapiro(normal_data, "y").command == "swilk y"
    assert shapiro(normal_data, "y", by="g").command == "swilk y, by(g)"


def test_levene_equal_variance(normal_data: pd.DataFrame) -> None:
    res = levene(normal_data, "y", "g")
    s = res.structured
    assert s["center"] == "median"
    assert s["p"] is not None and s["p"] > 0.01


def test_levene_unequal_variance() -> None:
    rng = np.random.default_rng(19)
    df = pd.DataFrame({
        "y": np.concatenate([rng.normal(0, 0.5, 80), rng.normal(0, 3.0, 80)]),
        "g": (["a"] * 80 + ["b"] * 80),
    })
    res = levene(df, "y", "g")
    assert res.structured["p"] is not None and res.structured["p"] < 0.001


def test_levene_command_default_center() -> None:
    df = pd.DataFrame({"y": [1.0, 2, 3, 4, 5, 6], "g": ["a", "a", "a", "b", "b", "b"]})
    assert levene(df, "y", "g").command == "robvar y, by(g)"
    assert levene(df, "y", "g", center="mean").command == "robvar y, by(g) center(mean)"
