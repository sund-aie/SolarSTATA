"""Factor-variable parsing + design-matrix expansion."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine import build_design, parse_indepvars
from solarstata.engine.factor import Atom, Term, format_term


def test_parse_plain_continuous() -> None:
    [t] = parse_indepvars(["age"])
    assert t == Term((Atom("age", "c"),))


def test_parse_explicit_c_dot() -> None:
    [t] = parse_indepvars(["c.age"])
    assert t == Term((Atom("age", "c"),))


def test_parse_i_dot() -> None:
    [t] = parse_indepvars(["i.sex"])
    assert t == Term((Atom("sex", "i"),))


def test_parse_pure_interaction() -> None:
    [t] = parse_indepvars(["i.sex#c.age"])
    assert t == Term((Atom("sex", "i"), Atom("age", "c")))


def test_parse_full_factorial_two_factor() -> None:
    terms = parse_indepvars(["i.sex##c.age"])
    assert terms == [
        Term((Atom("sex", "i"),)),
        Term((Atom("age", "c"),)),
        Term((Atom("sex", "i"), Atom("age", "c"))),
    ]


def test_parse_multiple_tokens_dedupe() -> None:
    terms = parse_indepvars(["age", "i.sex", "age"])
    assert terms == [Term((Atom("age", "c"),)), Term((Atom("sex", "i"),))]


def test_format_term_round_trip() -> None:
    assert format_term(Term((Atom("age", "c"),))) == "c.age"
    assert format_term(Term((Atom("sex", "i"),))) == "i.sex"


def test_build_design_continuous_only() -> None:
    df = pd.DataFrame({"age": [20, 30, 40], "x": [1.0, 2.0, 3.0]})
    out = build_design(df, parse_indepvars(["age", "x"]))
    assert "age" in out.X.columns and "x" in out.X.columns
    assert "_cons" in out.X.columns
    assert (out.X["_cons"] == 1).all()


def test_build_design_factor_creates_dummies_and_drops_reference() -> None:
    df = pd.DataFrame({"sex": ["F", "M", "F", "M", "F"]})
    out = build_design(df, parse_indepvars(["i.sex"]))
    # F is alphabetically first → reference, M is the only dummy column.
    assert "M.sex" in out.X.columns
    assert "F.sex" not in out.X.columns
    assert out.reference_levels["sex"] == "F"
    np.testing.assert_array_equal(out.X["M.sex"].to_numpy(), [0, 1, 0, 1, 0])


def test_build_design_continuous_x_continuous_interaction() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]})
    out = build_design(df, parse_indepvars(["c.x##c.y"]))
    # x##y = x, y, x#y
    assert "x" in out.X.columns
    assert "y" in out.X.columns
    assert "x#y" in out.X.columns
    np.testing.assert_array_almost_equal(out.X["x#y"].to_numpy(), [4.0, 10.0, 18.0])


def test_build_design_factor_x_continuous() -> None:
    df = pd.DataFrame({"sex": ["F", "M", "F", "M"], "age": [20, 30, 40, 50]})
    out = build_design(df, parse_indepvars(["i.sex#c.age"]))
    # interaction columns are level dummies multiplied by age
    assert "M.sex#age" in out.X.columns
    np.testing.assert_array_equal(out.X["M.sex#age"].to_numpy(), [0, 30, 0, 50])


def test_build_design_unknown_variable_raises() -> None:
    df = pd.DataFrame({"x": [1, 2]})
    with pytest.raises(KeyError):
        build_design(df, parse_indepvars(["missing"]))
