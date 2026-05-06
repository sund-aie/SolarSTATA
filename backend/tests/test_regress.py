"""OLS regression — coefficient correctness vs known-good reference."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from solarstata.engine import regress
from solarstata.walkthroughs.datasets import CLINIC_PATIENTS_CSV


@pytest.fixture(scope="module")
def clinic() -> pd.DataFrame:
    df = pd.read_csv(CLINIC_PATIENTS_CSV)
    return df[df["patient_id"] < 9000].copy()


@pytest.fixture(scope="module")
def synthetic_lm() -> pd.DataFrame:
    """y = 2 + 3*x1 - 1.5*x2 + ε (small noise) gives recoverable coefficients."""
    rng = np.random.default_rng(7)
    n = 500
    x1 = rng.normal(0, 1, size=n)
    x2 = rng.normal(0, 1, size=n)
    y = 2.0 + 3.0 * x1 - 1.5 * x2 + rng.normal(0, 0.5, size=n)
    return pd.DataFrame({"y": y, "x1": x1, "x2": x2})


def test_recovers_known_coefficients(synthetic_lm: pd.DataFrame) -> None:
    result, est = regress(synthetic_lm, "y", ["x1", "x2"])
    coefs = {row["name"]: row["coef"] for row in result.structured["coefficients"]}
    assert coefs["_cons"] == pytest.approx(2.0, abs=0.1)
    assert coefs["x1"] == pytest.approx(3.0, abs=0.1)
    assert coefs["x2"] == pytest.approx(-1.5, abs=0.1)
    assert est.cmd_kind == "regress"
    assert est.n_obs == 500


def test_factor_variable_drops_reference(clinic: pd.DataFrame) -> None:
    result, est = regress(clinic, "plaque_index", ["i.sex", "brushing_freq"])
    names = [r["name"] for r in result.structured["coefficients"]]
    # Real-row sex levels are F and M only. F is reference → only "M.sex" appears.
    assert "M.sex" in names
    assert "F.sex" not in names


def test_brushing_freq_negative_significant(clinic: pd.DataFrame) -> None:
    """Spec'd correlation: more brushing → less plaque, large effect."""
    result, _ = regress(
        clinic, "plaque_index", ["age", "i.sex", "brushing_freq"], vce="robust"
    )
    coefs = {row["name"]: row for row in result.structured["coefficients"]}
    bf = coefs["brushing_freq"]
    assert bf["coef"] is not None and bf["coef"] < -0.3
    assert bf["p"] is not None and bf["p"] < 0.001
    assert bf["significant"] is True


def test_robust_se_changes_se_not_coef(synthetic_lm: pd.DataFrame) -> None:
    base_result, _ = regress(synthetic_lm, "y", ["x1", "x2"], vce="ols")
    rob_result, _  = regress(synthetic_lm, "y", ["x1", "x2"], vce="robust")
    base = {r["name"]: r for r in base_result.structured["coefficients"]}
    rob  = {r["name"]: r for r in rob_result.structured["coefficients"]}
    # Coefficients identical, SEs may differ
    for name in ("x1", "x2"):
        assert base[name]["coef"] == pytest.approx(rob[name]["coef"], abs=1e-6)


def test_cluster_se_requires_cluster_arg(synthetic_lm: pd.DataFrame) -> None:
    with pytest.raises(ValueError):
        regress(synthetic_lm, "y", ["x1"], vce="cluster")


def test_if_qualifier_filters_rows(clinic: pd.DataFrame) -> None:
    full, _ = regress(clinic, "plaque_index", ["age"])
    filtered, est = regress(clinic, "plaque_index", ["age"], if_expr="age > 40")
    assert est.n_obs < full.structured["header"]["N"]


def test_e_update_populated(synthetic_lm: pd.DataFrame) -> None:
    result, _ = regress(synthetic_lm, "y", ["x1", "x2"])
    assert result.e_update is not None
    assert result.e_update["cmd"] == "regress"
    assert result.e_update["depvar"] == "y"
    assert result.e_update["N"] == 500


def test_command_string_includes_options(synthetic_lm: pd.DataFrame) -> None:
    result, _ = regress(synthetic_lm, "y", ["x1"], vce="robust", if_expr="x1 > 0")
    assert "regress" in result.command
    assert "if x1 > 0" in result.command
    assert "vce(robust)" in result.command


def test_text_output_has_coefficient_block(synthetic_lm: pd.DataFrame) -> None:
    result, _ = regress(synthetic_lm, "y", ["x1"])
    text = result.text
    assert "Linear regression" in text
    assert "Coefficient" in text
    assert "Std. err." in text
