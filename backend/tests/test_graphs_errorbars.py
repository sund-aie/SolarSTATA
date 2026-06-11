"""Error-bar source control on bar and line charts (v3.2).

The bar endpoint historically computed only 95% CI; the line endpoint
had no error bars. v3.2 adds an `err` selector (none / sd / sem /
ci95) and labels the y-axis with the chosen indicator.

These tests pin down four things:

1. The math: the half-width emitted into Plotly's error_y matches
   pandas/scipy when computed by hand for each indicator.
2. The y-axis labels self-document — "± SD" / "± SEM" / "± 95% CI"
   appears in the yaxis.title text so a downstream figure consumer
   knows which interval was rendered.
3. err="none" suppresses the error_y line (visible=False) on bar
   and skips the aggregation/error-bar plumbing on line.
4. Backwards-compat: bar's pre-3.2 caller (no err arg) still gets
   the 95% CI bars; line's pre-3.2 caller (no err arg) still gets
   the raw scatter trace it used to get.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp

from solarstata.engine.graphs import ACCENT, _color_for, bar_with_ci, line


@pytest.fixture
def simple_two_group_df() -> pd.DataFrame:
    """Two groups with known dispersion so we can hand-check the math."""
    rng = np.random.default_rng(seed=42)
    rows = []
    for _ in range(40):
        rows.append({"y": rng.normal(10.0, 2.0), "g": "A"})
    for _ in range(40):
        rows.append({"y": rng.normal(12.0, 1.0), "g": "B"})
    return pd.DataFrame(rows)


def _error_array(fig: dict) -> list[float]:
    return fig["data"][0]["error_y"]["array"]


def _error_visible(fig: dict) -> bool:
    return bool(fig["data"][0]["error_y"]["visible"])


def _yaxis_title(fig: dict) -> str:
    title = fig["layout"]["yaxis"]["title"]
    if isinstance(title, dict):
        return str(title.get("text", ""))
    return str(title)


# ---------------------------------------------------------------------------
# bar — math correctness
# ---------------------------------------------------------------------------

def test_bar_sd_matches_sample_std(simple_two_group_df: pd.DataFrame) -> None:
    fig = bar_with_ci(simple_two_group_df, "y", group="g", err="sd")
    errs = _error_array(fig)
    expected = [
        float(simple_two_group_df.loc[simple_two_group_df.g == g, "y"].std(ddof=1))
        for g in ("A", "B")
    ]
    assert errs == pytest.approx(expected, rel=1e-9)


def test_bar_sem_matches_scipy_sem(simple_two_group_df: pd.DataFrame) -> None:
    fig = bar_with_ci(simple_two_group_df, "y", group="g", err="sem")
    errs = _error_array(fig)
    expected = [
        float(sp.sem(simple_two_group_df.loc[simple_two_group_df.g == g, "y"]))
        for g in ("A", "B")
    ]
    assert errs == pytest.approx(expected, rel=1e-9)


def test_bar_ci95_matches_t_interval(simple_two_group_df: pd.DataFrame) -> None:
    fig = bar_with_ci(simple_two_group_df, "y", group="g", err="ci95")
    errs = _error_array(fig)
    expected = []
    for g in ("A", "B"):
        s = simple_two_group_df.loc[simple_two_group_df.g == g, "y"]
        se = float(sp.sem(s))
        expected.append(float(sp.t.ppf(0.975, df=len(s) - 1) * se))
    assert errs == pytest.approx(expected, rel=1e-9)


def test_bar_err_none_hides_error_bars(simple_two_group_df: pd.DataFrame) -> None:
    fig = bar_with_ci(simple_two_group_df, "y", group="g", err="none")
    assert _error_visible(fig) is False
    assert _error_array(fig) == [0.0, 0.0]


def test_bar_indicators_are_strictly_ordered(simple_two_group_df: pd.DataFrame) -> None:
    """For these data SD > 95%CI > SEM by definition (n=40, normal-ish)."""
    sd = _error_array(bar_with_ci(simple_two_group_df, "y", group="g", err="sd"))[0]
    sem = _error_array(bar_with_ci(simple_two_group_df, "y", group="g", err="sem"))[0]
    ci = _error_array(bar_with_ci(simple_two_group_df, "y", group="g", err="ci95"))[0]
    assert sem < ci < sd


# ---------------------------------------------------------------------------
# bar — y-axis labels self-document
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("err,suffix", [
    ("sd",   "± SD"),
    ("sem",  "± SEM"),
    ("ci95", "± 95% CI"),
])
def test_bar_yaxis_title_includes_err_suffix(
    simple_two_group_df: pd.DataFrame, err: str, suffix: str,
) -> None:
    fig = bar_with_ci(simple_two_group_df, "y", group="g", err=err)
    assert suffix in _yaxis_title(fig)


def test_bar_default_preserves_pre_3_2_behaviour(simple_two_group_df: pd.DataFrame) -> None:
    """Calling without err= must produce the same numbers as err='ci95'."""
    legacy = _error_array(bar_with_ci(simple_two_group_df, "y", group="g"))
    explicit = _error_array(bar_with_ci(simple_two_group_df, "y", group="g", err="ci95"))
    assert legacy == pytest.approx(explicit, rel=1e-12)


def test_bar_no_group_single_bar_with_sd(simple_two_group_df: pd.DataFrame) -> None:
    """No-group case still computes SD over the full series."""
    fig = bar_with_ci(simple_two_group_df, "y", err="sd")
    expected = float(simple_two_group_df["y"].std(ddof=1))
    assert _error_array(fig)[0] == pytest.approx(expected, rel=1e-9)
    assert "± SD" in _yaxis_title(fig)


# ---------------------------------------------------------------------------
# line — aggregation + error bars
# ---------------------------------------------------------------------------

@pytest.fixture
def repeated_x_df() -> pd.DataFrame:
    """3 x-levels × 10 reps each, with known variation per x."""
    rng = np.random.default_rng(seed=7)
    rows = []
    for x_val, mu, sigma in [(1, 5.0, 1.0), (2, 7.0, 2.0), (3, 9.0, 0.5)]:
        for _ in range(10):
            rows.append({"x": x_val, "y": rng.normal(mu, sigma)})
    return pd.DataFrame(rows)


def test_line_err_none_keeps_raw_trace(repeated_x_df: pd.DataFrame) -> None:
    """Pre-3.2 callers (no err) get the raw trace — one point per row."""
    fig = line(repeated_x_df, "x", "y")
    trace = fig["data"][0]
    assert len(trace["x"]) == 30  # not aggregated
    assert "error_y" not in trace  # no error bars added


def test_line_err_sd_aggregates_to_three_points(repeated_x_df: pd.DataFrame) -> None:
    fig = line(repeated_x_df, "x", "y", err="sd")
    trace = fig["data"][0]
    assert trace["x"] == [1.0, 2.0, 3.0]
    # Each y is the mean of 10 draws at that x; spread is the sample SD.
    expected_means = []
    expected_sds = []
    for x_val in (1, 2, 3):
        s = repeated_x_df.loc[repeated_x_df.x == x_val, "y"]
        expected_means.append(float(s.mean()))
        expected_sds.append(float(s.std(ddof=1)))
    assert trace["y"] == pytest.approx(expected_means, rel=1e-9)
    assert trace["error_y"]["array"] == pytest.approx(expected_sds, rel=1e-9)


def test_line_err_sem_matches_scipy(repeated_x_df: pd.DataFrame) -> None:
    fig = line(repeated_x_df, "x", "y", err="sem")
    expected = [
        float(sp.sem(repeated_x_df.loc[repeated_x_df.x == x_val, "y"]))
        for x_val in (1, 2, 3)
    ]
    assert fig["data"][0]["error_y"]["array"] == pytest.approx(expected, rel=1e-9)


def test_line_yaxis_title_includes_err_suffix(repeated_x_df: pd.DataFrame) -> None:
    for err, suffix in [("sd", "± SD"), ("sem", "± SEM"), ("ci95", "± 95% CI")]:
        fig = line(repeated_x_df, "x", "y", err=err)
        assert suffix in _yaxis_title(fig), f"missing {suffix} for err={err}"


def test_line_default_still_raw(repeated_x_df: pd.DataFrame) -> None:
    """Calling line() with no err arg must NOT aggregate — back-compat."""
    fig = line(repeated_x_df, "x", "y")
    assert len(fig["data"][0]["x"]) == 30


# ---------------------------------------------------------------------------
# bar — per-category marker colors
# ---------------------------------------------------------------------------

def test_bar_single_group_cycles_marker_color_per_category() -> None:
    """Each bar of a single-group chart gets its own PALETTE color —
    a color array parallel to the bars, not one flat accent."""
    df = pd.DataFrame({"y": [10.0, 11.0, 12.0, 13.0], "g": ["A", "B", "C", "D"]})
    fig = bar_with_ci(df, "y", group="g")
    color = fig["data"][0]["marker"]["color"]
    assert isinstance(color, list)
    assert len(color) == 4  # one entry per group
    assert color == [_color_for(i) for i in range(4)]


def test_bar_no_group_keeps_solid_accent(simple_two_group_df: pd.DataFrame) -> None:
    """The degenerate one-bar chart stays solid ACCENT — nothing to cycle."""
    fig = bar_with_ci(simple_two_group_df, "y")
    assert fig["data"][0]["marker"]["color"] == ACCENT


# ---------------------------------------------------------------------------
# Edge: single-row groups
# ---------------------------------------------------------------------------

def test_bar_single_row_group_has_zero_spread() -> None:
    df = pd.DataFrame({"y": [10.0, 11.0, 12.0], "g": ["A", "B", "C"]})
    for err in ("sd", "sem", "ci95"):
        fig = bar_with_ci(df, "y", group="g", err=err)
        errs = _error_array(fig)
        # n=1 per group → zero spread, no spurious values
        assert all(math.isclose(e, 0.0) for e in errs), f"err={err}: {errs}"
