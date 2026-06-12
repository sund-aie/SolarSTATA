"""Compact letter display — letters summarising pairwise comparisons.

Groups that share a letter are NOT significantly different; groups with
no letter in common ARE — at strict p < .05, the same alpha convention
as the significance brackets (graphs._stars_tier).

The input is the comparisons[] list a prior oneway's _pairwise already
produced. This module RENDERS that output into letters; it never
recomputes a statistic. A pair whose p_adj is None (not computable) is
treated as not significantly different and counted in n_missing so the
chart can surface the caveat instead of silently implying a result.

Algorithm: insert-and-absorb (Piepho 2004). Start with one column
holding every group; for each significant pair, split any column
containing both members into two (one without each member); then
absorb columns that became subsets of others. Letters are assigned to
columns ordered by their members' display positions, so output is
deterministic for a given comparisons list.
"""

from __future__ import annotations

SIGNIFICANCE_ALPHA = 0.05


def compact_letter_display(
    names: list[str],
    comparisons: list[dict],
    *,
    alpha: float = SIGNIFICANCE_ALPHA,
) -> tuple[dict[str, str], int]:
    """Assign compact letters to `names` from pairwise comparisons.

    `names` are the chart's group keys in display order (the same
    str(level) values _pairwise keys comparisons by). `comparisons`
    is the oneway posthoc_block's list of {a, b, p_adj, ...} dicts.

    Returns ({name: letters}, n_missing) where n_missing counts pairs
    between charted groups whose p_adj was None. Comparisons naming
    groups not present in `names` are ignored, mirroring how the
    bracket renderer skips them.
    """
    order = {name: i for i, name in enumerate(names)}

    sig_pairs: list[tuple[str, str]] = []
    n_missing = 0
    for cmp in comparisons:
        a, b = cmp.get("a"), cmp.get("b")
        if a not in order or b not in order or a == b:
            continue
        p_adj = cmp.get("p_adj")
        if p_adj is None:
            # Not computable — treated as not significantly different,
            # surfaced via n_missing rather than invented either way.
            n_missing += 1
            continue
        if float(p_adj) < alpha:
            sig_pairs.append((a, b))

    columns: list[set[str]] = [set(names)]
    for a, b in sig_pairs:
        split: list[set[str]] = []
        for col in columns:
            if a in col and b in col:
                split.append(col - {a})
                split.append(col - {b})
            else:
                split.append(col)
        columns = _absorb(split)

    # Deterministic letter order: columns sorted by their members'
    # display positions, so the leftmost group always reads "a…".
    columns.sort(key=lambda col: tuple(sorted(order[n] for n in col)))

    letters: dict[str, list[str]] = {name: [] for name in names}
    for idx, col in enumerate(columns):
        for name in col:
            letters[name].append(_letter(idx))
    return {name: "".join(ls) for name, ls in letters.items()}, n_missing


def _absorb(columns: list[set[str]]) -> list[set[str]]:
    """Drop empty columns, duplicates, and any column contained in another."""
    kept: list[set[str]] = []
    for col in columns:
        if not col:
            continue
        if any(col <= other for other in kept):
            continue
        kept = [other for other in kept if not other < col]
        kept.append(col)
    return kept


def _letter(i: int) -> str:
    """0 → a, 1 → b, …, 25 → z, 26 → aa (spreadsheet-column style)."""
    out = ""
    i += 1
    while i > 0:
        i, rem = divmod(i - 1, 26)
        out = chr(ord("a") + rem) + out
    return out
