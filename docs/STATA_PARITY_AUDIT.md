# Stata Parity & Statistical Rigor Audit
**Target:** v3.3 Backlog
**Auditors:** Qwen (Mathematical/Statistical Rigor), Claude (Product/Clinical Pragmatism)

This document captures the known statistical deviations and bugs identified during the v3.2 codebase audit. It is triaged by severity to guide the v3.3 development cycle. 

Our north star is not "1:1 numerical parity with Stata 19 at all costs," but rather "a Stata replica a clinician can trust." Some deviations are critical bugs that produce invalid results; others are convention differences or feature gaps.

---

## 🔴 Tier 1: Critical Bugs (Invalid Results)
*These produce mathematically incorrect results or silent data loss. Must fix.*

### 1. The Robust/Cluster F-Statistic is Invalid
* **File:** `backend/src/solarstata/engine/regress.py`
* **The Bug:** When `vce="robust"` or `vce="cluster"`, the header reports `model.fvalue`. In `statsmodels`, this is the standard homoskedastic OLS F-statistic based on the MSE. It ignores the robust covariance matrix.
* **Stata's Behavior:** Stata reports the Wald F-statistic testing the joint hypothesis that all slope coefficients are zero, using the robust VCE matrix.
* **The Fix:** Compute the Wald test manually for the header when `vce != "ols"`. Exclude the constant from the restriction matrix.

### 2. The Missing Value Semantic Trap (`.` vs `NaN`)
* **File:** `backend/src/solarstata/engine/qualifiers.py`
* **The Bug:** Stata treats `.` as positive infinity. Therefore, `keep if age > 60` **includes** missing values in Stata. In Pandas, `NaN > 60` evaluates to `False`, silently dropping them.
* **The Risk:** Silent data loss. A clinician migrating a workflow will get a different sample size and never know why.
* **The Fix:** Do not silently rewrite user filters. Instead, implement a pre-flight warning in the UI/CLI when an `if` condition contains `>` or `<` on a column with missing values, forcing the user to explicitly acknowledge the NaN handling (e.g., prompting them to add `& age < .`).

### 3. Shapiro-Wilk Random Subsampling (N > 5000)
* **File:** `backend/src/solarstata/engine/diagnostics.py`
* **The Bug:** To bypass `scipy.stats.shapiro`'s 5000-row limit, the engine randomly samples 5000 rows. This injects noise, breaks reproducibility, and is statistically invalid.
* **The Fix:** For N > 5000, abandon the Shapiro-Wilk test entirely. At massive N, normality tests reject on trivial deviations. Instead, automatically generate and return a **Q-Q plot** (via Plotly) and the D'Agostino-Pearson omnibus test (`scipy.stats.normaltest`) for skewness/kurtosis.

---

## 🟡 Tier 2: Verify & Fix (Empirical Check Required)
*These are theoretically sound critiques, but require empirical verification against real Stata before writing code.*

### 1. Cluster-Robust Small-Sample Correction
* **File:** `backend/src/solarstata/engine/regress.py`
* **The Claim:** Stata applies an additional finite-sample correction of `(N-1)/(N-k) * M/(M-1)` to cluster-robust SEs. `statsmodels` applies `M/(M-1)`, but its exact behavior depends on the version and `cov_kwds` (e.g., `use_correction`).
* **Action:** Run a dataset with 40 clusters through both SolarSTATA and Stata 19 using `vce(cluster id)`. Compare the SEs. If they diverge, manually scale `model.cov_params()` by the Stata correction factor.

### 2. RM-ANOVA Between-Subjects Error Term
* **File:** `backend/src/solarstata/engine/anova.py`
* **The Claim:** The "split-plot workaround" (running 1-way ANOVA on subject means) uses the wrong error term for the between-subjects effect in a mixed design.
* **Action:** This is mathematically fiddly and belongs in the broader "Mixed-Effects Models" v3.3 roadmap. Defer until implementing `statsmodels.formula.api.mixedlm`.

---

## 🔵 Tier 3: Convention & Feature Gaps
*Not "wrong," but deviations from Stata conventions or missing features. Address based on user demand.*

### 1. Two-Way ANOVA Sums of Squares
* **File:** `backend/src/solarstata/engine/anova.py`
* **Context:** SolarSTATA uses Type II SS (`anova_lm(model, typ=2)`). Stata defaults to Type III SS.
* **Action:** Change to `typ=3`. Ensure the design matrix uses sum-to-zero or treatment coding correctly, as Type III requires careful handling of the intercept to match Stata's exact SS partitioning.

### 2. Margins (AME) on Interactions
* **File:** `backend/src/solarstata/engine/postest.py`
* **Context:** Currently, AME for OLS just returns the raw coefficient. This is only correct for main effects. If a user runs `c.age##c.age`, the marginal effect depends on the data distribution.
* **Action:** Implement proper Jacobian averaging for OLS interactions, or restrict the `margins` command to main-effects-only models until v3.3.

### 3. Collinearity and Omitted Variables
* **Context:** Stata gracefully detects perfect multicollinearity, sets the coefficient to `0`, and tags it as `(omitted)`. `statsmodels.OLS` may throw a `Singular matrix` error or return `NaN`.
* **Action:** Implement a pre-flight rank check on the design matrix $X$ to mimic Stata's `omitted` behavior.

### 4. Tabulate Chi-Squared
* **Context:** The frontend advertises `tabulate x y, chi2`, but the backend only computes the crosstab matrix.
* **Action:** Implement the Pearson Chi-Squared statistic and p-value using `scipy.stats.chi2_contingency`.

---

## 🟢 Validated Strengths (Do Not Touch)
*Areas where the codebase correctly handles complex statistical nuances that replicas often botch.*

1. **Logit Odds Ratio CIs:** Exponentiating the log-odds CI bounds (`np.exp(lo)`) rather than using the delta-method SE to build symmetric CIs around the OR. Perfect.
2. **Wald Test Distributions:** Using the $t$-distribution for single-coefficient Wald tests in OLS, but the $F$-distribution for joint tests (and Chi2 for Logit). Perfect.
3. **Factor-Variable AST:** The parser and design-matrix expansion for `i.`, `c.`, `#`, and `##` is robust and production-ready.
