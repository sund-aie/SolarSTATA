"""Logistic regression — coefficients and odds-ratio handling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine import logit
from solarstata.walkthroughs.datasets import CLINIC_PATIENTS_CSV


@pytest.fixture(scope="module")
def clinic() -> pd.DataFrame:
    return pd.read_csv(CLINIC_PATIENTS_CSV).query("patient_id < 9000").copy()


@pytest.fixture(scope="module")
def synthetic_binary() -> pd.DataFrame:
    """logit(p) = -1 + 1.5*x. Recovery should be close."""
    rng = np.random.default_rng(11)
    n = 1000
    x = rng.normal(0, 1, size=n)
    logodds = -1.0 + 1.5 * x
    p = 1 / (1 + np.exp(-logodds))
    y = (rng.uniform(0, 1, n) < p).astype(int)
    return pd.DataFrame({"y": y, "x": x})


def test_recovers_known_coefficients(synthetic_binary: pd.DataFrame) -> None:
    result, est = logit(synthetic_binary, "y", ["x"])
    coefs = {r["name"]: r["coef"] for r in result.structured["coefficients"]}
    assert coefs["x"] == pytest.approx(1.5, abs=0.25)
    assert est.cmd_kind == "logit"


def test_odds_ratios_exponentiates_coef(synthetic_binary: pd.DataFrame) -> None:
    plain, _    = logit(synthetic_binary, "y", ["x"])
    or_result, _ = logit(synthetic_binary, "y", ["x"], odds_ratios=True)
    plain_coef = next(r["coef"] for r in plain.structured["coefficients"] if r["name"] == "x")
    or_coef    = next(r["coef"] for r in or_result.structured["coefficients"] if r["name"] == "x")
    assert or_coef == pytest.approx(np.exp(plain_coef), rel=1e-4)


def test_rejects_non_binary_outcome(clinic: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="0/1 outcome"):
        logit(clinic, "age", ["smoking"])


def test_smoking_increases_caries_odds(clinic: pd.DataFrame) -> None:
    result, _ = logit(
        clinic,
        "caries",
        ["age", "smoking", "diabetes", "brushing_freq"],
        odds_ratios=True,
    )
    coefs = {r["name"]: r for r in result.structured["coefficients"]}
    smk = coefs["smoking"]
    # Spec'd correlation: smoking → +caries. OR > 1 with reasonable significance.
    assert smk["coef"] is not None and smk["coef"] > 1.5


def test_e_update_populated(synthetic_binary: pd.DataFrame) -> None:
    result, _ = logit(synthetic_binary, "y", ["x"])
    e = result.e_update or {}
    assert e["cmd"] == "logit"
    assert e["depvar"] == "y"
    assert e["N"] == len(synthetic_binary)


def test_logistic_command_when_or_used(synthetic_binary: pd.DataFrame) -> None:
    result, _ = logit(synthetic_binary, "y", ["x"], odds_ratios=True)
    assert result.command.startswith("logistic")
