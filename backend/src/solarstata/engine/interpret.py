"""Plain-English interpretation of engine results.

A RENDERING layer over existing engine output — the same
single-source-of-truth discipline as the significance brackets and the
compact letter display. Every number in a sentence is read from the
result payload; nothing is recomputed here. If phrasing something
would require a new statistic, that statistic belongs in the engine
first, not in this module.

One pure function per result kind, signature (result_dict) ->
list[str]; `interpret(kind, result)` dispatches. Kinds without an
interpreter return [] and the API field stays an empty list — the
frontend renders nothing.

Phrasing rules enforced by tests:
  - Direction comes from the sign of the payload's difference or
    coefficient, naming the actual groups/variables.
  - "significant" appears for p < SIGNIFICANCE_ALPHA only (strict,
    matching graphs._stars_tier); non-significant results read
    "did not differ significantly" / "no significant … was detected",
    never "equal" or a trend claim.
  - Observational language only: "associated with", "differed" —
    never causal.
  - None values are reported as not computable, never invented.
"""

from __future__ import annotations

from .cld import SIGNIFICANCE_ALPHA

__all__ = ["SIGNIFICANCE_ALPHA", "format_p", "interpret"]


# ===================================================================
# Shared formatting — single source of truth for every sentence
# ===================================================================

def format_p(p: float) -> str:
    """Stata-flavoured p rendering: "p < .001" below .001, otherwise
    two decimals without the leading zero ("p = .03"); when two
    decimals would read ".00" (p in [.001, .005)), three decimals so
    the text never displays an impossible zero."""
    if p < 0.001:
        return "p < .001"
    s = f"{p:.2f}"
    if s == "0.00":
        s = f"{p:.3f}"
    return f"p = {s[1:] if s.startswith('0.') else s}"


def _sig(p: float | None) -> bool:
    return p is not None and p < SIGNIFICANCE_ALPHA


def _num(v: float) -> str:
    """Compact numeric rendering for magnitudes: two decimals in the
    everyday range, significant-digit form for extremes."""
    a = abs(v)
    if a != 0 and (a < 0.01 or a >= 100000):
        return f"{v:.3g}"
    return f"{v:.2f}"


def _int_or_num(v) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else _num(f)


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


# ===================================================================
# Dispatcher
# ===================================================================

def interpret(kind: str, result: dict) -> list[str]:
    fn = _INTERPRETERS.get(kind)
    if fn is None:
        return []
    try:
        return fn(result)
    except Exception:  # noqa: BLE001
        # Interpretation is additive; a payload this module cannot read
        # must never take down an otherwise-successful result.
        return []


# ===================================================================
# One-way ANOVA (+ posthoc pairs)
# ===================================================================

def interpret_oneway(result: dict) -> list[str]:
    depvar = result.get("depvar", "the outcome")
    groupvar = result.get("groupvar", "group")
    k = result.get("k")
    F, p = result.get("F"), result.get("p")
    dfs = (result.get("anova_table") or {}).get("df") or [None, None]
    df_b, df_w = dfs[0], dfs[1]

    sentences: list[str] = []
    if F is None or p is None:
        sentences.append(
            f"The overall F test for {depvar} across {groupvar} groups could not be computed."
        )
    else:
        stat = f"F({df_b}, {df_w}) = {_num(F)}, {format_p(p)}"
        if _sig(p):
            sentences.append(
                f"Mean {depvar} differed significantly across the {k} {groupvar} groups ({stat})."
            )
        else:
            sentences.append(
                f"Mean {depvar} did not differ significantly across the {k} {groupvar} groups ({stat})."
            )

    block = result.get("posthoc_block")
    if block and isinstance(block.get("comparisons"), list):
        method = str(block.get("method", "")).capitalize()
        sentences.append(f"Pairwise comparisons were adjusted with the {method} correction.")

        n_not_sig = 0
        for cmp in block["comparisons"]:
            a, b = cmp.get("a"), cmp.get("b")
            p_adj = cmp.get("p_adj")
            diff = cmp.get("mean_diff")
            if p_adj is None:
                sentences.append(f"The {a} vs {b} comparison could not be computed.")
            elif _sig(p_adj):
                if diff is None:
                    sentences.append(
                        f"{a} and {b} differed significantly ({format_p(p_adj)}), "
                        "but the mean difference could not be computed."
                    )
                else:
                    # mean_diff is mean(a) − mean(b); its sign names the
                    # higher group. Direction is the one claim we must
                    # never get backwards.
                    higher, lower = (a, b) if diff > 0 else (b, a)
                    sentences.append(
                        f"{higher} showed significantly higher mean {depvar} than {lower} "
                        f"(mean difference {_num(abs(diff))}, {format_p(p_adj)})."
                    )
            else:
                n_not_sig += 1
        if n_not_sig:
            if n_not_sig == len(block["comparisons"]):
                sentences.append(
                    f"None of the {_plural(n_not_sig, 'pairwise comparison')} reached significance."
                )
            else:
                sentences.append(
                    f"The remaining {_plural(n_not_sig, 'pair')} showed no significant difference."
                )
    return sentences


# ===================================================================
# Two-way ANOVA
# ===================================================================

def interpret_anova_two(result: dict) -> list[str]:
    depvar = result.get("depvar", "the outcome")
    factor_a = result.get("factor_a", "factor A")
    factor_b = result.get("factor_b", "factor B")
    rows = {r.get("Source"): r for r in result.get("rows", [])}
    resid_df = (rows.get("Residual") or {}).get("df")

    def _stat(row: dict) -> str:
        return f"F({row.get('df')}, {resid_df}) = {_num(row['F'])}, {format_p(row['Prob_F'])}"

    sentences: list[str] = []
    for factor in (factor_a, factor_b):
        row = rows.get(factor)
        if row is None:
            continue
        if row.get("F") is None or row.get("Prob_F") is None:
            sentences.append(f"The main effect of {factor} could not be computed.")
        elif _sig(row["Prob_F"]):
            sentences.append(
                f"There was a significant main effect of {factor} on {depvar} ({_stat(row)})."
            )
        else:
            sentences.append(
                f"No significant main effect of {factor} on {depvar} was found ({_stat(row)})."
            )

    inter = rows.get(f"{factor_a} # {factor_b}")
    if inter is not None:
        if inter.get("F") is None or inter.get("Prob_F") is None:
            sentences.append(
                f"The {factor_a} × {factor_b} interaction could not be computed."
            )
        elif _sig(inter["Prob_F"]):
            sentences.append(
                f"The {factor_a} × {factor_b} interaction was significant ({_stat(inter)}) — "
                f"the effect of {factor_a} on {depvar} depended on the level of {factor_b}."
            )
        else:
            sentences.append(
                f"The {factor_a} × {factor_b} interaction was not significant ({_stat(inter)})."
            )
    return sentences


# ===================================================================
# Repeated-measures ANOVA
# ===================================================================

_CORRECTION_NAMES = {"gg": "Greenhouse-Geisser", "hf": "Huynh-Feldt"}


def interpret_anova_rm(result: dict) -> list[str]:
    depvar = result.get("depvar", "the outcome")
    within = result.get("within", "the within-subject factor")
    correction = result.get("correction", "none")

    row = next(
        (r for r in result.get("rows", []) if str(r.get("Source", "")).lower() == str(within).lower()),
        None,
    )
    sentences: list[str] = []
    if row is None or row.get("F") is None:
        sentences.append(f"The within-subject effect of {within} could not be computed.")
    else:
        suffix = ""
        p_used = row.get("p")
        if correction != "none" and row.get("p_adj") is not None:
            p_used = row["p_adj"]
            corr = _CORRECTION_NAMES.get(correction, correction)
            eps = row.get("epsilon")
            eps_txt = f", ε = {_num(eps)}" if eps is not None else ""
            suffix = f" after {corr} sphericity correction{eps_txt}"
        if p_used is None:
            sentences.append(f"The within-subject effect of {within} could not be computed.")
        else:
            stat = (f"F({_int_or_num(row.get('df_num'))}, {_int_or_num(row.get('df_den'))}) "
                    f"= {_num(row['F'])}, {format_p(p_used)}")
            if _sig(p_used):
                sentences.append(
                    f"The within-subject effect of {within} on {depvar} was significant "
                    f"({stat}{suffix})."
                )
            else:
                sentences.append(
                    f"The within-subject effect of {within} on {depvar} was not significant "
                    f"({stat}{suffix})."
                )

    between = result.get("between")
    summary = result.get("between_summary")
    if between and summary:
        F, p = summary.get("F"), summary.get("p")
        if F is None or p is None:
            sentences.append(f"The between-subjects effect of {between} could not be computed.")
        elif _sig(p):
            sentences.append(
                f"Subjects also differed significantly by {between} "
                f"(F = {_num(F)}, {format_p(p)}; computed from subject-level means)."
            )
        else:
            sentences.append(
                f"No significant between-subjects effect of {between} was found "
                f"(F = {_num(F)}, {format_p(p)}; computed from subject-level means)."
            )
    return sentences


# ===================================================================
# OLS regression
# ===================================================================

def interpret_regress(result: dict) -> list[str]:
    depvar = result.get("depvar", "the outcome")
    header = result.get("header") or {}
    F, p = header.get("F"), header.get("Prob_F")
    r2 = header.get("R2")

    sentences: list[str] = []
    r2_clause = ""
    if r2 is not None:
        pct = f"{r2 * 100:.1f}".removesuffix(".0")
        r2_clause = f" and explained {pct}% of the variance in {depvar} (R² = {_num(r2)})"
    if F is None or p is None:
        sentences.append("The overall model F test could not be computed.")
        if r2 is not None:
            sentences.append(f"The model explained R² = {_num(r2)} of the variance in {depvar}.")
    else:
        stat = f"F({header.get('df_m')}, {header.get('df_r')}) = {_num(F)}, {format_p(p)}"
        if _sig(p):
            sentences.append(f"The model was statistically significant ({stat}){r2_clause}.")
        else:
            sentences.append(
                f"The model was not statistically significant overall ({stat}){r2_clause}."
            )

    for row in result.get("coefficients", []):
        name = row.get("name")
        if name == "_cons":
            continue
        coef, coef_p = row.get("coef"), row.get("p")
        if coef is None or coef_p is None:
            sentences.append(f"The coefficient for {name} could not be computed.")
        elif _sig(coef_p):
            direction = "increase" if coef > 0 else "decrease"
            sentences.append(
                f"Each unit increase in {name} was associated with a "
                f"{_num(abs(coef))} {direction} in {depvar} ({format_p(coef_p)})."
            )
        else:
            sentences.append(
                f"{name} was not significantly associated with {depvar} ({format_p(coef_p)})."
            )
    return sentences


# ===================================================================
# Logistic regression
# ===================================================================

def interpret_logit(result: dict) -> list[str]:
    depvar = result.get("depvar", "the outcome")
    header = result.get("header") or {}
    chi2, p = header.get("LR_chi2"), header.get("Prob_chi2")
    pr2 = header.get("Pseudo_R2")
    odds_ratios = bool(header.get("odds_ratios"))

    sentences: list[str] = []
    pr2_clause = f"; pseudo R² = {_num(pr2)}" if pr2 is not None else ""
    if chi2 is None or p is None:
        sentences.append("The model likelihood-ratio test could not be computed.")
    else:
        stat = f"LR χ²({header.get('df_m')}) = {_num(chi2)}, {format_p(p)}{pr2_clause}"
        if _sig(p):
            sentences.append(f"The model was statistically significant ({stat}).")
        else:
            sentences.append(f"The model was not statistically significant overall ({stat}).")

    for row in result.get("coefficients", []):
        name = row.get("name")
        if name == "_cons":
            continue
        coef, coef_p = row.get("coef"), row.get("p")
        if coef is None or coef_p is None:
            sentences.append(f"The coefficient for {name} could not be computed.")
        elif not _sig(coef_p):
            sentences.append(
                f"{name} was not significantly associated with the odds of {depvar} "
                f"({format_p(coef_p)})."
            )
        elif odds_ratios:
            # `coef` IS the odds ratio in this payload (exp already
            # applied by the engine) — read it, never re-derive it.
            if coef > 1:
                sentences.append(
                    f"Each unit increase in {name} was associated with {_num(coef)}× "
                    f"higher odds of {depvar} ({format_p(coef_p)})."
                )
            else:
                sentences.append(
                    f"Each unit increase in {name} was associated with lower odds of "
                    f"{depvar} (odds ratio {_num(coef)}, {format_p(coef_p)})."
                )
        else:
            direction = "higher" if coef > 0 else "lower"
            sentences.append(
                f"Higher {name} was associated with {direction} odds of {depvar} "
                f"(coefficient {_num(coef)} on the log-odds scale, {format_p(coef_p)})."
            )
    return sentences


# ===================================================================
# Diagnostics
# ===================================================================

def interpret_shapiro(result: dict) -> list[str]:
    variable = result.get("variable", "the variable")
    by = result.get("by")

    sentences: list[str] = []
    for row in result.get("rows", []):
        label = f"{variable} ({by} = {row['group']})" if by and row.get("group") is not None \
            else variable
        W, p = row.get("W"), row.get("p")
        if W is None or p is None:
            note = row.get("note")
            note_txt = f" ({note})" if note else ""
            sentences.append(f"The normality test for {label} could not be computed{note_txt}.")
        elif _sig(p):
            sentences.append(
                f"{label} showed a significant departure from a normal distribution "
                f"(W = {_num(W)}, {format_p(p)})."
            )
        else:
            # A non-significant Shapiro-Wilk does not prove normality —
            # only that no departure was detected.
            sentences.append(
                f"No significant departure from normality was detected for {label} "
                f"(W = {_num(W)}, {format_p(p)})."
            )
    return sentences


def interpret_levene(result: dict) -> list[str]:
    groupvar = result.get("groupvar", "group")
    W, p = result.get("W"), result.get("p")
    if W is None or p is None:
        return ["The equal-variance test could not be computed."]
    stat = f"W = {_num(W)}, {format_p(p)}"
    if _sig(p):
        return [
            f"Variances differed significantly across {groupvar} groups ({stat}); "
            "consider methods that do not assume equal variances (e.g. a Welch-type test)."
        ]
    return [
        f"Variances did not differ significantly across {groupvar} groups ({stat}); "
        "the equal-variance assumption was not contradicted."
    ]


# ===================================================================
# Descriptives — factual only, no inferential language
# ===================================================================

def interpret_tabstat(result: dict) -> list[str]:
    variables = result.get("variables") or []
    by = result.get("by")
    matrix = result.get("matrix") or {}

    if by:
        groups = [g for g in (result.get("groups") or []) if g != "Total"]
        return [
            f"Descriptive statistics for {', '.join(variables)} "
            f"across {_plural(len(groups), f'{by} group')}."
        ]

    sentences: list[str] = []
    for v in variables:
        cells = matrix.get(v) or {}
        parts = []
        if isinstance(cells.get("n"), (int, float)):
            parts.append(f"n = {_int_or_num(cells['n'])}")
        if isinstance(cells.get("mean"), (int, float)):
            parts.append(f"mean = {_num(float(cells['mean']))}")
        if isinstance(cells.get("sd"), (int, float)):
            parts.append(f"sd = {_num(float(cells['sd']))}")
        if parts:
            sentences.append(f"{v}: " + ", ".join(parts) + ".")
    return sentences


_INTERPRETERS = {
    "oneway": interpret_oneway,
    "anova_two": interpret_anova_two,
    "anova_rm": interpret_anova_rm,
    "regress": interpret_regress,
    "logit": interpret_logit,
    "shapiro": interpret_shapiro,
    "levene": interpret_levene,
    "tabstat": interpret_tabstat,
}
