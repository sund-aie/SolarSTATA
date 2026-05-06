"""Stata-style factor-variable notation: parsing + design-matrix expansion.

Supported:

  c.var          continuous (default for numerics)
  i.var          categorical, drop the lowest level as reference
  x#y            pure interaction (no main effects)
  x##y           full factorial: main effects + interaction
  c.x##c.x       polynomial (continuous × itself = squared term)

Not supported in Phase 3:

  ibn.var        no-reference encoding
  o.var          omit
  i(2).var       custom reference level
  L.var          time-series lag operators

Coefficient names mirror Stata's display:

  i.sex          → "1.sex", "2.sex" (only "2.sex" emitted; "1.sex" is reference)
  i.sex#c.age    → "1.sex#c.age", "2.sex#c.age"
  c.age##c.age   → "age", "c.age#c.age"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Iterable

import numpy as np
import pandas as pd


# ===================================================================
# AST: parsed forms
# ===================================================================

@dataclass(frozen=True)
class Term:
    """A single design-matrix term — possibly an interaction.

    Example: `i.sex#c.age` parses to Term(parts=[Atom('sex','i'), Atom('age','c')]).
    A bare `age` parses to Term(parts=[Atom('age','c')]).
    """

    parts: tuple["Atom", ...]

    @property
    def is_constant(self) -> bool:
        return len(self.parts) == 0


@dataclass(frozen=True)
class Atom:
    var: str
    kind: str  # 'i' or 'c'


# ===================================================================
# Parser
# ===================================================================

def parse_indepvars(tokens: Iterable[str]) -> list[Term]:
    """Expand `[i./c.]var` and `##` / `#` interactions into a flat term list.

    Each input token may be:
      - `var`        → 1 Term: c.var (or i.var if dtype suggests categorical, see below)
      - `i.var`      → 1 Term
      - `c.var`      → 1 Term
      - `x##y`       → 3 Terms: x, y, x#y (full factorial)
      - `x#y`        → 1 Term: pure interaction
      - `x##y##z`    → 7 Terms (all subsets except the empty one)

    Returns Terms in input order, deduplicated.
    """
    seen: list[Term] = []
    for token in tokens:
        for term in _expand_token(token):
            if term not in seen:
                seen.append(term)
    return seen


def _expand_token(token: str) -> list[Term]:
    if "##" in token:
        # Full factorial of factors separated by ##
        factors = [_factor_atoms(p) for p in token.split("##")]
        flat = [a[0] for a in factors]  # each side must be a single atom for now
        terms: list[Term] = []
        # All non-empty subsets, in canonical order: singletons first, then pairs, etc.
        from itertools import combinations
        for k in range(1, len(flat) + 1):
            for combo in combinations(flat, k):
                terms.append(Term(parts=tuple(combo)))
        return terms
    if "#" in token:
        # Pure interaction
        atoms: list[Atom] = []
        for piece in token.split("#"):
            atoms.extend(_factor_atoms(piece))
        return [Term(parts=tuple(atoms))]
    return [Term(parts=tuple(_factor_atoms(token)))]


def _factor_atoms(piece: str) -> list[Atom]:
    """Single piece, e.g. 'i.sex' or 'c.age' or 'age'."""
    piece = piece.strip()
    if piece.startswith("i."):
        return [Atom(var=piece[2:], kind="i")]
    if piece.startswith("c."):
        return [Atom(var=piece[2:], kind="c")]
    return [Atom(var=piece, kind="c")]   # default to continuous


# ===================================================================
# Design matrix builder
# ===================================================================

@dataclass
class DesignMatrix:
    X: pd.DataFrame                 # final columns ready for statsmodels (incl. const if requested)
    column_names: list[str]         # column order matches X
    term_index: dict[str, list[str]]  # term spec → list of column names contributing
    reference_levels: dict[str, object]  # var → reference value, for i. terms
    omitted: list[str] = field(default_factory=list)


def build_design(
    df: pd.DataFrame,
    terms: list[Term],
    *,
    add_constant: bool = True,
) -> DesignMatrix:
    """Construct a design matrix from parsed factor terms.

    For each Term we emit one or more columns:

      c.x                     →  one numeric column "x"
      i.x   (k levels)        →  k-1 dummy columns "L.x" for non-reference levels L
      i.x#c.y                 →  k-1 columns "L.x#c.y" (level dummy * y)
      i.x#i.y  (k×m levels)   →  (k-1)*(m-1) cross dummies
      c.x#c.y                 →  one numeric column "c.x#c.y" (product of x and y)

    The reference level for `i.var` is the smallest sortable value present
    in the column.
    """
    columns: dict[str, np.ndarray] = {}
    term_index: dict[str, list[str]] = {}
    reference_levels: dict[str, object] = {}

    for term in terms:
        cols, refs = _materialize_term(df, term)
        spec = format_term(term)
        term_index[spec] = list(cols.keys())
        for k, v in cols.items():
            columns[k] = v
        for var, ref in refs.items():
            reference_levels.setdefault(var, ref)

    X = pd.DataFrame(columns, index=df.index)

    if add_constant:
        # Always last column so coefficient lists read "var1, var2, …, _cons"
        X["_cons"] = 1.0

    return DesignMatrix(
        X=X,
        column_names=list(X.columns),
        term_index=term_index,
        reference_levels=reference_levels,
    )


def _materialize_term(df: pd.DataFrame, term: Term) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    """Return {column_name: values} contributed by a Term, plus reference-level metadata."""
    if term.is_constant:
        return ({}, {})

    # Per-atom column lists: each atom becomes a list of (suffix, vector).
    atom_columns: list[list[tuple[str, np.ndarray]]] = []
    references: dict[str, object] = {}
    for atom in term.parts:
        if atom.var not in df.columns:
            raise KeyError(f"variable {atom.var!r} not found in dataset")
        s = df[atom.var]
        if atom.kind == "c":
            arr = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
            atom_columns.append([(_atom_label(atom), arr)])
        elif atom.kind == "i":
            cats = _sorted_unique(s)
            if not cats:
                atom_columns.append([])
                continue
            ref = cats[0]
            references[atom.var] = ref
            level_cols: list[tuple[str, np.ndarray]] = []
            for level in cats[1:]:
                col = (s == level).astype(float).to_numpy()
                # Stata-style coefficient name for a non-reference level
                level_cols.append((f"{_format_level(level)}.{atom.var}", col))
            atom_columns.append(level_cols)
        else:
            raise ValueError(f"unknown atom kind: {atom.kind}")

    if not atom_columns or any(len(a) == 0 for a in atom_columns):
        return ({}, references)

    # Cartesian product across atoms gives the full set of design columns.
    out: dict[str, np.ndarray] = {}
    for combo in product(*atom_columns):
        names = [c[0] for c in combo]
        vec = np.ones_like(combo[0][1])
        for _, v in combo:
            vec = vec * v
        col_name = "#".join(names)
        out[col_name] = vec

    return out, references


def _atom_label(atom: Atom) -> str:
    """Coefficient name for a single atom term (used inside interactions and as base)."""
    if atom.kind == "c":
        return atom.var          # bare for plain continuous
    return f"i.{atom.var}"


def format_term(term: Term) -> str:
    """Stata-style display name for a Term, used as a key in term_index."""
    if term.is_constant:
        return "_cons"
    return "#".join(_atom_token(a) for a in term.parts)


def _atom_token(atom: Atom) -> str:
    return f"i.{atom.var}" if atom.kind == "i" else f"c.{atom.var}"


def _sorted_unique(s: pd.Series) -> list[object]:
    """Sorted distinct non-null values. Stable for both numeric and string columns."""
    vals = s.dropna().unique().tolist()
    try:
        vals.sort()
    except TypeError:
        vals.sort(key=str)
    return vals


def _format_level(level: object) -> str:
    if isinstance(level, (int, np.integer)):
        return str(int(level))
    if isinstance(level, (float, np.floating)):
        f = float(level)
        return str(int(f)) if f.is_integer() else f"{f:g}"
    return str(level)
