"""Significance brackets on bar charts (v3.2 — 2b).

2b RENDERS the posthoc_block produced by oneway. It does NOT
compute any new statistics. These tests pin down four properties:

1. Bracket count == count of pairs with p_adj < 0.05.
2. Star tier follows the publication convention strictly:
   *** if p < .001, ** if p < .01, * if p < .05.
   Boundary values (.001, .01, .05) fall OUT of their respective
   tiers — strict inequality.
3. Brackets stack by tightness: adjacent pairs lowest, wider
   spans higher, so they don't visually collide.
4. Grouped bars (subgroup set) ignore pairwise silently — even
   if the caller passes a payload — because the UI is supposed
   to disable the toggle there with an explanation. The engine
   is the second-line defence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine.graphs import bar_with_ci


@pytest.fixture
def four_groups_df() -> pd.DataFrame:
    """A, B, C, D each with 10 observations, distinct means."""
    rng = np.random.default_rng(seed=11)
    rows = []
    for label, mean in [("A", 10.0), ("B", 12.0), ("C", 14.0), ("D", 16.0)]:
        for _ in range(10):
            rows.append({"y": rng.normal(mean, 1.0), "g": label})
    return pd.DataFrame(rows)


def _pairwise_with(p_adjs: dict[tuple[str, str], float]) -> dict:
    """Build a posthoc_block stub. Only `comparisons` is consulted by
    the bracket renderer; other fields filled for shape parity with
    the real engine output.
    """
    comparisons = [
        {"a": a, "b": b, "mean_diff": 0.0, "se": 0.0, "t": 0.0, "p_raw": p, "p_adj": p}
        for (a, b), p in p_adjs.items()
    ]
    return {
        "method": "bonferroni",
        "n_pairs": len(comparisons),
        "comparisons": comparisons,
        "matrix": {},
    }


def _annotations(fig: dict) -> list[dict]:
    return fig["layout"].get("annotations", [])


def _shapes(fig: dict) -> list[dict]:
    return fig["layout"].get("shapes", [])


# ---------------------------------------------------------------------------
# Bracket count + star tier
# ---------------------------------------------------------------------------

def test_brackets_only_for_significant_pairs(four_groups_df: pd.DataFrame) -> None:
    pairwise = _pairwise_with({
        ("A", "B"): 0.0001,    # ***
        ("A", "C"): 0.02,      # *
        ("A", "D"): 0.4,       # no bracket
        ("B", "C"): 0.8,       # no bracket
        ("B", "D"): 0.9,       # no bracket
        ("C", "D"): 0.6,       # no bracket
    })
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise=pairwise)
    # 2 brackets × 3 line shapes each = 6 shapes; 2 annotations
    assert len(_shapes(fig)) == 6
    assert len(_annotations(fig)) == 2
    stars = sorted(a["text"] for a in _annotations(fig))
    assert stars == ["*", "***"]


def test_star_tiers_at_each_threshold(four_groups_df: pd.DataFrame) -> None:
    pairwise = _pairwise_with({
        ("A", "B"): 0.0009,    # < .001 → ***
        ("A", "C"): 0.009,     # < .01  → **
        ("A", "D"): 0.049,     # < .05  → *
    })
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise=pairwise)
    stars = sorted(a["text"] for a in _annotations(fig))
    assert stars == ["*", "**", "***"]


def test_boundary_values_are_strict(four_groups_df: pd.DataFrame) -> None:
    """p_adj == .001, .01, .05 must fall OUT of their respective
    tiers — strict less-than, matches publication norm."""
    pairwise = _pairwise_with({
        ("A", "B"): 0.001,     # not ***
        ("A", "C"): 0.01,      # not **
        ("A", "D"): 0.05,      # not *
    })
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise=pairwise)
    stars = sorted(a["text"] for a in _annotations(fig))
    assert stars == ["*", "**"]  # 0.001 → **, 0.01 → *, 0.05 → none


def test_no_brackets_when_no_pair_is_significant(four_groups_df: pd.DataFrame) -> None:
    pairwise = _pairwise_with({
        ("A", "B"): 0.1, ("A", "C"): 0.2, ("A", "D"): 0.5,
        ("B", "C"): 0.6, ("B", "D"): 0.7, ("C", "D"): 0.8,
    })
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise=pairwise)
    assert _shapes(fig) == []
    assert _annotations(fig) == []


def test_no_brackets_when_pairwise_is_none(four_groups_df: pd.DataFrame) -> None:
    """The figure shape is untouched when no pairwise payload is sent."""
    fig = bar_with_ci(four_groups_df, "y", group="g")
    # No shapes/annotations key added — Plotly defaults apply.
    assert "shapes" not in fig["layout"]
    assert "annotations" not in fig["layout"]


# ---------------------------------------------------------------------------
# Stacking
# ---------------------------------------------------------------------------

def test_brackets_stack_by_span(four_groups_df: pd.DataFrame) -> None:
    """Tighter spans render lower; wider spans stack above. Three
    significant pairs of different widths produce strictly
    increasing bracket heights from tightest to widest."""
    pairwise = _pairwise_with({
        ("A", "B"): 0.001,    # adjacent → tightest
        ("A", "C"): 0.001,    # 1-step gap
        ("A", "D"): 0.001,    # widest
    })
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise=pairwise)
    # 3 brackets × 3 line shapes = 9 shapes; group them by the y0
    # of the top line (every 3rd shape is the top connector).
    shapes = _shapes(fig)
    assert len(shapes) == 9
    top_ys = [shapes[1]["y0"], shapes[4]["y0"], shapes[7]["y0"]]
    assert top_ys[0] < top_ys[1] < top_ys[2]


# ---------------------------------------------------------------------------
# Grouped bars
# ---------------------------------------------------------------------------

def test_grouped_bars_ignore_pairwise_silently(four_groups_df: pd.DataFrame) -> None:
    """When subgroup is set, brackets are skipped even if the
    caller passes a pairwise payload. The UI is supposed to
    disable the toggle there; this is the engine-side guard."""
    df = four_groups_df.copy()
    df["sub"] = (df.index % 2).map({0: "P", 1: "Q"})
    pairwise = _pairwise_with({("A", "B"): 0.0001})
    fig = bar_with_ci(df, "y", group="g", subgroup="sub", pairwise=pairwise)
    assert "shapes" not in fig["layout"]
    assert "annotations" not in fig["layout"]


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_pairwise_with_unknown_group_skipped(four_groups_df: pd.DataFrame) -> None:
    """Pairs referencing a group not in the chart are silently ignored."""
    pairwise = _pairwise_with({
        ("A", "B"): 0.001,         # both in chart → bracketed
        ("A", "Z"): 0.001,         # Z absent     → ignored
    })
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise=pairwise)
    assert len(_annotations(fig)) == 1


def test_malformed_pairwise_is_a_no_op(four_groups_df: pd.DataFrame) -> None:
    """A pairwise dict missing 'comparisons' must not crash the
    figure — defensive, since the payload arrives over the wire."""
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise={"method": "bogus"})
    assert "shapes" not in fig["layout"]
    assert "annotations" not in fig["layout"]
