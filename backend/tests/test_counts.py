"""Counts chart engine and route (v3.3 Part B).

Six properties this test file pins down:

1. Count math is exact — single-trace sum equals N, grouped grid
   sums match per-group raw counts from value_counts.
2. Percent math sums to 100 across the chosen normalization scope
   (within float tolerance).
3. The default normalize="total" stays mathematically constant
   regardless of grouping; switching to "within_group" or "within_x"
   changes only the row/column normalisation, never the underlying
   cells.
4. NaN cells are dropped — same default as pandas value_counts.
5. Encounter order is preserved on both axes — categorical labels
   like Baseline / 5-day / 10-day don't get alphabetised.
6. Value labels are honoured — a column labelled {0: "incorrect",
   1: "correct"} shows those strings on the x-axis.

Plus a route-level smoke for the command preview, asserting that the
normalize(...) suffix appears only when the chosen scope diverges
from Stata's default for the current state.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from solarstata.engine.graphs import counts


@pytest.fixture
def quiz_df() -> pd.DataFrame:
    """Pre/post quiz fixture — binary q correctness across two treatment arms."""
    rng = np.random.default_rng(seed=11)
    rows = []
    for _ in range(60):  # A arm: 60 patients
        rows.append({"q1_correct": int(rng.integers(0, 2)), "treatment": "A"})
    for _ in range(40):  # B arm: 40 patients
        rows.append({"q1_correct": int(rng.integers(0, 2)), "treatment": "B"})
    return pd.DataFrame(rows)


def _bar_ys(fig: dict, trace_index: int = 0) -> list[float]:
    return list(fig["data"][trace_index]["y"])


def _xs(fig: dict, trace_index: int = 0) -> list:
    return list(fig["data"][trace_index]["x"])


def _trace_count(fig: dict) -> int:
    return len(fig["data"])


# ---------------------------------------------------------------------------
# Count math
# ---------------------------------------------------------------------------

def test_count_ungrouped_sums_to_n(quiz_df: pd.DataFrame) -> None:
    fig = counts(quiz_df, "q1_correct", mode="count")
    assert sum(_bar_ys(fig)) == pytest.approx(len(quiz_df))


def test_count_grouped_grid_matches_raw_value_counts(quiz_df: pd.DataFrame) -> None:
    fig = counts(quiz_df, "q1_correct", group="treatment", mode="count")
    # Two group traces × two x-levels = 4 cells total
    assert _trace_count(fig) == 2
    expected_a = quiz_df.loc[quiz_df.treatment == "A", "q1_correct"].value_counts()
    expected_b = quiz_df.loc[quiz_df.treatment == "B", "q1_correct"].value_counts()
    # The trace order matches encounter order — A then B in this fixture.
    a_xs = _xs(fig, 0)
    a_ys = _bar_ys(fig, 0)
    for lvl, y in zip(a_xs, a_ys):
        # the chart x-axis displays the value; same key works
        assert y == float(expected_a[int(lvl)])
    b_xs = _xs(fig, 1)
    b_ys = _bar_ys(fig, 1)
    for lvl, y in zip(b_xs, b_ys):
        assert y == float(expected_b[int(lvl)])


# ---------------------------------------------------------------------------
# Percent normalization
# ---------------------------------------------------------------------------

def test_percent_ungrouped_sums_to_100(quiz_df: pd.DataFrame) -> None:
    fig = counts(quiz_df, "q1_correct", mode="percent")
    assert sum(_bar_ys(fig)) == pytest.approx(100.0)


def test_percent_grouped_total_chart_sums_to_100(quiz_df: pd.DataFrame) -> None:
    """normalize="total" — every bar across the chart sums to 100."""
    fig = counts(quiz_df, "q1_correct", group="treatment",
                 mode="percent", normalize="total")
    grand = sum(sum(t["y"]) for t in fig["data"])
    assert grand == pytest.approx(100.0)


def test_percent_grouped_within_group_each_trace_sums_to_100(quiz_df: pd.DataFrame) -> None:
    """normalize="within_group" — each trace's bars sum to 100 (each
    group level is its own pie)."""
    fig = counts(quiz_df, "q1_correct", group="treatment",
                 mode="percent", normalize="within_group")
    for trace in fig["data"]:
        assert sum(trace["y"]) == pytest.approx(100.0)


def test_percent_grouped_within_x_each_x_level_sums_to_100(quiz_df: pd.DataFrame) -> None:
    """normalize="within_x" — at each x-level, the sum across groups
    is 100."""
    fig = counts(quiz_df, "q1_correct", group="treatment",
                 mode="percent", normalize="within_x")
    n_x = len(fig["data"][0]["y"])
    for xi in range(n_x):
        col_sum = sum(trace["y"][xi] for trace in fig["data"])
        assert col_sum == pytest.approx(100.0)


def test_default_normalize_is_total_regardless_of_grouping(quiz_df: pd.DataFrame) -> None:
    """The whole point of option (A) — the default never silently shifts."""
    fig_ungrouped = counts(quiz_df, "q1_correct", mode="percent")
    fig_grouped = counts(quiz_df, "q1_correct", group="treatment", mode="percent")
    # Both must use "total" normalization.
    assert sum(_bar_ys(fig_ungrouped)) == pytest.approx(100.0)
    grand_grouped = sum(sum(t["y"]) for t in fig_grouped["data"])
    assert grand_grouped == pytest.approx(100.0)


def test_count_mode_ignores_normalize_parameter(quiz_df: pd.DataFrame) -> None:
    """Setting normalize doesn't change anything when mode is count."""
    fig_total = counts(quiz_df, "q1_correct", group="treatment",
                       mode="count", normalize="total")
    fig_within = counts(quiz_df, "q1_correct", group="treatment",
                        mode="count", normalize="within_group")
    for ti in range(_trace_count(fig_total)):
        assert _bar_ys(fig_total, ti) == _bar_ys(fig_within, ti)


# ---------------------------------------------------------------------------
# NaN handling
# ---------------------------------------------------------------------------

def test_nan_cells_dropped(quiz_df: pd.DataFrame) -> None:
    df = quiz_df.copy()
    # Punch some NaNs into both columns
    df.loc[df.index[0:5], "q1_correct"] = np.nan
    df.loc[df.index[5:10], "treatment"] = np.nan
    fig = counts(df, "q1_correct", group="treatment", mode="count")
    # NaN rows must not contribute to any trace
    expected_n = int(df.dropna(subset=["q1_correct", "treatment"]).shape[0])
    assert sum(sum(t["y"]) for t in fig["data"]) == pytest.approx(expected_n)


# ---------------------------------------------------------------------------
# Encounter order
# ---------------------------------------------------------------------------

def test_encounter_order_preserved_on_x_axis() -> None:
    """A column with timepoint labels in non-alphabetical encounter
    order must come out in that same order on the x-axis."""
    df = pd.DataFrame({
        "timepoint": ["Baseline", "Baseline", "5-day", "5-day", "10-day", "10-day"],
        "treatment": ["A", "B", "A", "B", "A", "B"],
    })
    fig = counts(df, "timepoint", mode="count")
    assert _xs(fig) == ["Baseline", "5-day", "10-day"]
    # categoryorder must be pinned to that array
    assert fig["layout"]["xaxis"]["categoryorder"] == "array"
    assert fig["layout"]["xaxis"]["categoryarray"] == ["Baseline", "5-day", "10-day"]


def test_encounter_order_preserved_on_group_legend() -> None:
    """Group level order is preserved across the legend / trace order."""
    df = pd.DataFrame({
        "q": [0, 1, 0, 1, 0, 1],
        "arm": ["control", "treatment", "control", "treatment", "control", "treatment"],
    })
    fig = counts(df, "q", group="arm", mode="count")
    trace_names = [t["name"] for t in fig["data"]]
    assert trace_names == ["control", "treatment"]


# ---------------------------------------------------------------------------
# Value labels
# ---------------------------------------------------------------------------

def test_value_labels_displayed_on_x_axis() -> None:
    """A {0: "incorrect", 1: "correct"} mapping should show those
    strings on the x-axis, not the numeric codes."""
    df = pd.DataFrame({"q1": [0, 0, 0, 1, 1, 1, 1, 1]})
    fig = counts(
        df, "q1", mode="count",
        value_labels={"q1": {0: "incorrect", 1: "correct"}},
    )
    assert _xs(fig) == ["incorrect", "correct"]


def test_value_labels_on_group_legend() -> None:
    df = pd.DataFrame({
        "q": [0, 0, 0, 1, 1, 1],
        "arm": [1, 2, 1, 2, 1, 2],
    })
    fig = counts(
        df, "q", group="arm", mode="count",
        value_labels={"arm": {1: "control", 2: "treatment"}},
    )
    trace_names = [t["name"] for t in fig["data"]]
    assert trace_names == ["control", "treatment"]


# ---------------------------------------------------------------------------
# Route: command preview omits suffix only when at Stata default
# ---------------------------------------------------------------------------

def test_route_command_count_ungrouped(client: TestClient, quiz_df: pd.DataFrame, tmp_path) -> None:
    _load_frame(client, quiz_df, tmp_path)
    resp = client.post("/api/graphs/counts", json={
        "x": "q1_correct", "mode": "count",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["command"] == "graph bar (count) q1_correct"


def test_route_command_percent_grouped_within_group_no_suffix(client: TestClient,
                                                              quiz_df: pd.DataFrame, tmp_path) -> None:
    """within_group matches Stata's default for `(percent) y, over(x)`
    — no normalize(...) suffix in the command preview."""
    _load_frame(client, quiz_df, tmp_path)
    resp = client.post("/api/graphs/counts", json={
        "x": "q1_correct", "group": "treatment",
        "mode": "percent", "normalize": "within_group",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["command"] == "graph bar (percent) q1_correct, over(treatment)"


def test_route_command_percent_grouped_total_has_suffix(client: TestClient,
                                                        quiz_df: pd.DataFrame, tmp_path) -> None:
    _load_frame(client, quiz_df, tmp_path)
    resp = client.post("/api/graphs/counts", json={
        "x": "q1_correct", "group": "treatment",
        "mode": "percent", "normalize": "total",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["command"] == (
        "graph bar (percent) q1_correct, over(treatment) normalize(total)"
    )


def test_route_command_percent_grouped_within_x_has_suffix(client: TestClient,
                                                           quiz_df: pd.DataFrame, tmp_path) -> None:
    _load_frame(client, quiz_df, tmp_path)
    resp = client.post("/api/graphs/counts", json={
        "x": "q1_correct", "group": "treatment",
        "mode": "percent", "normalize": "within_x",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["command"] == (
        "graph bar (percent) q1_correct, over(treatment) normalize(within_x)"
    )


def test_route_command_percent_ungrouped_no_suffix(client: TestClient,
                                                   quiz_df: pd.DataFrame, tmp_path) -> None:
    """Ungrouped collapses all normalize scopes to total — no suffix."""
    _load_frame(client, quiz_df, tmp_path)
    resp = client.post("/api/graphs/counts", json={
        "x": "q1_correct", "mode": "percent", "normalize": "total",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["command"] == "graph bar (percent) q1_correct"


def test_ungrouped_counts_cycle_marker_color_per_category(quiz_df: pd.DataFrame) -> None:
    """Categorical levels are distinct — each bar gets its own PALETTE
    color, same per-bar array convention as the single-group bar chart."""
    from solarstata.engine.graphs import _color_for

    fig = counts(quiz_df, "q1_correct")
    color = fig["data"][0]["marker"]["color"]
    assert isinstance(color, list)
    assert len(color) == 2  # one entry per q1_correct level
    assert color == [_color_for(i) for i in range(2)]


def test_route_unknown_variable_400(client: TestClient, quiz_df: pd.DataFrame, tmp_path) -> None:
    _load_frame(client, quiz_df, tmp_path)
    resp = client.post("/api/graphs/counts", json={
        "x": "nonexistent_column", "mode": "count",
    })
    assert resp.status_code == 400


def _load_frame(client: TestClient, df: pd.DataFrame, tmp_path) -> None:
    """Helper: stage a CSV upload so the session has a frame to chart against."""
    p = tmp_path / "fixture.csv"
    df.to_csv(p, index=False)
    with p.open("rb") as fh:
        client.post(
            "/api/data/upload",
            files={"file": ("fixture.csv", fh, "text/csv")},
        )
