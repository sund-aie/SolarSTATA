"""Shapiro-Wilk normality and Levene's variance-homogeneity tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp

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


def test_levene_includes_singleton_groups() -> None:
    """A 1-obs group stays in the test: W/p must match scipy over ALL groups.

    Regression: the engine used to drop n<2 groups silently, so the reported
    W was for a different grouping than the user requested (clinic_patients
    education_level has a singleton 'unknown' level that triggered this).
    """
    rng = np.random.default_rng(11)
    df = pd.DataFrame({
        "y": np.concatenate([rng.normal(0, 1, 40), rng.normal(0, 1, 40), [2.5]]),
        "g": ["a"] * 40 + ["b"] * 40 + ["c"],
    })
    res = levene(df, "y", "g")
    s = res.structured
    samples = [df.loc[df["g"] == g, "y"].to_numpy() for g in ("a", "b", "c")]
    W, p = sp.levene(*samples, center="median")
    assert s["W"] == pytest.approx(float(W), abs=1e-6)
    assert s["p"] == pytest.approx(float(p), abs=1e-6)
    assert [r["group"] for r in s["groups"]] == ["a", "b", "c"]
    assert s["df1"] == 2
    singleton = next(r for r in s["groups"] if r["group"] == "c")
    assert singleton["n"] == 1
    assert singleton["sd"] is None  # undefined with one obs, never fabricated


def test_levene_skips_groups_with_no_observations() -> None:
    """Groups that are empty after dropping missing depvar values cannot
    participate; they are excluded rather than crashing scipy."""
    rng = np.random.default_rng(13)
    df = pd.DataFrame({
        "y": np.concatenate([rng.normal(0, 1, 30), rng.normal(0, 1, 30), [np.nan, np.nan]]),
        "g": ["a"] * 30 + ["b"] * 30 + ["c", "c"],
    })
    res = levene(df, "y", "g")
    s = res.structured
    assert [r["group"] for r in s["groups"]] == ["a", "b"]
    assert s["df1"] == 1
