"""Postestimation: predict, margins, test, lincom, estat ic, estat vif."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine import (
    estat_ic,
    estat_vif,
    lincom,
    logit,
    margins,
    predict,
    regress,
    wald_test,
)


@pytest.fixture(scope="module")
def lm_data() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    n = 300
    x1 = rng.normal(0, 1, size=n)
    x2 = rng.normal(0, 1, size=n)
    y = 1.0 + 2.0 * x1 - 0.5 * x2 + rng.normal(0, 0.3, size=n)
    return pd.DataFrame({"y": y, "x1": x1, "x2": x2})


@pytest.fixture(scope="module")
def logit_data() -> pd.DataFrame:
    rng = np.random.default_rng(13)
    n = 800
    x1 = rng.normal(0, 1, size=n)
    x2 = rng.normal(0, 1, size=n)
    p = 1 / (1 + np.exp(-(0.0 + 1.0 * x1 + 0.5 * x2)))
    y = (rng.uniform(0, 1, n) < p).astype(int)
    return pd.DataFrame({"y": y, "x1": x1, "x2": x2})


# predict -----------------------------------------------------------

def test_predict_xb_after_regress(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1", "x2"])
    result, col = predict(lm_data, est, kind="xb", new_var="yhat")
    assert result.structured["new_var"] == "yhat"
    # Predictions should correlate strongly with y (R² is high).
    assert col.corr(lm_data["y"]) > 0.9


def test_predict_resid_after_regress(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1", "x2"])
    _, resid = predict(lm_data, est, kind="resid", new_var="r")
    # Residuals should center near zero.
    assert abs(resid.mean(skipna=True)) < 0.05


def test_predict_pr_after_logit(logit_data: pd.DataFrame) -> None:
    _, est = logit(logit_data, "y", ["x1", "x2"])
    _, prob = predict(logit_data, est, kind="pr", new_var="phat")
    assert prob.min(skipna=True) >= 0.0
    assert prob.max(skipna=True) <= 1.0


def test_predict_kind_validation(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1"])
    with pytest.raises(ValueError):
        predict(lm_data, est, kind="pr", new_var="x")


def test_predict_without_estimation_raises() -> None:
    with pytest.raises(ValueError, match="no estimates"):
        predict(pd.DataFrame({"x": [1, 2]}), None, kind="xb", new_var="x")


# margins -----------------------------------------------------------

def test_margins_after_regress_matches_coefficients(lm_data: pd.DataFrame) -> None:
    result, est = regress(lm_data, "y", ["x1", "x2"])
    m = margins(lm_data, est)
    coefs = {r["name"]: r["coef"] for r in result.structured["coefficients"]}
    margins_dict = {r["name"]: r["dy_dx"] for r in m.structured["rows"]}
    for name in ("x1", "x2"):
        assert margins_dict[name] == pytest.approx(coefs[name], abs=1e-5)


def test_margins_after_logit(logit_data: pd.DataFrame) -> None:
    _, est = logit(logit_data, "y", ["x1", "x2"])
    m = margins(logit_data, est)
    rows = {r["name"]: r for r in m.structured["rows"]}
    # x1 should be larger AME than x2 (true coef 1.0 vs 0.5)
    assert abs(rows["x1"]["dy_dx"]) > abs(rows["x2"]["dy_dx"])


# test (Wald) -------------------------------------------------------

def test_wald_test_single_coef(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1", "x2"])
    r = wald_test(est, ["x1"])
    # x1 = 0 should be soundly rejected
    assert r.structured["p"] is not None and r.structured["p"] < 0.001


def test_wald_test_joint(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1", "x2"])
    r = wald_test(est, ["x1", "x2"])
    assert r.structured["p"] is not None and r.structured["p"] < 0.001


def test_wald_test_unknown_coefficient(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1"])
    with pytest.raises(ValueError, match="unknown"):
        wald_test(est, ["nope"])


# lincom ------------------------------------------------------------

def test_lincom_scaled_coef(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1"])
    result_lc = lincom(est, "2*x1")
    row = result_lc.structured["rows"][0]
    assert row["estimate"] is not None and row["estimate"] > 3.5  # ≈ 2 * 2.0


def test_lincom_sum_of_two(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1", "x2"])
    row = lincom(est, "x1 + x2").structured["rows"][0]
    # ≈ 2.0 + (-0.5) = 1.5
    assert row["estimate"] == pytest.approx(1.5, abs=0.15)


def test_lincom_unknown_var(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1"])
    with pytest.raises(ValueError, match="unknown coefficient"):
        lincom(est, "missing")


# estat ic / vif ----------------------------------------------------

def test_estat_ic_returns_aic_bic(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1", "x2"])
    rows = estat_ic(est).structured["rows"]
    assert rows[0]["AIC"] is not None
    assert rows[0]["BIC"] is not None


def test_estat_vif_for_each_predictor(lm_data: pd.DataFrame) -> None:
    _, est = regress(lm_data, "y", ["x1", "x2"])
    result_vif = estat_vif(lm_data, est)
    rows = result_vif.structured["rows"]
    names = {r["name"] for r in rows}
    assert names == {"x1", "x2"}  # _cons excluded
    # With independent draws, VIFs should be close to 1.
    for r in rows:
        assert 0.5 < r["vif"] < 3.0


def test_estat_vif_only_after_regress(logit_data: pd.DataFrame) -> None:
    _, est = logit(logit_data, "y", ["x1"])
    with pytest.raises(ValueError, match="only follows regress"):
        estat_vif(logit_data, est)
