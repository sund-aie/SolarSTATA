"""Stata-style ASCII renderers.

These produce the exact-looking tables Stata prints for `summarize` and
`tabulate`. Pro mode ships these strings to the Results pane verbatim;
Guided mode renders the structured payload as Tailwind cards instead.
"""

from __future__ import annotations

import math
from typing import Sequence

import pandas as pd


def _fnum(x: float | int | None, width: int = 10, prec: int = 6) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return f"{'.':>{width}}"
    if isinstance(x, int):
        return f"{x:>{width}d}"
    return f"{x:>{width}.{prec}g}"


def render_summarize(rows: list[dict], *, detail: bool) -> str:
    """Render a `summarize` table.

    Non-detail layout matches Stata exactly:

        Variable |     Obs        Mean    Std. dev.       Min        Max
        ---------+---------------------------------------------------------
            age  |     400    44.5025    14.39214         18         80
    """
    if not rows:
        return "no observations\n"

    if not detail:
        header = (
            f"{'Variable':>15} | {'Obs':>8} {'Mean':>11} {'Std. dev.':>11} "
            f"{'Min':>10} {'Max':>10}"
        )
        sep = "-" * 15 + "-+-" + "-" * 56
        body_lines = []
        for r in rows:
            obs = r.get("Obs", 0)
            body_lines.append(
                f"{r['Variable']:>15} | {obs:>8d} {_fnum(r.get('Mean'), 11)} "
                f"{_fnum(r.get('SD'), 11)} {_fnum(r.get('Min'), 10)} {_fnum(r.get('Max'), 10)}"
            )
        return "\n".join([header, sep, *body_lines])

    # detail layout — one block per variable
    blocks: list[str] = []
    for r in rows:
        blocks.append(_render_summarize_detail_block(r))
    return "\n\n".join(blocks)


def _render_summarize_detail_block(r: dict) -> str:
    name = r["Variable"]
    title = f"{name}\n" + "-" * 61
    header = (
        f"{'Percentiles':>20}  {'Smallest':>10}\n"
        f"{'1%':>6}  {_fnum(r.get('p1'), 12)}  {_fnum(r.get('Min'), 12)}\n"
        f"{'5%':>6}  {_fnum(r.get('p5'), 12)}\n"
        f"{'10%':>6}  {_fnum(r.get('p10'), 12)}      {'Obs':>8} {r.get('Obs', 0):>10d}\n"
        f"{'25%':>6}  {_fnum(r.get('p25'), 12)}      {'Sum of wgt.':>11} {r.get('Obs', 0):>7d}\n\n"
        f"{'50%':>6}  {_fnum(r.get('p50'), 12)}      {'Mean':>11} {_fnum(r.get('Mean'), 12)}\n"
        f"{'':>6}  {'':>12}      {'Std. dev.':>11} {_fnum(r.get('SD'), 12)}\n"
        f"{'75%':>6}  {_fnum(r.get('p75'), 12)}\n"
        f"{'90%':>6}  {_fnum(r.get('p90'), 12)}      {'Variance':>11} {_fnum(r.get('Variance'), 12)}\n"
        f"{'95%':>6}  {_fnum(r.get('p95'), 12)}      {'Skewness':>11} {_fnum(r.get('Skewness'), 12)}\n"
        f"{'99%':>6}  {_fnum(r.get('p99'), 12)}      {'Kurtosis':>11} {_fnum(r.get('Kurtosis'), 12)}\n"
    )
    return title + "\n" + header


def render_tabulate_oneway(var: str, table: pd.DataFrame) -> str:
    """One-way `tabulate var` output.

        education_lev~l |      Freq.     Percent        Cum.
        ----------------+-----------------------------------
                primary |         50       12.50       12.50
              secondary |        140       35.00       47.50
              ...
                  Total |        400      100.00
    """
    name = var
    label_w = max(len(name), max((len(str(v)) for v in table[var]), default=1), 5)
    header = f"{name:>{label_w}} | {'Freq.':>10} {'Percent':>10} {'Cum.':>10}"
    sep = "-" * label_w + "-+-" + "-" * 33
    body_lines = []
    cum = 0.0
    total_n = int(table["Freq."].sum())
    for _, row in table.iterrows():
        cum += float(row["Percent"])
        body_lines.append(
            f"{str(row[var]):>{label_w}} | {int(row['Freq.']):>10d} "
            f"{float(row['Percent']):>10.2f} {cum:>10.2f}"
        )
    total_line = f"{'Total':>{label_w}} | {total_n:>10d} {100.00:>10.2f}"
    return "\n".join([header, sep, *body_lines, sep, total_line])


# ===================================================================
# Regression table — Stata-style ASCII rendering
# ===================================================================

def render_regress_table(
    *,
    title: str,
    depvar: str,
    header: dict,
    coef_rows: list[dict],
) -> str:
    """Render the Stata `regress` ASCII output (header block + coef table)."""
    lines: list[str] = []

    n = header.get("N", "")
    df_m = header.get("df_m", "")
    df_r = header.get("df_r", "")
    F = header.get("F")
    p = header.get("Prob_F")
    r2 = header.get("R2")
    r2_a = header.get("R2_adj")
    rmse = header.get("RMSE")

    # Title block
    lines.append("")
    lines.append(f"      {title:<60}")
    lines.append("")
    lines.append(
        f"      Source |       SS           df       MS      "
        f"  Number of obs   = {_fnum(n, 9, 0)}"
    )
    lines.append(
        f"-------------+----------------------------------   F({df_m}, {df_r})"
        f"{' ':>9}= {_fnum(F, 9)}"
    )
    lines.append(
        f"      Model |                                       Prob > F"
        f"{' ':>11}= {_fnum(p, 9, 4)}"
    )
    lines.append(
        f"   Residual |                                       R-squared"
        f"{' ':>10}= {_fnum(r2, 9, 4)}"
    )
    lines.append(
        f"-------------+----------------------------------   Adj R-squared"
        f"{' ':>6}= {_fnum(r2_a, 9, 4)}"
    )
    lines.append(
        f"      Total |                                       Root MSE"
        f"{' ':>11}= {_fnum(rmse, 9)}"
    )
    lines.append("")

    # Coefficient table — column widths chosen to mirror Stata's default
    name_w = max(12, max((len(r["name"]) for r in coef_rows), default=12))
    sep = "-" * (name_w + 1) + "+" + "-" * 64
    head = (
        f"{depvar:>{name_w}} |{'Coefficient':>12} {'Std. err.':>10}{'t':>8}{'P>|t|':>9}"
        f"     [95% conf. interval]"
    )
    lines.append(sep)
    lines.append(head)
    lines.append(sep)
    for r in coef_rows:
        sig = "*" if r.get("significant") else " "
        lines.append(
            f"{r['name']:>{name_w}} |{_fnum(r['coef'], 12)} "
            f"{_fnum(r['se'], 10)} {_fnum(r['t'], 7, 2)} "
            f"{_fnum(r['p'], 8, 4)}{sig}{_fnum(r['ci_low'], 12)} "
            f"{_fnum(r['ci_high'], 11)}"
        )
    lines.append(sep)

    if header.get("vce") == "robust":
        lines.append("Robust standard errors (HC1)")
    elif header.get("vce") == "hc3":
        lines.append("Robust standard errors (HC3)")
    elif header.get("vce") == "cluster":
        lines.append(f"Standard errors clustered on {header.get('cluster')}")

    return "\n".join(lines)


def render_logit_table(
    *,
    title: str,
    depvar: str,
    header: dict,
    coef_rows: list[dict],
    odds_ratios: bool = False,
) -> str:
    """Render the Stata `logit` (or `logistic`) ASCII output."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"      {title:<60}")
    lines.append("")
    n = header.get("N", "")
    df_m = header.get("df_m", "")
    chi2 = header.get("LR_chi2")
    chi2_p = header.get("Prob_chi2")
    psr2 = header.get("Pseudo_R2")
    ll = header.get("log_likelihood")
    lines.append(f"      Number of obs   = {_fnum(n, 9, 0)}")
    lines.append(f"      LR chi2({df_m})       = {_fnum(chi2, 9)}")
    lines.append(f"      Prob > chi2     = {_fnum(chi2_p, 9, 4)}")
    lines.append(f"      Log likelihood  = {_fnum(ll, 12, 4)}    Pseudo R2 = {_fnum(psr2, 9, 4)}")
    lines.append("")

    coef_label = "Odds ratio" if odds_ratios else "Coefficient"
    name_w = max(12, max((len(r["name"]) for r in coef_rows), default=12))
    sep = "-" * (name_w + 1) + "+" + "-" * 64
    head = (
        f"{depvar:>{name_w}} |{coef_label:>12} {'Std. err.':>10}{'z':>8}{'P>|z|':>9}"
        f"     [95% conf. interval]"
    )
    lines.append(sep)
    lines.append(head)
    lines.append(sep)
    for r in coef_rows:
        sig = "*" if r.get("significant") else " "
        lines.append(
            f"{r['name']:>{name_w}} |{_fnum(r['coef'], 12)} "
            f"{_fnum(r['se'], 10)} {_fnum(r['z'], 7, 2)} "
            f"{_fnum(r['p'], 8, 4)}{sig}{_fnum(r['ci_low'], 12)} "
            f"{_fnum(r['ci_high'], 11)}"
        )
    lines.append(sep)

    if header.get("vce") == "robust":
        lines.append("Robust standard errors")
    elif header.get("vce") == "cluster":
        lines.append(f"Standard errors clustered on {header.get('cluster')}")
    return "\n".join(lines)


def render_tabulate_twoway(
    var1: str, var2: str, ct: pd.DataFrame, *, row_pct: bool = False
) -> str:
    """Two-way crosstab.

                    | var2
        var1        |  cat1   cat2   cat3 |   Total
        ------------+---------------------+--------
        catA        |    10     20     30 |      60
        ...
    """
    col_labels: Sequence = ct.columns.tolist()
    label_w = max(len(var1), max((len(str(i)) for i in ct.index), default=1), 5)
    cell_w = max(7, max((len(str(c)) for c in col_labels), default=5))

    head1 = " " * label_w + " | " + var2
    head2 = (
        f"{var1:>{label_w}} | "
        + " ".join(f"{str(c):>{cell_w}}" for c in col_labels)
    )
    sep = "-" * label_w + "-+-" + "-" * (len(col_labels) * (cell_w + 1))
    rows_out = []
    for idx, row in ct.iterrows():
        rows_out.append(
            f"{str(idx):>{label_w}} | "
            + " ".join(f"{int(v):>{cell_w}d}" if isinstance(v, (int, float)) else f"{str(v):>{cell_w}}" for v in row)
        )
    return "\n".join([head1, head2, sep, *rows_out])
