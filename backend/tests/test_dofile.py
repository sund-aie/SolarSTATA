"""Do-file parser + dispatcher."""

from __future__ import annotations

import pandas as pd
import pytest

from solarstata.engine.dofile import dispatch, parse_line
from solarstata.session.models import Frame, Session


# ---- parser ---------------------------------------------------------

def test_parse_simple_command() -> None:
    p = parse_line("summarize age weight")
    assert p is not None
    assert p.command == "summarize"
    assert p.args == ["age", "weight"]


def test_parse_with_if_qualifier() -> None:
    p = parse_line("regress y x1 x2 if age > 40")
    assert p.command == "regress"
    assert p.args == ["y", "x1", "x2"]
    assert p.if_expr == "age > 40"


def test_parse_with_in_qualifier() -> None:
    p = parse_line("summarize y in 1/100")
    assert p.in_range == "1/100"


def test_parse_with_options() -> None:
    p = parse_line("regress y x1 x2, vce(robust) noheader")
    assert p.options.get("vce") == "robust"
    assert p.options.get("noheader") is True


def test_parse_options_with_paren_args() -> None:
    p = parse_line("regress y x, vce(cluster id) level(95)")
    assert p.options.get("vce") == "cluster id"
    assert p.options.get("level") == "95"


def test_parse_by_prefix() -> None:
    p = parse_line("by sex: summarize age")
    assert p.prefix == "by"
    assert p.prefix_varlist == ["sex"]
    assert p.command == "summarize"


def test_parse_estat_subcommand() -> None:
    p = parse_line("estat ic")
    assert p.command == "estat"
    assert p.subcommand == "ic"


def test_parse_returns_none_on_blank() -> None:
    assert parse_line("") is None
    assert parse_line("   ") is None
    assert parse_line("// just a comment") is None


def test_parse_factor_variable_args() -> None:
    p = parse_line("regress y i.sex c.age##c.age")
    assert p.args == ["y", "i.sex", "c.age##c.age"]


def test_parse_logit_with_or() -> None:
    p = parse_line("logit y x1 x2, or vce(robust)")
    assert p.options.get("or") is True
    assert p.options.get("vce") == "robust"


# ---- dispatch -------------------------------------------------------

@pytest.fixture
def session_with_data() -> tuple[Session, Frame]:
    df = pd.DataFrame({
        "y":  [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "x1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        "x2": [1, 0, 1, 0, 1, 0],
    })
    frame = Frame(name="default", df=df)
    session = Session(session_id="test")
    session.set_frame(frame)
    return session, frame


def test_dispatch_summarize(session_with_data) -> None:
    session, frame = session_with_data
    parsed = parse_line("summarize y x1")
    out = dispatch(parsed, session, frame)
    assert len(out.blocks) == 1
    assert out.estimation is None


def test_dispatch_regress_stores_estimation(session_with_data) -> None:
    session, frame = session_with_data
    out = dispatch(parse_line("regress y x1"), session, frame)
    assert out.estimation is not None
    assert out.estimation.cmd_kind == "regress"


def test_dispatch_predict_after_regress(session_with_data) -> None:
    session, frame = session_with_data
    reg_out = dispatch(parse_line("regress y x1"), session, frame)
    session.last_estimation = reg_out.estimation
    pred_out = dispatch(parse_line("predict yhat"), session, frame)
    assert len(pred_out.dataset_mutations) == 1
    name, col = pred_out.dataset_mutations[0]
    assert name == "yhat"
    assert len(col) == len(frame.df)


def test_dispatch_regress_robust_via_options(session_with_data) -> None:
    session, frame = session_with_data
    out = dispatch(parse_line("regress y x1 x2, vce(robust)"), session, frame)
    assert out.estimation is not None
    assert out.blocks[0].structured["header"]["vce"] == "robust"


def test_dispatch_unknown_command(session_with_data) -> None:
    session, frame = session_with_data
    with pytest.raises(ValueError, match="not supported"):
        dispatch(parse_line("zzzzbogus y"), session, frame)
