"""Plain-English interpretation layer (v3.3 keystone).

interpret() RENDERS existing engine payloads into sentences; it never
computes a statistic. These tests pin the phrasing contract:

1. Direction names the actually-higher group / the sign of the actual
   coefficient, and FLIPS when the data flip — the worst failure mode
   (inverted A/B) is tested in both directions for oneway, regress,
   and logit.
2. Significance language is strict p < .05: a non-significant result
   never reads "significant" without negation, and never "equal" /
   "equivalent" / "the same".
3. The p-format cutoffs are pinned with explicit strings (.0009, .003,
   .03, and the .05 boundary).
4. None values (a not-computable p_adj, a missing F) produce "could
   not be computed" sentences — never a fabricated comparison.
5. No observational result ever reads causally ("caused", "led to",
   "because").

Fixtures call the real engine functions so payload shapes can never
drift from production; hand-built dicts (mirroring those shapes
exactly) cover the edge cases real fits cannot easily produce.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine.anova import anova_two, oneway
from solarstata.engine.diagnostics import levene, shapiro
from solarstata.engine.interpret import SIGNIFICANCE_ALPHA, format_p, interpret
from solarstata.engine.logit import logit
from solarstata.engine.regress import regress
from solarstata.engine.tabstat import tabstat

CAUSAL_WORDS = ("caused", "led to", "because")
EQUALITY_WORDS = ("equal", "equivalent", "the same")


def _assert_never_causal_or_equal(sentences: list[str]) -> None:
    joined = " ".join(sentences).lower()
    for word in CAUSAL_WORDS + EQUALITY_WORDS:
        assert word not in joined, f"forbidden word {word!r} in: {joined}"


# ---------------------------------------------------------------------------
# Engine-built fixtures
# ---------------------------------------------------------------------------

def _two_group_df(mean_a: float, mean_b: float, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = [{"y": rng.normal(mean_a, 1.0), "g": "A"} for _ in range(20)]
    rows += [{"y": rng.normal(mean_b, 1.0), "g": "B"} for _ in range(20)]
    return pd.DataFrame(rows)


def _slope_df(slope: float, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 10, 60)
    return pd.DataFrame({"x": x, "y": slope * x + rng.normal(0, 0.5, 60)})


# ---------------------------------------------------------------------------
# p-format — explicit string pins
# ---------------------------------------------------------------------------

def test_format_p_cutoffs_exact() -> None:
    assert format_p(0.0009) == "p < .001"
    assert format_p(0.003) == "p = .003"
    assert format_p(0.03) == "p = .03"
    assert format_p(0.05) == "p = .05"
    assert format_p(0.45) == "p = .45"


def test_alpha_boundary_is_not_significant() -> None:
    payload = {
        "kind": "oneway", "depvar": "y", "groupvar": "g", "k": 2,
        "F": 3.9, "p": 0.05,
        "anova_table": {"df": [1, 38, 39]},
        "posthoc_block": None,
    }
    [sentence] = interpret("oneway", payload)
    assert "did not differ significantly" in sentence
    assert "p = .05" in sentence
    assert SIGNIFICANCE_ALPHA == 0.05


# ---------------------------------------------------------------------------
# oneway — direction, posthoc, missing pairs
# ---------------------------------------------------------------------------

def test_oneway_significant_overall_sentence_reads_payload_numbers() -> None:
    result = oneway(_two_group_df(10.0, 14.0), "y", "g").structured
    sentences = interpret("oneway", result)
    overall = sentences[0]
    assert "Mean y differed significantly across the 2 g groups" in overall
    assert f"F(1, 38)" in overall
    assert "p < .001" in overall


def test_oneway_pair_direction_names_higher_group_and_flips() -> None:
    b_higher = interpret("oneway", oneway(
        _two_group_df(10.0, 14.0), "y", "g", posthoc="bonferroni").structured)
    a_higher = interpret("oneway", oneway(
        _two_group_df(14.0, 10.0), "y", "g", posthoc="bonferroni").structured)
    assert any("B showed significantly higher mean y than A" in s for s in b_higher)
    assert any("A showed significantly higher mean y than B" in s for s in a_higher)
    # The inverted claim must not appear in either output.
    assert not any("A showed significantly higher" in s for s in b_higher)
    assert not any("B showed significantly higher" in s for s in a_higher)


def test_oneway_mentions_correction_method() -> None:
    result = oneway(_two_group_df(10.0, 14.0), "y", "g", posthoc="bonferroni").structured
    sentences = interpret("oneway", result)
    assert any("Bonferroni correction" in s for s in sentences)


def test_oneway_nonsignificant_never_overclaims() -> None:
    result = oneway(_two_group_df(10.0, 10.0), "y", "g", posthoc="bonferroni").structured
    sentences = interpret("oneway", result)
    assert any("did not differ significantly" in s for s in sentences)
    # The only "significant" tokens allowed are negated forms.
    for s in sentences:
        bare = s.replace("not differ significantly", "") \
                .replace("No significant", "").replace("no significant", "") \
                .replace("reached significance", "")
        assert "significant" not in bare, s
    _assert_never_causal_or_equal(sentences)


def test_oneway_none_p_adj_says_could_not_be_computed() -> None:
    result = oneway(_two_group_df(10.0, 14.0), "y", "g", posthoc="bonferroni").structured
    result["posthoc_block"]["comparisons"][0]["p_adj"] = None
    sentences = interpret("oneway", result)
    assert any("A vs B comparison could not be computed" in s for s in sentences)
    # No direction claim may be fabricated for the missing pair.
    assert not any("showed significantly higher" in s for s in sentences)


# ---------------------------------------------------------------------------
# anova_two — main effects + careful interaction phrasing
# ---------------------------------------------------------------------------

def _anova_two_payload(p_a: float, p_b: float, p_inter: float) -> dict:
    return {
        "kind": "anova_two", "depvar": "y", "factor_a": "drug", "factor_b": "sex",
        "interaction": True,
        "rows": [
            {"Source": "drug", "SS": 10.0, "df": 1, "MS": 10.0, "F": 9.0, "Prob_F": p_a},
            {"Source": "sex", "SS": 1.0, "df": 1, "MS": 1.0, "F": 0.8, "Prob_F": p_b},
            {"Source": "drug # sex", "SS": 6.0, "df": 1, "MS": 6.0, "F": 5.5, "Prob_F": p_inter},
            {"Source": "Residual", "SS": 50.0, "df": 36, "MS": 1.4, "F": None, "Prob_F": None},
        ],
    }


def test_anova_two_significant_interaction_says_effect_depends() -> None:
    sentences = interpret("anova_two", _anova_two_payload(0.004, 0.40, 0.02))
    inter = next(s for s in sentences if "interaction" in s)
    assert "drug × sex interaction was significant" in inter
    assert "depended on the level of sex" in inter
    assert any("significant main effect of drug" in s for s in sentences)
    assert any("No significant main effect of sex" in s for s in sentences)


def test_anova_two_nonsignificant_interaction_does_not_imply_dependence() -> None:
    sentences = interpret("anova_two", _anova_two_payload(0.004, 0.40, 0.60))
    inter = next(s for s in sentences if "interaction" in s)
    assert "was not significant" in inter
    assert "depended" not in inter
    _assert_never_causal_or_equal(sentences)


def test_anova_two_real_engine_payload_round_trips() -> None:
    rng = np.random.default_rng(3)
    rows = []
    for a in ("ctrl", "treat"):
        for b in ("f", "m"):
            shift = 3.0 if a == "treat" else 0.0
            for _ in range(15):
                rows.append({"y": rng.normal(10 + shift, 1.0), "a": a, "b": b})
    result = anova_two(pd.DataFrame(rows), "y", "a", "b").structured
    sentences = interpret("anova_two", result)
    assert any("significant main effect of a" in s for s in sentences)
    _assert_never_causal_or_equal(sentences)


# ---------------------------------------------------------------------------
# anova_rm — within effect + sphericity mention
# ---------------------------------------------------------------------------

def _anova_rm_payload(correction: str) -> dict:
    corrected = correction != "none"
    return {
        "kind": "anova_rm", "depvar": "score", "subject": "id", "within": "time",
        "between": None, "between_summary": None, "correction": correction,
        "rows": [{
            "Source": "time", "F": 12.0, "df_num": 2.0, "df_den": 18.0,
            "p": 0.0004,
            "epsilon": 0.81 if corrected else None,
            "p_adj": 0.002 if corrected else None,
        }],
        "n_subjects": 10, "n_obs": 30,
    }


def test_anova_rm_within_effect_sentence() -> None:
    sentences = interpret("anova_rm", _anova_rm_payload("none"))
    [s] = sentences
    assert "within-subject effect of time on score was significant" in s
    assert "F(2, 18) = 12.00" in s
    assert "p < .001" in s
    assert "sphericity" not in s


def test_anova_rm_mentions_sphericity_correction_and_uses_adjusted_p() -> None:
    [s] = interpret("anova_rm", _anova_rm_payload("gg"))
    assert "Greenhouse-Geisser sphericity correction" in s
    assert "p = .002" in s  # the adjusted p, not the raw .0004


# ---------------------------------------------------------------------------
# regress — model sentence, per-coefficient direction, intercept skipped
# ---------------------------------------------------------------------------

def test_regress_direction_follows_coefficient_sign_and_flips() -> None:
    pos, _ = regress(_slope_df(+3.0), "y", ["x"])
    neg, _ = regress(_slope_df(-3.0), "y", ["x"])
    pos_s = interpret("regress", pos.structured)
    neg_s = interpret("regress", neg.structured)
    assert any("increase in y" in s and "Each unit increase in x" in s for s in pos_s)
    assert any("decrease in y" in s for s in neg_s)
    assert not any("decrease in y" in s for s in pos_s)
    assert not any("increase in y" in s and "associated with a" in s for s in neg_s)


def test_regress_model_sentence_and_intercept_skipped() -> None:
    result, _ = regress(_slope_df(+3.0), "y", ["x"])
    sentences = interpret("regress", result.structured)
    assert any("The model was statistically significant" in s and "R²" in s
               for s in sentences)
    assert not any("_cons" in s for s in sentences)
    _assert_never_causal_or_equal(sentences)


def test_regress_nonsignificant_predictor_phrasing() -> None:
    rng = np.random.default_rng(11)
    df = pd.DataFrame({"x": rng.normal(0, 1, 80), "y": rng.normal(0, 1, 80)})
    result, _ = regress(df, "y", ["x"])
    sentences = interpret("regress", result.structured)
    assert any("x was not significantly associated with y" in s for s in sentences)
    _assert_never_causal_or_equal(sentences)


# ---------------------------------------------------------------------------
# logit — OR path reads the payload OR; non-OR path speaks to sign
# ---------------------------------------------------------------------------

def _logit_payload(*, odds_ratios: bool, coef: float, p: float) -> dict:
    return {
        "kind": "logit", "depvar": "caries", "indepvars": ["smoking"],
        "header": {
            "N": 100, "df_m": 1, "LR_chi2": 9.0, "Prob_chi2": 0.003,
            "Pseudo_R2": 0.08, "log_likelihood": -50.0,
            "log_likelihood_null": -55.0, "vce": "mle", "cluster": None,
            "odds_ratios": odds_ratios,
        },
        "coefficients": [
            {"name": "smoking", "coef": coef, "se": 0.3, "z": 2.9, "p": p,
             "ci_low": coef - 0.5, "ci_high": coef + 0.5,
             "raw_coef": coef, "raw_se": 0.3, "significant": p < 0.05},
            {"name": "_cons", "coef": 0.5, "se": 0.2, "z": 2.0, "p": 0.04,
             "ci_low": 0.1, "ci_high": 0.9, "raw_coef": 0.5, "raw_se": 0.2,
             "significant": True},
        ],
    }


def test_logit_odds_ratio_path_reads_payload_or() -> None:
    above = interpret("logit", _logit_payload(odds_ratios=True, coef=2.50, p=0.004))
    below = interpret("logit", _logit_payload(odds_ratios=True, coef=0.40, p=0.004))
    assert any("2.50× higher odds of caries" in s for s in above)
    assert any("lower odds of caries (odds ratio 0.40" in s for s in below)


def test_logit_log_odds_path_speaks_to_sign() -> None:
    pos = interpret("logit", _logit_payload(odds_ratios=False, coef=1.4, p=0.004))
    neg = interpret("logit", _logit_payload(odds_ratios=False, coef=-1.4, p=0.004))
    assert any("higher odds of caries" in s and "log-odds" in s for s in pos)
    assert any("lower odds of caries" in s and "log-odds" in s for s in neg)


def test_logit_real_engine_payload_round_trips() -> None:
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, 200)
    prob = 1 / (1 + np.exp(-(0.2 + 1.5 * x)))
    df = pd.DataFrame({"x": x, "y": (rng.random(200) < prob).astype(float)})
    result, _ = logit(df, "y", ["x"])
    sentences = interpret("logit", result.structured)
    assert any("The model was statistically significant" in s for s in sentences)
    assert any("higher odds of y" in s for s in sentences)
    _assert_never_causal_or_equal(sentences)


# ---------------------------------------------------------------------------
# shapiro / levene — correct framing
# ---------------------------------------------------------------------------

def test_shapiro_nonsignificant_says_no_departure_detected_not_normal() -> None:
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"y": rng.normal(0, 1, 200)})
    sentences = interpret("shapiro", shapiro(df, "y").structured)
    [s] = sentences
    assert "No significant departure from normality was detected for y" in s
    assert "is normal" not in s and "was normal" not in s


def test_shapiro_significant_departure_and_by_group_labels() -> None:
    rng = np.random.default_rng(5)
    df = pd.DataFrame({
        "y": np.concatenate([rng.exponential(1, 100), rng.normal(0, 1, 100)]),
        "g": ["skewed"] * 100 + ["normal"] * 100,
    })
    sentences = interpret("shapiro", shapiro(df, "y", by="g").structured)
    assert any("y (g = skewed)" in s and "significant departure" in s for s in sentences)
    assert any("y (g = normal)" in s and "No significant departure" in s for s in sentences)


def test_shapiro_not_computable_group_reports_note() -> None:
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0, 1.5, 2.5, 0.9], "g": ["a"] * 5 + ["b"] * 2})
    sentences = interpret("shapiro", shapiro(df, "y", by="g").structured)
    assert any("could not be computed" in s and "(g = b)" in s for s in sentences)


def test_levene_both_directions() -> None:
    rng = np.random.default_rng(19)
    unequal = pd.DataFrame({
        "y": np.concatenate([rng.normal(0, 0.5, 80), rng.normal(0, 3.0, 80)]),
        "g": ["a"] * 80 + ["b"] * 80,
    })
    equal = pd.DataFrame({
        "y": np.random.default_rng(3).normal(0, 1.0, 160),
        "g": ["a"] * 80 + ["b"] * 80,
    })
    [sig] = interpret("levene", levene(unequal, "y", "g").structured)
    [nsd] = interpret("levene", levene(equal, "y", "g").structured)
    assert "Variances differed significantly across g groups" in sig
    assert "do not assume equal variances" in sig
    assert "Variances did not differ significantly across g groups" in nsd
    assert "not contradicted" in nsd


# ---------------------------------------------------------------------------
# descriptives + dispatch
# ---------------------------------------------------------------------------

def test_tabstat_summary_is_factual_with_no_inferential_language() -> None:
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0]})
    sentences = interpret("tabstat", tabstat(df, ["y"]).structured)
    assert sentences and "y:" in sentences[0]
    assert "mean = 2.50" in sentences[0]
    joined = " ".join(sentences).lower()
    for word in ("significant", "p =", "p <", "associated"):
        assert word not in joined


def test_unknown_kind_returns_empty_list() -> None:
    assert interpret("histogram", {"kind": "histogram"}) == []
    assert interpret("", {}) == []


def test_to_response_carries_interpretation_additively() -> None:
    result = oneway(_two_group_df(10.0, 14.0), "y", "g", posthoc="bonferroni")
    resp = result.to_response()
    assert isinstance(resp["interpretation"], list)
    assert len(resp["interpretation"]) >= 2
    # The pre-existing keys are untouched.
    assert set(resp) == {"command", "result", "text", "r_set", "e_set", "interpretation"}
