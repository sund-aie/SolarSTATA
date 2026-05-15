"""ANOVA family — one-way, two-way, repeated-measures.

Stata equivalents:
    oneway depvar groupvar [, bonferroni|scheffe|sidak]
    anova depvar factor_a##factor_b
    anova depvar subject##within##between, repeated(within)

One-way ANOVA always emits Bartlett's test for equal variances at the
bottom of the output (matches real Stata's default). Post-hoc pairwise
comparisons are optional and produced as a triangular matrix that
mirrors `oneway, bonferroni`'s console output.
"""

from __future__ import annotations

from itertools import combinations
from typing import Literal

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as sp
from statsmodels.formula.api import ols
from statsmodels.stats.anova import AnovaRM, anova_lm
from statsmodels.stats.multicomp import pairwise_tukeyhsd  # noqa: F401 — reserved for Tukey path

from .qualifiers import apply_if, apply_in
from .results import Result


PosthocKind = Literal["none", "bonferroni", "scheffe", "sidak"]


def _safe(v) -> float | None:
    if v is None:
        return None
    f = float(v)
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 6)


def _fmt(v, prec: int = 4) -> str:
    if v is None:
        return "."
    return f"{v:.{prec}f}"


# =====================================================================
# One-way ANOVA
# =====================================================================

def oneway(
    df: pd.DataFrame,
    depvar: str,
    groupvar: str,
    *,
    posthoc: PosthocKind = "none",
    if_expr: str | None = None,
    in_range: str | None = None,
) -> Result:
    if depvar not in df.columns:
        raise KeyError(f"variable {depvar!r} not in dataset")
    if groupvar not in df.columns:
        raise KeyError(f"variable {groupvar!r} not in dataset")

    sub = apply_in(apply_if(df, if_expr), in_range)
    sub = sub.dropna(subset=[depvar, groupvar])
    if sub.empty:
        raise ValueError("no observations remain after filtering")

    groups = list(sub[groupvar].dropna().unique())
    try:
        groups.sort()
    except TypeError:
        groups.sort(key=str)
    if len(groups) < 2:
        raise ValueError("oneway needs at least two groups")

    samples = []
    group_stats = []
    for g in groups:
        s = pd.to_numeric(sub.loc[sub[groupvar] == g, depvar], errors="coerce").dropna()
        if s.empty:
            continue
        samples.append(s.to_numpy())
        group_stats.append({
            "group": str(g),
            "n": int(len(s)),
            "mean": _safe(s.mean()),
            "sd": _safe(s.std(ddof=1)) if len(s) > 1 else None,
        })

    if len(samples) < 2:
        raise ValueError("oneway needs at least two non-empty groups")

    F, p = sp.f_oneway(*samples)
    n_total = int(sum(len(s) for s in samples))
    k = len(samples)
    grand_mean = float(np.concatenate(samples).mean())
    ss_between = float(sum(len(s) * (s.mean() - grand_mean) ** 2 for s in samples))
    ss_within = float(sum(((s - s.mean()) ** 2).sum() for s in samples))
    ss_total = ss_between + ss_within
    df_between = k - 1
    df_within = n_total - k
    ms_between = ss_between / df_between if df_between > 0 else None
    ms_within = ss_within / df_within if df_within > 0 else None

    anova_table = {
        "Source":   ["Between groups", "Within groups", "Total"],
        "SS":       [_safe(ss_between), _safe(ss_within), _safe(ss_total)],
        "df":       [df_between, df_within, n_total - 1],
        "MS":       [_safe(ms_between), _safe(ms_within), None],
        "F":        [_safe(F), None, None],
        "Prob_F":   [_safe(p), None, None],
    }

    # Bartlett's test, appended unconditionally — matches Stata default.
    try:
        bart_stat, bart_p = sp.bartlett(*samples)
        bartlett = {
            "chi2": _safe(bart_stat),
            "df": k - 1,
            "p": _safe(bart_p),
        }
    except ValueError:
        # bartlett fails when a group has zero variance — surface the
        # condition without crashing the whole run.
        bartlett = {"chi2": None, "df": k - 1, "p": None,
                    "note": "Bartlett's test undefined (a group has zero variance)"}

    # Posthoc pairwise comparisons.
    posthoc_block = None
    if posthoc != "none":
        posthoc_block = _pairwise(samples, [g["group"] for g in group_stats],
                                  method=posthoc, df_within=df_within,
                                  ms_within=ms_within)

    text = _render_oneway(depvar, groupvar, group_stats, anova_table,
                          bartlett, posthoc, posthoc_block)
    command_parts = ["oneway", depvar, groupvar]
    if if_expr:
        command_parts.append(f"if {if_expr}")
    if in_range:
        command_parts.append(f"in {in_range}")
    if posthoc != "none":
        command_parts.append(f", {posthoc}")
    command = " ".join(command_parts).replace(" ,", ",")

    structured = {
        "kind": "oneway",
        "depvar": depvar,
        "groupvar": groupvar,
        "n": n_total,
        "k": k,
        "F": _safe(F),
        "p": _safe(p),
        "group_stats": group_stats,
        "anova_table": anova_table,
        "bartlett": bartlett,
        "posthoc": posthoc,
        "posthoc_block": posthoc_block,
    }
    return Result(command=command, structured=structured, text=text)


def _pairwise(samples, names, *, method: str, df_within: int, ms_within: float | None) -> dict:
    """Pairwise comparisons of means with adjusted p-values.

    Returns:
      method, n_pairs, comparisons: [{a, b, mean_diff, se, t, p_raw, p_adj}],
      matrix: triangular dict of dicts keyed by group names.
    """
    n_groups = len(samples)
    n_pairs = n_groups * (n_groups - 1) // 2
    pooled_se = np.sqrt(ms_within) if ms_within and ms_within > 0 else None

    comparisons = []
    for i, j in combinations(range(n_groups), 2):
        a, b = samples[i], samples[j]
        mean_a, mean_b = float(a.mean()), float(b.mean())
        diff = mean_a - mean_b
        if pooled_se is not None and df_within > 0:
            se_diff = pooled_se * np.sqrt(1.0 / len(a) + 1.0 / len(b))
            t = diff / se_diff if se_diff > 0 else 0.0
            p_raw = float(2 * sp.t.sf(abs(t), df=df_within))
        else:
            se_diff = float("nan")
            t = float("nan")
            p_raw = float("nan")

        if method == "bonferroni":
            p_adj = min(p_raw * n_pairs, 1.0)
        elif method == "sidak":
            p_adj = 1.0 - (1.0 - p_raw) ** n_pairs
        elif method == "scheffe":
            # Scheffé: F_pair = t² / (k-1); compare to F(k-1, n-k)
            df_num = n_groups - 1
            f_pair = t * t / df_num if df_num > 0 else float("nan")
            p_adj = float(sp.f.sf(f_pair, df_num, df_within)) if df_num > 0 else float("nan")
        else:
            p_adj = p_raw

        comparisons.append({
            "a":         names[i],
            "b":         names[j],
            "mean_diff": _safe(diff),
            "se":        _safe(se_diff),
            "t":         _safe(t),
            "p_raw":     _safe(p_raw),
            "p_adj":     _safe(p_adj),
        })

    matrix: dict[str, dict[str, dict[str, float | None]]] = {}
    for r in comparisons:
        matrix.setdefault(r["a"], {})[r["b"]] = {
            "mean_diff": r["mean_diff"],
            "p_adj":     r["p_adj"],
        }
    return {
        "method": method,
        "n_pairs": n_pairs,
        "comparisons": comparisons,
        "matrix": matrix,
    }


def _render_oneway(depvar, groupvar, group_stats, table, bartlett,
                   posthoc, posthoc_block) -> str:
    lines = ["", f"                        Analysis of Variance — {depvar} by {groupvar}", ""]
    lines.append(f"    {'Source':<18} {'SS':>11} {'df':>6} {'MS':>11} {'F':>9} {'Prob>F':>10}")
    lines.append("    " + "-" * 70)
    for i in range(len(table["Source"])):
        line = (f"    {table['Source'][i]:<18} "
                f"{_fmt(table['SS'][i]):>11} "
                f"{table['df'][i]:>6} "
                f"{_fmt(table['MS'][i]) if table['MS'][i] is not None else '':>11} "
                f"{_fmt(table['F'][i]) if table['F'][i] is not None else '':>9} "
                f"{_fmt(table['Prob_F'][i]) if table['Prob_F'][i] is not None else '':>10}")
        lines.append(line)
    lines.append("")
    lines.append("    " + "-" * 70)
    lines.append(f"    {'group':>14} {'n':>6} {'mean':>12} {'sd':>12}")
    lines.append("    " + "-" * 70)
    for g in group_stats:
        lines.append(f"    {g['group']:>14} {g['n']:>6d} {_fmt(g.get('mean')):>12} {_fmt(g.get('sd')):>12}")
    lines.append("")

    # Bartlett — always present.
    lines.append(
        f"    Bartlett's test for equal variances: "
        f"chi2({bartlett['df']}) = {_fmt(bartlett.get('chi2'))}  "
        f"Prob > chi2 = {_fmt(bartlett.get('p'))}"
    )
    if bartlett.get("note"):
        lines.append(f"        {bartlett['note']}")

    if posthoc_block:
        lines.append("")
        lines.append(f"    Multiple comparisons of means — {posthoc.title()} method")
        lines.append("    " + "-" * 70)
        lines.append(f"    {'a':>14} {'b':>14} {'mean diff':>12} {'p (adj)':>10}")
        for c in posthoc_block["comparisons"]:
            lines.append(
                f"    {c['a']:>14} {c['b']:>14} "
                f"{_fmt(c['mean_diff']):>12} {_fmt(c['p_adj']):>10}"
            )
    return "\n".join(lines)


# =====================================================================
# Two-way ANOVA
# =====================================================================

def anova_two(
    df: pd.DataFrame,
    depvar: str,
    factor_a: str,
    factor_b: str,
    *,
    interaction: bool = True,
    if_expr: str | None = None,
    in_range: str | None = None,
) -> Result:
    for v in (depvar, factor_a, factor_b):
        if v not in df.columns:
            raise KeyError(f"variable {v!r} not in dataset")

    sub = apply_in(apply_if(df, if_expr), in_range)
    sub = sub.dropna(subset=[depvar, factor_a, factor_b])
    if sub.empty:
        raise ValueError("no observations remain after filtering")
    # statsmodels patsy can't handle spaces in column names cleanly; sanitize
    # by aliasing them. Real-world Stata users almost never have spaces but
    # let's be defensive.
    work = sub.rename(columns={depvar: "_y", factor_a: "_a", factor_b: "_b"})

    if interaction:
        formula = "_y ~ C(_a) + C(_b) + C(_a):C(_b)"
    else:
        formula = "_y ~ C(_a) + C(_b)"
    model = ols(formula, data=work).fit()
    table = anova_lm(model, typ=2)

    # Translate the patsy aliases back so the output reads naturally.
    label_map = {
        "C(_a)": factor_a,
        "C(_b)": factor_b,
        "C(_a):C(_b)": f"{factor_a} # {factor_b}",
        "Residual": "Residual",
    }
    rows = []
    for src in table.index:
        rows.append({
            "Source":   label_map.get(src, src),
            "SS":       _safe(table.loc[src, "sum_sq"]),
            "df":       int(table.loc[src, "df"]),
            "MS":       _safe(table.loc[src, "sum_sq"] / table.loc[src, "df"])
                          if table.loc[src, "df"] > 0 else None,
            "F":        _safe(table.loc[src, "F"]),
            "Prob_F":   _safe(table.loc[src, "PR(>F)"]),
        })

    text = _render_anova_table(f"Two-way ANOVA — {depvar} ~ {factor_a} × {factor_b}", rows)
    command = f"anova {depvar} {factor_a}{'##' if interaction else '+'}{factor_b}"
    if if_expr:
        command += f" if {if_expr}"
    if in_range:
        command += f" in {in_range}"

    structured = {
        "kind": "anova_two",
        "depvar": depvar,
        "factor_a": factor_a,
        "factor_b": factor_b,
        "interaction": interaction,
        "rows": rows,
        "r_squared": _safe(model.rsquared),
        "r_squared_adj": _safe(model.rsquared_adj),
        "n": int(model.nobs),
    }
    return Result(command=command, structured=structured, text=text)


# =====================================================================
# Repeated-measures ANOVA
# =====================================================================

def anova_rm(
    df: pd.DataFrame,
    depvar: str,
    subject: str,
    within: str,
    *,
    between: str | None = None,
    correction: Literal["none", "gg", "hf"] = "none",
    if_expr: str | None = None,
    in_range: str | None = None,
) -> Result:
    """Repeated-measures ANOVA via statsmodels.AnovaRM.

    One within-subjects factor + optional between-subjects factor.
    Sphericity corrections (Greenhouse-Geisser / Huynh-Feldt) are
    applied to the within-subject p-values; the F statistic itself
    is unchanged, only df and p are adjusted.
    """
    for v in (depvar, subject, within):
        if v not in df.columns:
            raise KeyError(f"variable {v!r} not in dataset")
    if between and between not in df.columns:
        raise KeyError(f"variable {between!r} not in dataset")

    sub = apply_in(apply_if(df, if_expr), in_range)
    cols = [depvar, subject, within] + ([between] if between else [])
    sub = sub.dropna(subset=cols).copy()
    if sub.empty:
        raise ValueError("no observations remain after filtering")

    # statsmodels expects each subject to have one row per within-level.
    # Sanitize types so groupby doesn't choke on mixed dtypes.
    sub[subject] = sub[subject].astype(str)
    sub[within] = sub[within].astype(str)
    if between:
        sub[between] = sub[between].astype(str)

    within_factors = [within]

    try:
        # statsmodels' AnovaRM currently refuses any between= argument with
        # "Between subject effect not yet supported!". We honour that and
        # always fit within-only here; the between factor (if any) is
        # surfaced as a separate one-way ANOVA on subject-level means so
        # the user still gets the between-group inference without us
        # silently lying about partitioning the error term.
        model = AnovaRM(
            data=sub,
            depvar=depvar,
            subject=subject,
            within=within_factors,
        ).fit()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Repeated-measures fit failed: {exc}")

    between_summary = None
    if between:
        # Subject-level means → one-way ANOVA across between-levels.
        # This is the standard split-plot workaround when the package
        # doesn't expose a full mixed-design fit.
        subject_means = sub.groupby([subject, between], as_index=False)[depvar].mean()
        try:
            from .anova import oneway as _oneway  # type: ignore[unused-ignore]  # late bind
            between_result = _oneway(subject_means, depvar, between)
            between_summary = {
                "F": between_result.structured.get("F"),
                "p": between_result.structured.get("p"),
                "k": between_result.structured.get("k"),
                "n_subjects": int(subject_means.shape[0]),
            }
        except Exception:  # noqa: BLE001 — don't let the workaround crash the main fit
            between_summary = None

    summary = model.anova_table
    rows = []
    for src in summary.index:
        F = summary.loc[src, "F Value"]
        p = summary.loc[src, "Pr > F"]
        num_df = summary.loc[src, "Num DF"]
        den_df = summary.loc[src, "Den DF"]
        if correction != "none":
            # Greenhouse-Geisser / Huynh-Feldt correction estimate.
            # Without per-source epsilon from statsmodels, use a
            # conservative GG-style adjustment (the lower-bound epsilon).
            # This errs on the side of larger p-values.
            eps = _sphericity_epsilon(sub, depvar, subject, within, kind=correction) \
                if src.lower().find(within.lower()) >= 0 else 1.0
            adj_num = num_df * eps
            adj_den = den_df * eps
            adj_p = float(sp.f.sf(F, max(1e-6, adj_num), max(1e-6, adj_den)))
        else:
            adj_p = float(p)
            eps = 1.0

        rows.append({
            "Source":    str(src),
            "F":         _safe(F),
            "df_num":    _safe(num_df),
            "df_den":    _safe(den_df),
            "p":         _safe(p),
            "epsilon":   _safe(eps) if correction != "none" else None,
            "p_adj":     _safe(adj_p) if correction != "none" else None,
        })

    title = f"Repeated-measures ANOVA — {depvar} within {within}"
    if between:
        title += f", between {between}"
    text = _render_rm(title, rows, correction, between=between, between_summary=between_summary)
    command_pieces = ["anova", depvar]
    factor_chain = [subject, within] + ([between] if between else [])
    command_pieces.append("##".join(factor_chain))
    command_pieces.append(f", repeated({within})")
    if correction != "none":
        command_pieces.append(f"{correction}")
    command = " ".join(command_pieces).replace(" ,", ",")

    structured = {
        "kind": "anova_rm",
        "depvar": depvar,
        "subject": subject,
        "within": within,
        "between": between,
        "between_summary": between_summary,
        "correction": correction,
        "rows": rows,
        "n_subjects": int(sub[subject].nunique()),
        "n_obs": int(len(sub)),
    }
    return Result(command=command, structured=structured, text=text)


def _sphericity_epsilon(df: pd.DataFrame, depvar: str, subject: str,
                       within: str, *, kind: str) -> float:
    """Compute Greenhouse-Geisser / Huynh-Feldt sphericity epsilon.

    Reshapes to wide (subjects × within levels), computes the
    covariance matrix of the differences, and applies the standard
    Box correction estimate. Falls back to 1.0 (no correction) if
    the shape isn't well-conditioned.
    """
    try:
        wide = df.pivot_table(index=subject, columns=within, values=depvar, aggfunc="mean")
        wide = wide.dropna(how="any")
        if wide.shape[1] < 2 or wide.shape[0] < 2:
            return 1.0
        cov = wide.cov().to_numpy()
        k = cov.shape[0]
        diag_mean = np.trace(cov) / k
        cov_mean = cov.mean()
        gg_num = k ** 2 * (diag_mean - cov_mean) ** 2
        gg_den = (k - 1) * (np.sum(cov ** 2) - 2 * k * np.sum(cov.mean(axis=0) ** 2)
                            + k ** 2 * cov_mean ** 2)
        eps_gg = gg_num / gg_den if gg_den > 0 else 1.0
        eps_gg = float(np.clip(eps_gg, 1 / (k - 1), 1.0))
        if kind == "gg":
            return eps_gg
        if kind == "hf":
            n = wide.shape[0]
            eps_hf = (n * (k - 1) * eps_gg - 2) / ((k - 1) * (n - 1 - (k - 1) * eps_gg))
            return float(np.clip(eps_hf, eps_gg, 1.0))
    except Exception:  # noqa: BLE001
        return 1.0
    return 1.0


def _render_rm(title: str, rows: list[dict], correction: str, *,
               between: str | None = None,
               between_summary: dict | None = None) -> str:
    lines = ["", "  " + title, ""]
    lines.append(f"  {'Source':<25} {'F':>10} {'df_num':>8} {'df_den':>8} {'p':>10}"
                 + (f" {'eps':>6} {'p (adj)':>10}" if correction != "none" else ""))
    lines.append("  " + "-" * 75)
    for r in rows:
        base = (f"  {r['Source']:<25} "
                f"{_fmt(r['F']):>10} "
                f"{_fmt(r['df_num']):>8} "
                f"{_fmt(r['df_den']):>8} "
                f"{_fmt(r['p']):>10}")
        if correction != "none":
            base += f" {_fmt(r['epsilon']):>6} {_fmt(r['p_adj']):>10}"
        lines.append(base)
    if correction != "none":
        lines.append("")
        lines.append(f"  Sphericity correction: {correction.upper()}")
    if between and between_summary:
        lines.append("")
        lines.append(f"  Between-subjects effect ({between})")
        lines.append(f"    Computed from subject-level means (split-plot workaround):")
        lines.append(f"    F = {_fmt(between_summary.get('F'))}  "
                     f"p = {_fmt(between_summary.get('p'))}  "
                     f"k = {between_summary.get('k')}")
        lines.append("    Note: a proper mixed-effects between×within fit lands in v3.1.")
    return "\n".join(lines)


# =====================================================================
# Shared table renderer (two-way)
# =====================================================================

def _render_anova_table(title: str, rows: list[dict]) -> str:
    lines = ["", "    " + title, ""]
    lines.append(f"    {'Source':<22} {'SS':>11} {'df':>6} {'MS':>11} {'F':>9} {'Prob>F':>10}")
    lines.append("    " + "-" * 70)
    for r in rows:
        lines.append(
            f"    {r['Source']:<22} {_fmt(r['SS']):>11} "
            f"{r['df']:>6d} {_fmt(r['MS']):>11} "
            f"{_fmt(r['F']):>9} {_fmt(r['Prob_F']):>10}"
        )
    return "\n".join(lines)


# Suppress import warning — sm is imported for future LME / GLS work and
# keeps the heavy statsmodels surface warm in the bytecode cache.
_ = sm
