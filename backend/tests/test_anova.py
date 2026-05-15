"""ANOVA family — oneway with Bartlett, two-way, repeated-measures."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine import anova_rm, anova_two, oneway


@pytest.fixture
def three_groups() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame({
        "y": np.concatenate([
            rng.normal(10.0, 1.0, size=30),
            rng.normal(12.0, 1.0, size=30),
            rng.normal(11.0, 1.0, size=30),
        ]),
        "g": ["a"] * 30 + ["b"] * 30 + ["c"] * 30,
    })


def test_oneway_basic_anova_table(three_groups: pd.DataFrame) -> None:
    res = oneway(three_groups, "y", "g")
    s = res.structured
    assert s["kind"] == "oneway"
    assert s["k"] == 3
    assert s["n"] == 90
    sources = s["anova_table"]["Source"]
    assert sources == ["Between groups", "Within groups", "Total"]
    assert s["F"] is not None and s["F"] > 1.0
    assert s["p"] is not None and s["p"] < 1e-6


def test_oneway_always_emits_bartlett(three_groups: pd.DataFrame) -> None:
    res = oneway(three_groups, "y", "g")
    bart = res.structured["bartlett"]
    assert bart["df"] == 2
    # Variances are roughly equal so we expect Bartlett to fail to reject.
    assert bart["chi2"] is not None
    assert bart["p"] is not None and bart["p"] > 0.01


def test_oneway_bonferroni_posthoc(three_groups: pd.DataFrame) -> None:
    res = oneway(three_groups, "y", "g", posthoc="bonferroni")
    block = res.structured["posthoc_block"]
    assert block is not None
    assert block["method"] == "bonferroni"
    assert block["n_pairs"] == 3
    pairs = {(c["a"], c["b"]) for c in block["comparisons"]}
    assert pairs == {("a", "b"), ("a", "c"), ("b", "c")}
    # The ab and ac pairs should be significant (means differ by ~2 / ~1
    # given the simulated effect sizes).
    by_pair = {(c["a"], c["b"]): c for c in block["comparisons"]}
    assert by_pair[("a", "b")]["p_adj"] is not None
    assert by_pair[("a", "b")]["p_adj"] < 0.001


def test_oneway_command_string(three_groups: pd.DataFrame) -> None:
    assert oneway(three_groups, "y", "g").command == "oneway y g"
    assert oneway(three_groups, "y", "g", posthoc="bonferroni").command == \
        "oneway y g, bonferroni"


def test_oneway_text_has_bartlett(three_groups: pd.DataFrame) -> None:
    text = oneway(three_groups, "y", "g").text
    assert "Bartlett's test for equal variances" in text


def test_oneway_unknown_variable_raises(three_groups: pd.DataFrame) -> None:
    with pytest.raises(KeyError):
        oneway(three_groups, "missing", "g")


# ---------------------------------------------------------------------
# Two-way ANOVA
# ---------------------------------------------------------------------

def test_anova_two_with_interaction() -> None:
    rng = np.random.default_rng(11)
    rows = []
    for a in ("low", "high"):
        for b in ("control", "treatment"):
            mean = (5 if a == "low" else 10) + (0 if b == "control" else 4)
            for _ in range(20):
                rows.append({"y": mean + rng.normal(0, 1), "a": a, "b": b})
    df = pd.DataFrame(rows)

    res = anova_two(df, "y", "a", "b", interaction=True)
    sources = [r["Source"] for r in res.structured["rows"]]
    assert "a" in sources and "b" in sources
    assert any("#" in s for s in sources)  # interaction line present
    # Both main effects should be significant.
    p_by_src = {r["Source"]: r["Prob_F"] for r in res.structured["rows"]}
    assert p_by_src["a"] is not None and p_by_src["a"] < 0.001
    assert p_by_src["b"] is not None and p_by_src["b"] < 0.001


def test_anova_two_without_interaction() -> None:
    df = pd.DataFrame({
        "y": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 2,
        "a": (["x"] * 10 + ["y"] * 10),
        "b": (["p", "q"] * 10),
    })
    res = anova_two(df, "y", "a", "b", interaction=False)
    sources = [r["Source"] for r in res.structured["rows"]]
    assert not any("#" in s for s in sources)


# ---------------------------------------------------------------------
# Repeated-measures ANOVA
# ---------------------------------------------------------------------

def test_anova_rm_within_only() -> None:
    """20 subjects × 3 timepoints, monotonic increase per subject."""
    rng = np.random.default_rng(13)
    rows = []
    for subj in range(20):
        baseline = rng.normal(50, 5)
        for t, offset in enumerate([0, 5, 12]):
            rows.append({
                "subj": f"s{subj}",
                "time": f"t{t}",
                "y": baseline + offset + rng.normal(0, 1),
            })
    df = pd.DataFrame(rows)

    res = anova_rm(df, "y", subject="subj", within="time")
    s = res.structured
    assert s["n_subjects"] == 20
    assert any(r["Source"].lower().startswith("time") for r in s["rows"])
    time_row = next(r for r in s["rows"] if r["Source"].lower().startswith("time"))
    # Effect of time should be highly significant given the +5 / +12 means.
    assert time_row["p"] is not None and time_row["p"] < 1e-6


def test_anova_rm_with_correction() -> None:
    """Same fixture; verify GG correction produces an epsilon ≤ 1."""
    rng = np.random.default_rng(17)
    rows = []
    for subj in range(15):
        baseline = rng.normal(50, 5)
        for t, offset in enumerate([0, 4, 8]):
            rows.append({
                "subj": f"s{subj}",
                "time": f"t{t}",
                "y": baseline + offset + rng.normal(0, 1.5),
            })
    df = pd.DataFrame(rows)

    res = anova_rm(df, "y", subject="subj", within="time", correction="gg")
    time_row = next(r for r in res.structured["rows"] if r["Source"].lower().startswith("time"))
    assert time_row["epsilon"] is not None and 0 < time_row["epsilon"] <= 1.0
    assert time_row["p_adj"] is not None


def test_anova_rm_with_between_subject() -> None:
    """Split-plot workaround: between effect surfaces via subject-level means."""
    rng = np.random.default_rng(19)
    rows = []
    # Two between-groups; group B has a larger overall mean.
    for subj in range(24):
        grp = "A" if subj < 12 else "B"
        baseline = rng.normal(50 if grp == "A" else 58, 4)
        for t, offset in enumerate([0, 3, 6]):
            rows.append({
                "subj": f"s{subj}",
                "time": f"t{t}",
                "grp": grp,
                "y": baseline + offset + rng.normal(0, 1.2),
            })
    df = pd.DataFrame(rows)

    res = anova_rm(df, "y", subject="subj", within="time", between="grp")
    s = res.structured
    assert s["between"] == "grp"
    assert s["between_summary"] is not None
    bs = s["between_summary"]
    assert bs["F"] is not None and bs["F"] > 1.0
    assert bs["p"] is not None and bs["p"] < 0.05
    assert "Between-subjects effect" in res.text
