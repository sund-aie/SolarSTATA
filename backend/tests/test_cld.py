"""Compact letter display (v3.3) — algorithm + bar-chart rendering.

compact_letter_display RENDERS the posthoc_block a prior oneway
produced; it never computes statistics. These tests pin down:

1. The defining CLD property, both directions: two groups share a
   letter IFF their pair is not significantly different (strict
   p < .05, same alpha as the brackets).
2. Missing pairs (p_adj None) are treated as not significantly
   different and counted in n_missing — never invented either way.
3. Determinism: same input, same letters; leftmost group reads "a".
4. The bar renderer: one letter annotation per bar in bracket-star
   font, an under-plot caveat + widened margin only when a pair is
   missing, and the same silent skips as brackets (ungrouped bars,
   subgroup clustering).
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine.cld import SIGNIFICANCE_ALPHA, compact_letter_display
from solarstata.engine.graphs import ACCENT, CAVEAT, CAVEAT_TEXT, bar_with_ci, box


def _cmp(a: str, b: str, p_adj: float | None) -> dict:
    return {"a": a, "b": b, "mean_diff": 0.0, "se": 0.0, "t": 0.0,
            "p_raw": p_adj, "p_adj": p_adj}


def _shares_letter(letters: dict[str, str], a: str, b: str) -> bool:
    return bool(set(letters[a]) & set(letters[b]))


# ---------------------------------------------------------------------------
# Algorithm — the defining property
# ---------------------------------------------------------------------------

def test_all_pairs_significant_gives_distinct_letters() -> None:
    names = ["A", "B", "C"]
    comparisons = [_cmp(a, b, 0.001) for a, b in combinations(names, 2)]
    letters, n_missing = compact_letter_display(names, comparisons)
    assert letters == {"A": "a", "B": "b", "C": "c"}
    assert n_missing == 0


def test_no_pairs_significant_gives_one_shared_letter() -> None:
    names = ["A", "B", "C"]
    comparisons = [_cmp(a, b, 0.9) for a, b in combinations(names, 2)]
    letters, n_missing = compact_letter_display(names, comparisons)
    assert letters == {"A": "a", "B": "a", "C": "a"}
    assert n_missing == 0


def test_chain_overlap_gives_ab_middle_group() -> None:
    """A≠C but A~B and B~C — the classic a / ab / b pattern."""
    names = ["A", "B", "C"]
    comparisons = [
        _cmp("A", "B", 0.40),
        _cmp("A", "C", 0.01),
        _cmp("B", "C", 0.30),
    ]
    letters, _ = compact_letter_display(names, comparisons)
    assert letters == {"A": "a", "B": "ab", "C": "b"}


def test_share_letter_iff_not_significant_on_mixed_four_groups() -> None:
    """Both directions of the CLD contract on a 4-group mixed fixture."""
    names = ["A", "B", "C", "D"]
    p_by_pair = {
        ("A", "B"): 0.002, ("A", "C"): 0.500, ("A", "D"): 0.010,
        ("B", "C"): 0.030, ("B", "D"): 0.700, ("C", "D"): 0.200,
    }
    comparisons = [_cmp(a, b, p) for (a, b), p in p_by_pair.items()]
    letters, _ = compact_letter_display(names, comparisons)
    for (a, b), p in p_by_pair.items():
        if p < SIGNIFICANCE_ALPHA:
            assert not _shares_letter(letters, a, b), f"{a}/{b} (p={p}) share a letter"
        else:
            assert _shares_letter(letters, a, b), f"{a}/{b} (p={p}) share no letter"


def test_two_groups_significant_and_not() -> None:
    sig, _ = compact_letter_display(["A", "B"], [_cmp("A", "B", 0.01)])
    nsd, _ = compact_letter_display(["A", "B"], [_cmp("A", "B", 0.50)])
    assert sig == {"A": "a", "B": "b"}
    assert nsd == {"A": "a", "B": "a"}


def test_alpha_boundary_is_strict() -> None:
    """p_adj == .05 exactly is NOT significant — matches _stars_tier."""
    letters, _ = compact_letter_display(["A", "B"], [_cmp("A", "B", 0.05)])
    assert letters == {"A": "a", "B": "a"}


def test_every_group_always_gets_at_least_one_letter() -> None:
    """Even a group significantly different from all others keeps a letter."""
    names = ["A", "B", "C", "D"]
    comparisons = [_cmp("A", other, 0.001) for other in ("B", "C", "D")]
    comparisons += [_cmp(a, b, 0.9) for a, b in (("B", "C"), ("B", "D"), ("C", "D"))]
    letters, _ = compact_letter_display(names, comparisons)
    assert all(letters[n] for n in names)
    assert letters == {"A": "a", "B": "b", "C": "b", "D": "b"}


# ---------------------------------------------------------------------------
# Algorithm — missing and irrelevant pairs
# ---------------------------------------------------------------------------

def test_none_p_adj_treated_as_not_significant_and_counted() -> None:
    names = ["A", "B", "C"]
    comparisons = [
        _cmp("A", "B", None),
        _cmp("A", "C", 0.001),
        _cmp("B", "C", 0.001),
    ]
    letters, n_missing = compact_letter_display(names, comparisons)
    assert n_missing == 1
    assert _shares_letter(letters, "A", "B")  # the missing pair shares
    assert not _shares_letter(letters, "A", "C")
    assert not _shares_letter(letters, "B", "C")


def test_n_missing_zero_when_all_pairs_computed() -> None:
    names = ["A", "B"]
    _, n_missing = compact_letter_display(names, [_cmp("A", "B", 0.3)])
    assert n_missing == 0


def test_pairs_naming_uncharted_groups_are_ignored() -> None:
    """Comparisons referencing groups not on the chart don't count —
    not even toward n_missing — mirroring the bracket renderer."""
    names = ["A", "B"]
    comparisons = [
        _cmp("A", "B", 0.01),
        _cmp("A", "Z", 0.001),
        _cmp("Z", "Q", None),
    ]
    letters, n_missing = compact_letter_display(names, comparisons)
    assert letters == {"A": "a", "B": "b"}
    assert n_missing == 0


def test_empty_comparisons_share_one_letter() -> None:
    letters, n_missing = compact_letter_display(["A", "B", "C"], [])
    assert letters == {"A": "a", "B": "a", "C": "a"}
    assert n_missing == 0


def test_letters_are_deterministic_and_follow_display_order() -> None:
    names = ["Baseline", "5-day", "10-day"]
    comparisons = [
        _cmp("Baseline", "5-day", 0.01),
        _cmp("Baseline", "10-day", 0.001),
        _cmp("5-day", "10-day", 0.60),
    ]
    first, _ = compact_letter_display(names, comparisons)
    second, _ = compact_letter_display(names, comparisons)
    assert first == second
    # Display-leftmost group reads "a"; the NSD pair shares "b".
    assert first == {"Baseline": "a", "5-day": "b", "10-day": "b"}


# ---------------------------------------------------------------------------
# Bar rendering — annotations, caveat, skips
# ---------------------------------------------------------------------------

@pytest.fixture
def four_groups_df() -> pd.DataFrame:
    rng = np.random.default_rng(seed=11)
    rows = []
    for label, mean in [("A", 10.0), ("B", 12.0), ("C", 14.0), ("D", 16.0)]:
        for _ in range(10):
            rows.append({"y": rng.normal(mean, 1.0), "g": label})
    return pd.DataFrame(rows)


def _posthoc_block(p_adjs: dict[tuple[str, str], float | None]) -> dict:
    return {
        "method": "bonferroni",
        "n_pairs": len(p_adjs),
        "comparisons": [_cmp(a, b, p) for (a, b), p in p_adjs.items()],
        "matrix": {},
    }


def _all_significant_block() -> dict:
    return _posthoc_block({pair: 0.001 for pair in combinations("ABCD", 2)})


def test_bar_letters_one_annotation_per_bar_no_shapes(four_groups_df: pd.DataFrame) -> None:
    fig = bar_with_ci(four_groups_df, "y", group="g",
                      pairwise=_all_significant_block(), posthoc_viz="letters")
    annotations = fig["layout"].get("annotations", [])
    assert len(annotations) == 4
    assert [a["text"] for a in annotations] == ["a", "b", "c", "d"]
    assert fig["layout"].get("shapes", []) == []  # letters never draw brackets


def test_bar_letters_use_bracket_star_font(four_groups_df: pd.DataFrame) -> None:
    fig = bar_with_ci(four_groups_df, "y", group="g",
                      pairwise=_all_significant_block(), posthoc_viz="letters")
    for a in fig["layout"]["annotations"]:
        assert a["font"] == {"family": "Geist Mono, monospace", "size": 13,
                             "color": "rgba(0,0,0,0.75)"}


def test_bar_letters_sit_above_bar_plus_error_tip(four_groups_df: pd.DataFrame) -> None:
    fig = bar_with_ci(four_groups_df, "y", group="g",
                      pairwise=_all_significant_block(), posthoc_viz="letters")
    trace = fig["data"][0]
    tops = [y + e for y, e in zip(trace["y"], trace["error_y"]["array"])]
    for annotation, top in zip(fig["layout"]["annotations"], tops):
        assert annotation["y"] > top


def test_bar_letters_missing_pair_emits_caveat_and_widens_margin(
    four_groups_df: pd.DataFrame,
) -> None:
    block = _posthoc_block({pair: 0.001 for pair in combinations("ABCD", 2)})
    block["comparisons"][0]["p_adj"] = None  # A vs B not computable
    fig = bar_with_ci(four_groups_df, "y", group="g",
                      pairwise=block, posthoc_viz="letters")
    annotations = fig["layout"]["annotations"]
    caveats = [a for a in annotations if a["text"] == CAVEAT_TEXT]
    assert len(caveats) == 1
    caveat = caveats[0]
    assert caveat["xref"] == "paper" and caveat["yref"] == "paper"
    assert caveat["font"]["color"] == CAVEAT
    assert fig["layout"]["margin"]["b"] == 80
    # The affected pair now shares a letter instead of claiming a result.
    a_letters, b_letters = annotations[0]["text"], annotations[1]["text"]
    assert set(a_letters) & set(b_letters)


def test_bar_letters_no_missing_pairs_keeps_default_margin(
    four_groups_df: pd.DataFrame,
) -> None:
    fig = bar_with_ci(four_groups_df, "y", group="g",
                      pairwise=_all_significant_block(), posthoc_viz="letters")
    assert fig["layout"]["margin"]["b"] == 50
    assert all(a["text"] != CAVEAT_TEXT for a in fig["layout"]["annotations"])


def test_bar_default_posthoc_viz_still_renders_brackets(four_groups_df: pd.DataFrame) -> None:
    """Back-compat: callers that pass pairwise without posthoc_viz get
    the v3.2 brackets, untouched."""
    fig = bar_with_ci(four_groups_df, "y", group="g", pairwise=_all_significant_block())
    assert len(fig["layout"]["shapes"]) == 6 * 3  # 6 sig pairs × 3 line shapes
    assert all(a["text"].startswith("*") for a in fig["layout"]["annotations"])


def test_ungrouped_and_subgrouped_bars_skip_letters(four_groups_df: pd.DataFrame) -> None:
    df = four_groups_df.assign(t=np.tile(["pre", "post"], 20))
    ungrouped = bar_with_ci(four_groups_df, "y",
                            pairwise=_all_significant_block(), posthoc_viz="letters")
    clustered = bar_with_ci(df, "y", group="g", subgroup="t",
                            pairwise=_all_significant_block(), posthoc_viz="letters")
    assert ungrouped["layout"].get("annotations", []) == []
    assert ungrouped["data"][0]["marker"]["color"] == ACCENT
    assert clustered["layout"].get("annotations", []) == []


# ---------------------------------------------------------------------------
# Clustered bars — letters per bar, comparing groups WITHIN each subgroup
# ---------------------------------------------------------------------------

@pytest.fixture
def clustered_df() -> pd.DataFrame:
    """4 materials × 2 timepoints, means far apart within each timepoint
    so every within-timepoint pair is significant."""
    rng = np.random.default_rng(seed=23)
    rows = []
    for t in ("pre", "post"):
        for g, mean in [("A", 10.0), ("B", 20.0), ("C", 30.0), ("D", 40.0)]:
            for _ in range(12):
                rows.append({"y": rng.normal(mean, 1.0), "g": g, "t": t})
    return pd.DataFrame(rows)


def test_clustered_letters_one_per_bar_at_exact_offsets(clustered_df: pd.DataFrame) -> None:
    fig = bar_with_ci(clustered_df, "y", group="g", subgroup="t",
                      posthoc_viz="letters", posthoc_method="bonferroni")
    annotations = fig["layout"]["annotations"]
    assert len(annotations) == 8  # 4 groups × 2 timepoints
    # bargap geometry is pinned, so positions are exact: category i,
    # trace j of 2 → x = i − 0.4 + 0.8·(j + 0.5)/2.
    assert fig["layout"]["bargap"] == 0.2
    expected_x = sorted(i - 0.4 + 0.8 * (j + 0.5) / 2 for j in range(2) for i in range(4))
    assert sorted(a["x"] for a in annotations) == pytest.approx(expected_x)
    for a in annotations:
        assert a["font"] == {"family": "Geist Mono, monospace", "size": 13,
                             "color": "rgba(0,0,0,0.75)"}


def test_clustered_letters_compare_within_each_subgroup_level(
    clustered_df: pd.DataFrame,
) -> None:
    """All pairs significant within each timepoint → a/b/c/d twice, and
    each letter set is independent per timepoint (both start at 'a')."""
    fig = bar_with_ci(clustered_df, "y", group="g", subgroup="t",
                      posthoc_viz="letters", posthoc_method="bonferroni")
    by_trace: dict[int, list[str]] = {0: [], 1: []}
    for a in fig["layout"]["annotations"]:
        j = 0 if (a["x"] - round(a["x"])) < 0 else 1  # left/right bar of the pair
        by_trace[j].append(a["text"])
    assert sorted(by_trace[0]) == ["a", "b", "c", "d"]
    assert sorted(by_trace[1]) == ["a", "b", "c", "d"]


def test_clustered_letters_share_iff_not_significant_per_level() -> None:
    """Mixed effects: A≠B at pre, A~B at post — letters must flip
    between the two timepoints accordingly."""
    rng = np.random.default_rng(seed=20)  # p_pre ≈ 1e-22, p_post ≈ .98
    rows = []
    for g, pre_mean, post_mean in [("A", 10.0, 15.0), ("B", 20.0, 15.0)]:
        for _ in range(15):
            rows.append({"y": rng.normal(pre_mean, 1.0), "g": g, "t": "pre"})
            rows.append({"y": rng.normal(post_mean, 1.0), "g": g, "t": "post"})
    fig = bar_with_ci(pd.DataFrame(rows), "y", group="g", subgroup="t",
                      posthoc_viz="letters", posthoc_method="bonferroni")
    annotations = fig["layout"]["annotations"]
    assert len(annotations) == 4
    pre = [a["text"] for a in annotations if (a["x"] - round(a["x"])) < 0]
    post = [a["text"] for a in annotations if (a["x"] - round(a["x"])) > 0]
    assert pre == ["a", "b"]      # significantly different at pre
    assert post == ["a", "a"]     # not significantly different at post


def test_clustered_letters_skip_empty_cells() -> None:
    rng = np.random.default_rng(seed=31)
    rows = []
    for g, mean in [("A", 10.0), ("B", 20.0), ("C", 30.0)]:
        for t in ("pre", "post"):
            if g == "C" and t == "post":
                continue  # C never measured at post
            for _ in range(10):
                rows.append({"y": rng.normal(mean, 1.0), "g": g, "t": t})
    fig = bar_with_ci(pd.DataFrame(rows), "y", group="g", subgroup="t",
                      posthoc_viz="letters", posthoc_method="bonferroni")
    # 3 bars at pre + 2 at post — the missing C/post bar gets no letter.
    assert len(fig["layout"]["annotations"]) == 5


def test_clustered_default_method_none_stays_bare(clustered_df: pd.DataFrame) -> None:
    fig = bar_with_ci(clustered_df, "y", group="g", subgroup="t")
    assert fig["layout"].get("annotations", []) == []
    assert fig["layout"].get("shapes", []) == []


def test_clustered_not_computable_level_emits_caveat() -> None:
    """A timepoint where every group has one observation has no within
    error term — its pairs are not computable, so the caveat shows and
    no result is invented (the affected bars share a letter)."""
    rng = np.random.default_rng(seed=37)
    rows = []
    for g, mean in [("A", 10.0), ("B", 20.0)]:
        rows.append({"y": mean, "g": g, "t": "single"})  # n=1 cells
        for _ in range(10):
            rows.append({"y": rng.normal(mean, 1.0), "g": g, "t": "full"})
    fig = bar_with_ci(pd.DataFrame(rows), "y", group="g", subgroup="t",
                      posthoc_viz="letters", posthoc_method="bonferroni")
    caveats = [a for a in fig["layout"]["annotations"] if a["text"] == CAVEAT_TEXT]
    assert len(caveats) == 1
    assert fig["layout"]["margin"]["b"] == 80


# ---------------------------------------------------------------------------
# Box rendering — same letters, box tops instead of bar tops
# ---------------------------------------------------------------------------

def test_box_letters_one_annotation_per_box_no_shapes(four_groups_df: pd.DataFrame) -> None:
    fig = box(four_groups_df, "y", group="g", pairwise=_all_significant_block())
    annotations = fig["layout"].get("annotations", [])
    assert len(annotations) == 4
    assert [a["text"] for a in annotations] == ["a", "b", "c", "d"]
    assert fig["layout"].get("shapes", []) == []  # box is letters-only
    # Identical font to the bar letters and the bracket stars.
    for a in annotations:
        assert a["font"] == {"family": "Geist Mono, monospace", "size": 13,
                             "color": "rgba(0,0,0,0.75)"}


def test_box_letters_sit_above_each_group_max(four_groups_df: pd.DataFrame) -> None:
    fig = box(four_groups_df, "y", group="g", pairwise=_all_significant_block())
    for annotation, trace in zip(fig["layout"]["annotations"], fig["data"]):
        assert annotation["x"] == trace["name"]
        assert annotation["y"] > max(trace["y"])


def test_box_axis_is_category_typed_in_encounter_order(four_groups_df: pd.DataFrame) -> None:
    fig = box(four_groups_df, "y", group="g", pairwise=_all_significant_block())
    xaxis = fig["layout"]["xaxis"]
    assert xaxis["type"] == "category"
    assert xaxis["categoryorder"] == "array"
    assert xaxis["categoryarray"] == [t["name"] for t in fig["data"]]


def test_box_letters_missing_pair_emits_caveat_and_widens_margin(
    four_groups_df: pd.DataFrame,
) -> None:
    block = _posthoc_block({pair: 0.001 for pair in combinations("ABCD", 2)})
    block["comparisons"][0]["p_adj"] = None
    fig = box(four_groups_df, "y", group="g", pairwise=block)
    caveats = [a for a in fig["layout"]["annotations"] if a["text"] == CAVEAT_TEXT]
    assert len(caveats) == 1
    assert caveats[0]["xref"] == "paper" and caveats[0]["yref"] == "paper"
    assert caveats[0]["font"]["color"] == CAVEAT
    assert fig["layout"]["margin"]["b"] == 80


def test_box_without_pairwise_has_no_annotations(four_groups_df: pd.DataFrame) -> None:
    fig = box(four_groups_df, "y", group="g")
    assert fig["layout"].get("annotations", []) == []
    assert fig["layout"]["margin"]["b"] == 50


def test_ungrouped_box_ignores_pairwise(four_groups_df: pd.DataFrame) -> None:
    fig = box(four_groups_df, "y", pairwise=_all_significant_block())
    assert fig["layout"].get("annotations", []) == []
    assert len(fig["data"]) == 1
