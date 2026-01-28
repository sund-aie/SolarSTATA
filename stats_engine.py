"""
SolarSTATA Statistical Engine
Replicates Stata 19 core statistical functions with Python.
Covers: Descriptive Stats, T-tests, ANOVA, Regression, GLM,
        Chi-Square, Power Analysis, Survival Analysis, Non-parametric tests.
"""

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from scipy.special import comb
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.diagnostic import het_breuschpagan, het_white
from statsmodels.stats.stattools import durbin_watson
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import warnings
import re

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# 1. DESCRIPTIVE STATISTICS  (Stata: summarize, tabstat, detail)
# ---------------------------------------------------------------------------

def descriptive_stats(df, variables=None, detail=False):
    """Stata-style summarize command."""
    if variables is None:
        variables = df.select_dtypes(include=[np.number]).columns.tolist()

    results = []
    for var in variables:
        col = pd.to_numeric(df[var], errors="coerce").dropna()
        if col.empty:
            continue
        n = len(col)
        mean = col.mean()
        std = col.std(ddof=1)
        minimum = col.min()
        maximum = col.max()
        row = {
            "Variable": var, "Obs": n, "Mean": mean,
            "Std. Dev.": std, "Min": minimum, "Max": maximum,
        }
        if detail:
            row.update({
                "Variance": col.var(ddof=1),
                "Skewness": sp_stats.skew(col, bias=False),
                "Kurtosis": sp_stats.kurtosis(col, bias=False, fisher=False),
                "p1": np.percentile(col, 1),
                "p5": np.percentile(col, 5),
                "p10": np.percentile(col, 10),
                "p25": np.percentile(col, 25),
                "p50": np.percentile(col, 50),
                "p75": np.percentile(col, 75),
                "p90": np.percentile(col, 90),
                "p95": np.percentile(col, 95),
                "p99": np.percentile(col, 99),
                "Sum of Wgt.": n,
            })
        results.append(row)
    return pd.DataFrame(results)


def tabulate(df, var1, var2=None):
    """Stata-style tabulate command with optional cross-tab."""
    if var2 is None:
        freq = df[var1].value_counts().sort_index()
        total = freq.sum()
        tab = pd.DataFrame({
            var1: freq.index,
            "Freq.": freq.values,
            "Percent": (freq.values / total * 100).round(2),
            "Cum.": (freq.values.cumsum() / total * 100).round(2),
        })
        return tab
    else:
        return pd.crosstab(df[var1], df[var2], margins=True, margins_name="Total")


def normality_test(df, variable):
    """Stata-style sktest (D'Agostino-Pearson omnibus)."""
    col = pd.to_numeric(df[variable], errors="coerce").dropna()
    stat_sk, p_sk = sp_stats.skewtest(col)
    stat_ku, p_ku = sp_stats.kurtosistest(col)
    chi2 = stat_sk**2 + stat_ku**2
    p_combined = 1 - sp_stats.chi2.cdf(chi2, df=2)
    stat_sw, p_sw = sp_stats.shapiro(col) if len(col) <= 5000 else (np.nan, np.nan)
    return {
        "Variable": variable, "Obs": len(col),
        "Skewness_z": round(stat_sk, 4), "Skewness_p": round(p_sk, 4),
        "Kurtosis_z": round(stat_ku, 4), "Kurtosis_p": round(p_ku, 4),
        "chi2(2)": round(chi2, 4), "Prob>chi2": round(p_combined, 4),
        "Shapiro-Wilk_W": round(stat_sw, 4) if not np.isnan(stat_sw) else "N/A",
        "Shapiro-Wilk_p": round(p_sw, 4) if not np.isnan(p_sw) else "N/A",
    }


# ---------------------------------------------------------------------------
# 2. T-TESTS  (Stata: ttest)
# ---------------------------------------------------------------------------

def ttest_one_sample(df, variable, mu=0):
    """One-sample t-test."""
    col = pd.to_numeric(df[variable], errors="coerce").dropna()
    t_stat, p_val = sp_stats.ttest_1samp(col, mu)
    ci = sp_stats.t.interval(0.95, df=len(col)-1, loc=col.mean(), scale=sp_stats.sem(col))
    return {
        "Variable": variable, "Obs": len(col), "Mean": round(col.mean(), 6),
        "Std. Err.": round(sp_stats.sem(col), 6),
        "Std. Dev.": round(col.std(ddof=1), 6),
        "[95% Conf. Interval]": f"[{ci[0]:.6f}, {ci[1]:.6f}]",
        "t": round(t_stat, 4), "df": len(col)-1,
        "Ha: mean != {mu}": round(p_val, 4),
        "Ha: mean < {mu}": round(p_val/2, 4) if t_stat < 0 else round(1-p_val/2, 4),
        "Ha: mean > {mu}": round(p_val/2, 4) if t_stat > 0 else round(1-p_val/2, 4),
        "mu_0": mu,
    }


def ttest_two_sample(df, variable, groupvar, equal_var=True):
    """Two-sample t-test (Stata: ttest var, by(group))."""
    groups = df[groupvar].dropna().unique()
    if len(groups) != 2:
        return {"error": f"Need exactly 2 groups, found {len(groups)}: {list(groups)}"}

    g1 = pd.to_numeric(df.loc[df[groupvar] == groups[0], variable], errors="coerce").dropna()
    g2 = pd.to_numeric(df.loc[df[groupvar] == groups[1], variable], errors="coerce").dropna()

    t_stat, p_val = sp_stats.ttest_ind(g1, g2, equal_var=equal_var)
    t_welch, p_welch = sp_stats.ttest_ind(g1, g2, equal_var=False)

    n1, n2 = len(g1), len(g2)
    m1, m2 = g1.mean(), g2.mean()
    s1, s2 = g1.std(ddof=1), g2.std(ddof=1)
    se1, se2 = sp_stats.sem(g1), sp_stats.sem(g2)
    diff = m1 - m2

    if equal_var:
        sp2 = ((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2)
        se_diff = np.sqrt(sp2 * (1/n1 + 1/n2))
        dof = n1 + n2 - 2
    else:
        se_diff = np.sqrt(se1**2 + se2**2)
        dof = (se1**2 + se2**2)**2 / (se1**4/(n1-1) + se2**4/(n2-1))

    ci = sp_stats.t.interval(0.95, df=dof, loc=diff, scale=se_diff)

    return {
        "Group_1": str(groups[0]), "n1": n1, "mean1": round(m1, 6), "se1": round(se1, 6),
        "Group_2": str(groups[1]), "n2": n2, "mean2": round(m2, 6), "se2": round(se2, 6),
        "combined_n": n1+n2, "combined_mean": round((m1*n1+m2*n2)/(n1+n2), 6),
        "diff": round(diff, 6), "Std. Err.": round(se_diff, 6),
        "[95% Conf. Interval]": f"[{ci[0]:.6f}, {ci[1]:.6f}]",
        "t_equal_var": round(t_stat, 4), "p_equal_var": round(p_val, 4),
        "t_welch": round(t_welch, 4), "p_welch": round(p_welch, 4),
        "df_equal": n1+n2-2, "df_satterthwaite": round(dof, 2),
    }


def ttest_paired(df, var1, var2):
    """Paired t-test."""
    c1 = pd.to_numeric(df[var1], errors="coerce")
    c2 = pd.to_numeric(df[var2], errors="coerce")
    valid = c1.notna() & c2.notna()
    c1, c2 = c1[valid], c2[valid]
    diff = c1 - c2
    t_stat, p_val = sp_stats.ttest_rel(c1, c2)
    ci = sp_stats.t.interval(0.95, df=len(diff)-1, loc=diff.mean(), scale=sp_stats.sem(diff))
    return {
        "Variable_1": var1, "Variable_2": var2, "Obs": len(diff),
        "Mean(diff)": round(diff.mean(), 6),
        "Std. Err.": round(sp_stats.sem(diff), 6),
        "Std. Dev.": round(diff.std(ddof=1), 6),
        "[95% Conf. Interval]": f"[{ci[0]:.6f}, {ci[1]:.6f}]",
        "t": round(t_stat, 4), "df": len(diff)-1,
        "Ha: mean(diff) != 0": round(p_val, 4),
    }


# ---------------------------------------------------------------------------
# 3. ANOVA  (Stata: oneway, anova)
# ---------------------------------------------------------------------------

def oneway_anova(df, depvar, groupvar):
    """One-way ANOVA (Stata: oneway depvar groupvar)."""
    groups = []
    group_names = []
    for name, grp in df.groupby(groupvar):
        vals = pd.to_numeric(grp[depvar], errors="coerce").dropna()
        if len(vals) > 0:
            groups.append(vals.values)
            group_names.append(str(name))

    if len(groups) < 2:
        return {"error": "Need at least 2 groups with data"}

    f_stat, p_val = sp_stats.f_oneway(*groups)

    all_vals = np.concatenate(groups)
    grand_mean = all_vals.mean()
    N = len(all_vals)
    k = len(groups)

    ss_between = sum(len(g) * (g.mean() - grand_mean)**2 for g in groups)
    ss_within = sum(((g - g.mean())**2).sum() for g in groups)
    ss_total = ((all_vals - grand_mean)**2).sum()

    df_between = k - 1
    df_within = N - k
    df_total = N - 1
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within

    # Bartlett's test for equal variances
    bart_stat, bart_p = sp_stats.bartlett(*groups)
    # Levene's test
    lev_stat, lev_p = sp_stats.levene(*groups)

    # Group summaries
    group_stats = []
    for i, g in enumerate(groups):
        group_stats.append({
            "Group": group_names[i], "N": len(g),
            "Mean": round(g.mean(), 6), "Std. Dev.": round(g.std(ddof=1), 6),
        })

    return {
        "anova_table": {
            "Source": ["Between groups", "Within groups", "Total"],
            "SS": [round(ss_between, 4), round(ss_within, 4), round(ss_total, 4)],
            "df": [df_between, df_within, df_total],
            "MS": [round(ms_between, 4), round(ms_within, 4), ""],
            "F": [round(f_stat, 4), "", ""],
            "Prob > F": [round(p_val, 4), "", ""],
        },
        "group_stats": group_stats,
        "bartlett": {"chi2": round(bart_stat, 4), "p": round(bart_p, 4)},
        "levene": {"F": round(lev_stat, 4), "p": round(lev_p, 4)},
        "F": round(f_stat, 4), "Prob > F": round(p_val, 4),
    }


def twoway_anova(df, depvar, factor1, factor2, interaction=True):
    """Two-way ANOVA."""
    temp = df[[depvar, factor1, factor2]].dropna().copy()
    temp[depvar] = pd.to_numeric(temp[depvar], errors="coerce")
    temp = temp.dropna()

    if interaction:
        formula = f"{depvar} ~ C({factor1}) * C({factor2})"
    else:
        formula = f"{depvar} ~ C({factor1}) + C({factor2})"

    model = ols(formula, data=temp).fit()
    aov = anova_lm(model, typ=2)

    return {
        "anova_table": aov.to_dict(),
        "anova_table_str": aov.to_string(),
        "r_squared": round(model.rsquared, 4),
        "adj_r_squared": round(model.rsquared_adj, 4),
        "model_summary": model.summary().as_text(),
    }




# ---------------------------------------------------------------------------
# 4. CHI-SQUARE TESTS  (Stata: tabulate var1 var2, chi2)
# ---------------------------------------------------------------------------

def chi_square_test(df, var1, var2):
    """Chi-square test of independence."""
    ct = pd.crosstab(df[var1], df[var2])
    chi2, p, dof, expected = sp_stats.chi2_contingency(ct)

    # Cramér's V
    n = ct.sum().sum()
    k = min(ct.shape) - 1
    cramers_v = np.sqrt(chi2 / (n * k)) if k > 0 else 0

    return {
        "observed": ct.to_dict(),
        "expected": pd.DataFrame(expected, index=ct.index, columns=ct.columns).round(2).to_dict(),
        "chi2": round(chi2, 4),
        "df": dof,
        "Pr": round(p, 4),
        "cramers_v": round(cramers_v, 4),
        "n": int(n),
        "observed_str": ct.to_string(),
        "expected_str": pd.DataFrame(
            np.round(expected, 2), index=ct.index, columns=ct.columns
        ).to_string(),
    }


def chi_square_goodness_of_fit(df, variable, expected_freq=None):
    """Goodness-of-fit chi-square test."""
    observed = df[variable].value_counts().sort_index()
    if expected_freq is None:
        expected_freq = np.full(len(observed), observed.sum() / len(observed))
    chi2, p = sp_stats.chisquare(observed.values, f_exp=expected_freq)
    return {
        "chi2": round(chi2, 4), "df": len(observed) - 1,
        "Pr": round(p, 4), "observed": observed.to_dict(),
    }


# ---------------------------------------------------------------------------
# 5. LINEAR REGRESSION  (Stata: regress)
# ---------------------------------------------------------------------------

def linear_regression(df, depvar, indepvars, robust=False):
    """OLS regression (Stata: regress y x1 x2 ..., [vce(robust)])."""
    cols = [depvar] + indepvars
    temp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if temp.empty or len(temp) < len(indepvars) + 2:
        return {"error": "Insufficient observations after dropping missing values"}

    y = temp[depvar]
    X = sm.add_constant(temp[indepvars])

    if robust:
        model = sm.OLS(y, X).fit(cov_type="HC1")
    else:
        model = sm.OLS(y, X).fit()

    # VIF
    vif_data = []
    for i, col in enumerate(X.columns):
        if col == "const":
            continue
        vif_val = variance_inflation_factor(X.values, i)
        vif_data.append({"Variable": col, "VIF": round(vif_val, 2)})

    # Diagnostics
    residuals = model.resid
    dw = durbin_watson(residuals)

    return {
        "summary": model.summary().as_text(),
        "coefficients": {
            name: {
                "coef": round(model.params[name], 6),
                "std_err": round(model.bse[name], 6),
                "t": round(model.tvalues[name], 4),
                "P>|t|": round(model.pvalues[name], 4),
                "ci_low": round(model.conf_int().loc[name, 0], 6),
                "ci_high": round(model.conf_int().loc[name, 1], 6),
            }
            for name in model.params.index
        },
        "r_squared": round(model.rsquared, 4),
        "adj_r_squared": round(model.rsquared_adj, 4),
        "f_statistic": round(model.fvalue, 4),
        "f_pvalue": round(model.f_pvalue, 4),
        "n": int(model.nobs),
        "vif": vif_data,
        "durbin_watson": round(dw, 4),
        "aic": round(model.aic, 4),
        "bic": round(model.bic, 4),
        "e_b": model.params.to_dict(),
        "e_V": model.cov_params().to_dict(),
        "e_r2": round(model.rsquared, 6),
        "e_N": int(model.nobs),
    }


# ---------------------------------------------------------------------------
# 6. LOGISTIC REGRESSION  (Stata: logit / logistic)
# ---------------------------------------------------------------------------

def logistic_regression(df, depvar, indepvars):
    """Logistic regression via MLE (Stata: logit y x1 x2)."""
    cols = [depvar] + indepvars
    temp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    y = temp[depvar]
    X = sm.add_constant(temp[indepvars])

    model = sm.Logit(y, X).fit(disp=0)

    # Marginal effects at means
    mfx = model.get_margeff(at="mean")

    return {
        "summary": model.summary().as_text(),
        "coefficients": {
            name: {
                "coef": round(model.params[name], 6),
                "std_err": round(model.bse[name], 6),
                "z": round(model.tvalues[name], 4),
                "P>|z|": round(model.pvalues[name], 4),
                "odds_ratio": round(np.exp(model.params[name]), 4),
            }
            for name in model.params.index
        },
        "pseudo_r2": round(model.prsquared, 4),
        "log_likelihood": round(model.llf, 4),
        "aic": round(model.aic, 4),
        "bic": round(model.bic, 4),
        "n": int(model.nobs),
        "marginal_effects": mfx.summary_frame().to_string(),
    }


def probit_regression(df, depvar, indepvars):
    """Probit regression (Stata: probit y x1 x2)."""
    cols = [depvar] + indepvars
    temp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    y = temp[depvar]
    X = sm.add_constant(temp[indepvars])

    model = sm.Probit(y, X).fit(disp=0)
    mfx = model.get_margeff(at="mean")

    return {
        "summary": model.summary().as_text(),
        "pseudo_r2": round(model.prsquared, 4),
        "n": int(model.nobs),
        "marginal_effects": mfx.summary_frame().to_string(),
    }


# ---------------------------------------------------------------------------
# 7. NON-PARAMETRIC TESTS  (Stata: ranksum, signrank, kwallis)
# ---------------------------------------------------------------------------

def mann_whitney_u(df, variable, groupvar):
    """Mann-Whitney U / Wilcoxon rank-sum (Stata: ranksum)."""
    groups = df[groupvar].dropna().unique()
    if len(groups) != 2:
        return {"error": f"Need exactly 2 groups, found {len(groups)}"}
    g1 = pd.to_numeric(df.loc[df[groupvar] == groups[0], variable], errors="coerce").dropna()
    g2 = pd.to_numeric(df.loc[df[groupvar] == groups[1], variable], errors="coerce").dropna()
    u_stat, p_val = sp_stats.mannwhitneyu(g1, g2, alternative="two-sided")
    return {
        "U": round(u_stat, 4), "p": round(p_val, 4),
        "Group_1": str(groups[0]), "n1": len(g1),
        "Group_2": str(groups[1]), "n2": len(g2),
        "test": "Mann-Whitney U (Wilcoxon rank-sum)",
    }


def wilcoxon_signed_rank(df, var1, var2):
    """Wilcoxon signed-rank test (Stata: signrank)."""
    c1 = pd.to_numeric(df[var1], errors="coerce")
    c2 = pd.to_numeric(df[var2], errors="coerce")
    valid = c1.notna() & c2.notna()
    stat, p_val = sp_stats.wilcoxon(c1[valid], c2[valid])
    return {"T": round(stat, 4), "p": round(p_val, 4), "n": int(valid.sum())}


def kruskal_wallis(df, depvar, groupvar):
    """Kruskal-Wallis test (Stata: kwallis)."""
    groups = []
    names = []
    for name, grp in df.groupby(groupvar):
        vals = pd.to_numeric(grp[depvar], errors="coerce").dropna()
        if len(vals) > 0:
            groups.append(vals.values)
            names.append(str(name))
    h_stat, p_val = sp_stats.kruskal(*groups)
    return {
        "H": round(h_stat, 4), "df": len(groups)-1,
        "p": round(p_val, 4), "groups": names,
        "test": "Kruskal-Wallis H",
    }


# ---------------------------------------------------------------------------
# 8. CORRELATION  (Stata: correlate, pwcorr, spearman)
# ---------------------------------------------------------------------------

def correlation_matrix(df, variables, method="pearson"):
    """Correlation matrix (Stata: correlate / pwcorr / spearman)."""
    temp = df[variables].apply(pd.to_numeric, errors="coerce")
    if method == "spearman":
        corr = temp.corr(method="spearman")
    else:
        corr = temp.corr(method="pearson")

    # p-values
    n = len(temp.dropna())
    p_matrix = pd.DataFrame(np.ones((len(variables), len(variables))),
                            index=variables, columns=variables)
    for i, v1 in enumerate(variables):
        for j, v2 in enumerate(variables):
            if i != j:
                valid = temp[[v1, v2]].dropna()
                if len(valid) > 2:
                    if method == "spearman":
                        r, p = sp_stats.spearmanr(valid[v1], valid[v2])
                    else:
                        r, p = sp_stats.pearsonr(valid[v1], valid[v2])
                    p_matrix.iloc[i, j] = round(p, 4)

    return {
        "correlation": corr.round(4).to_dict(),
        "correlation_str": corr.round(4).to_string(),
        "p_values": p_matrix.round(4).to_dict(),
        "p_values_str": p_matrix.round(4).to_string(),
        "method": method, "n": n,
    }


# ---------------------------------------------------------------------------
# 9. POWER ANALYSIS  (Stata: power)
# ---------------------------------------------------------------------------

def power_ttest(n=None, delta=None, sd=1, alpha=0.05, power=None):
    """Power analysis for t-test."""
    from scipy.stats import norm, t as t_dist

    if power is None and n is not None and delta is not None:
        se = sd * np.sqrt(2.0 / n)
        ncp = abs(delta) / se
        crit = t_dist.ppf(1 - alpha/2, df=2*n - 2)
        power_val = 1 - t_dist.cdf(crit - ncp, df=2*n-2) + t_dist.cdf(-crit - ncp, df=2*n-2)
        return {"power": round(power_val, 4), "n": n, "delta": delta, "sd": sd, "alpha": alpha}

    if n is None and delta is not None and power is not None:
        for n_try in range(4, 100000):
            se = sd * np.sqrt(2.0 / n_try)
            ncp = abs(delta) / se
            crit = t_dist.ppf(1 - alpha/2, df=2*n_try - 2)
            pwr = 1 - t_dist.cdf(crit - ncp, df=2*n_try-2) + t_dist.cdf(-crit - ncp, df=2*n_try-2)
            if pwr >= power:
                return {"n_per_group": n_try, "total_n": 2*n_try,
                        "power": round(pwr, 4), "delta": delta, "sd": sd, "alpha": alpha}
        return {"error": "Could not find n within range"}

    return {"error": "Provide (n, delta, sd) to compute power, or (delta, sd, power) to compute n"}


def power_anova(k, n=None, f_effect=None, alpha=0.05, power=None):
    """Power analysis for one-way ANOVA using non-central F."""
    from scipy.stats import f as f_dist, ncf

    if power is None and n is not None and f_effect is not None:
        lmbda = n * k * f_effect**2
        df1 = k - 1
        df2 = k * (n - 1)
        f_crit = f_dist.ppf(1 - alpha, df1, df2)
        power_val = 1 - ncf.cdf(f_crit, df1, df2, lmbda)
        return {"power": round(power_val, 4), "n_per_group": n,
                "total_n": n*k, "k": k, "f_effect": f_effect, "alpha": alpha}

    if n is None and f_effect is not None and power is not None:
        for n_try in range(3, 50000):
            lmbda = n_try * k * f_effect**2
            df1 = k - 1
            df2 = k * (n_try - 1)
            f_crit = f_dist.ppf(1 - alpha, df1, df2)
            pwr = 1 - ncf.cdf(f_crit, df1, df2, lmbda)
            if pwr >= power:
                return {"n_per_group": n_try, "total_n": n_try*k, "power": round(pwr, 4),
                        "k": k, "f_effect": f_effect, "alpha": alpha}
        return {"error": "Could not find n within range"}

    return {"error": "Provide appropriate parameters"}


def power_chi2(w, n=None, df=1, alpha=0.05, power=None):
    """Power analysis for chi-square test."""
    from scipy.stats import chi2, ncx2

    if power is None and n is not None:
        lmbda = n * w**2
        crit = chi2.ppf(1 - alpha, df)
        power_val = 1 - ncx2.cdf(crit, df, lmbda)
        return {"power": round(power_val, 4), "n": n, "w": w, "df": df, "alpha": alpha}

    if n is None and power is not None:
        for n_try in range(5, 100000):
            lmbda = n_try * w**2
            crit = chi2.ppf(1 - alpha, df)
            pwr = 1 - ncx2.cdf(crit, df, lmbda)
            if pwr >= power:
                return {"n": n_try, "power": round(pwr, 4), "w": w, "df": df, "alpha": alpha}
        return {"error": "Could not find n within range"}

    return {"error": "Provide appropriate parameters"}


# ---------------------------------------------------------------------------
# 10. SAMPLE SIZE CALCULATION
# ---------------------------------------------------------------------------

def sample_size_means(delta, sd, alpha=0.05, power=0.80, ratio=1):
    """Sample size for comparing two means."""
    from scipy.stats import norm
    z_alpha = norm.ppf(1 - alpha/2)
    z_beta = norm.ppf(power)
    n1 = ((z_alpha + z_beta)**2 * sd**2 * (1 + 1/ratio)) / delta**2
    n2 = n1 / ratio
    return {
        "n1": int(np.ceil(n1)), "n2": int(np.ceil(n2)),
        "total": int(np.ceil(n1) + np.ceil(n2)),
        "delta": delta, "sd": sd, "alpha": alpha, "power": power, "ratio": ratio,
    }


def sample_size_proportions(p1, p2, alpha=0.05, power=0.80, ratio=1):
    """Sample size for comparing two proportions."""
    from scipy.stats import norm
    z_alpha = norm.ppf(1 - alpha/2)
    z_beta = norm.ppf(power)
    p_bar = (p1 + ratio * p2) / (1 + ratio)
    n1 = ((z_alpha * np.sqrt((1 + 1/ratio) * p_bar * (1 - p_bar)) +
           z_beta * np.sqrt(p1*(1-p1) + p2*(1-p2)/ratio))**2) / (p1 - p2)**2
    n2 = n1 / ratio
    return {
        "n1": int(np.ceil(n1)), "n2": int(np.ceil(n2)),
        "total": int(np.ceil(n1) + np.ceil(n2)),
        "p1": p1, "p2": p2, "alpha": alpha, "power": power,
    }


# ---------------------------------------------------------------------------
# 11. SURVIVAL ANALYSIS  (Stata: stset, sts, stcox)
# ---------------------------------------------------------------------------

def kaplan_meier(df, time_var, event_var, group_var=None):
    """Kaplan-Meier survival estimates."""
    try:
        from lifelines import KaplanMeierFitter
        from lifelines.statistics import logrank_test
    except ImportError:
        return {"error": "lifelines package required for survival analysis"}

    temp = df[[time_var, event_var] + ([group_var] if group_var else [])].dropna()
    temp[time_var] = pd.to_numeric(temp[time_var], errors="coerce")
    temp[event_var] = pd.to_numeric(temp[event_var], errors="coerce")
    temp = temp.dropna()

    results = {}

    if group_var is None:
        kmf = KaplanMeierFitter()
        kmf.fit(temp[time_var], temp[event_var])
        results["survival_table"] = kmf.survival_function_.to_string()
        results["median_survival"] = str(kmf.median_survival_time_)
        results["n"] = len(temp)
    else:
        groups = temp[group_var].unique()
        tables = {}
        medians = {}
        km_fitters = {}
        for g in groups:
            mask = temp[group_var] == g
            kmf = KaplanMeierFitter()
            kmf.fit(temp.loc[mask, time_var], temp.loc[mask, event_var], label=str(g))
            tables[str(g)] = kmf.survival_function_.to_string()
            medians[str(g)] = str(kmf.median_survival_time_)
            km_fitters[str(g)] = kmf

        results["survival_tables"] = tables
        results["median_survival"] = medians

        if len(groups) == 2:
            g1_mask = temp[group_var] == groups[0]
            g2_mask = temp[group_var] == groups[1]
            lr = logrank_test(
                temp.loc[g1_mask, time_var], temp.loc[g2_mask, time_var],
                temp.loc[g1_mask, event_var], temp.loc[g2_mask, event_var],
            )
            results["logrank"] = {
                "test_statistic": round(lr.test_statistic, 4),
                "p_value": round(lr.p_value, 4),
            }

    return results


def cox_regression(df, time_var, event_var, covariates):
    """Cox Proportional Hazards model (Stata: stcox)."""
    try:
        from lifelines import CoxPHFitter
    except ImportError:
        return {"error": "lifelines package required"}

    cols = [time_var, event_var] + covariates
    temp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()

    cph = CoxPHFitter()
    cph.fit(temp, duration_col=time_var, event_col=event_var)

    return {
        "summary": cph.summary.to_string(),
        "coefficients": {
            row: {
                "coef": round(cph.summary.loc[row, "coef"], 6),
                "exp(coef)": round(cph.summary.loc[row, "exp(coef)"], 4),
                "se(coef)": round(cph.summary.loc[row, "se(coef)"], 6),
                "z": round(cph.summary.loc[row, "z"], 4),
                "p": round(cph.summary.loc[row, "p"], 4),
            }
            for row in cph.summary.index
        },
        "concordance": round(cph.concordance_index_, 4),
        "log_likelihood": round(cph.log_likelihood_, 4),
        "n": len(temp),
    }


# ---------------------------------------------------------------------------
# 12. DATA MANAGEMENT UTILITIES
# ---------------------------------------------------------------------------

def detect_variable_types(df):
    """Analyze and classify variables (like Stata's codebook)."""
    info = []
    # Use positional indexing to avoid issues with duplicate column names
    for i, col in enumerate(df.columns):
        col_series = df.iloc[:, i]

        # Guard: if iloc returns a DataFrame (duplicate column names), take first column
        if isinstance(col_series, pd.DataFrame):
            col_series = col_series.iloc[:, 0]

        n_total = len(col_series)
        n_missing = int(col_series.isna().sum())
        n_valid = n_total - n_missing
        n_unique = int(col_series.nunique())

        try:
            numeric = pd.to_numeric(col_series, errors="coerce")
        except (TypeError, AttributeError):
            numeric = pd.Series([np.nan] * n_total)
        n_numeric = int(numeric.notna().sum())

        if n_numeric / max(n_valid, 1) > 0.8 and n_unique > 10:
            vtype = "continuous"
        elif n_unique <= 20 or n_numeric / max(n_valid, 1) <= 0.5:
            vtype = "categorical"
        else:
            vtype = "continuous"

        example = "N/A"
        if n_valid > 0:
            first_valid = col_series.dropna().iloc[0]
            example = str(first_valid)

        info.append({
            "Variable": col, "Type": vtype,
            "N": n_valid, "Missing": n_missing,
            "Unique": n_unique,
            "Example": example,
        })
    return pd.DataFrame(info)


def clean_data(df):
    """Auto-clean dataset: strip whitespace, detect types, handle obvious issues."""
    cleaned = df.copy()
    for i in range(len(cleaned.columns)):
        col = cleaned.iloc[:, i]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        try:
            if col.dtype == object:
                cleaned.iloc[:, i] = col.str.strip()
        except AttributeError:
            pass
    cleaned.columns = [str(c).strip().replace(" ", "_") for c in cleaned.columns]
    return cleaned


def reshape_wide_to_long(df, stub, i_var, j_var="time"):
    """Stata-style reshape long."""
    return pd.wide_to_long(df, stubnames=stub, i=i_var, j=j_var).reset_index()


def reshape_long_to_wide(df, index, columns, values):
    """Stata-style reshape wide."""
    return df.pivot_table(index=index, columns=columns, values=values).reset_index()


# ---------------------------------------------------------------------------
# 13. FISHER'S EXACT TEST
# ---------------------------------------------------------------------------

def fisher_exact_test(df, var1, var2):
    """Fisher's Exact Test for 2x2 contingency tables (small cell counts)."""
    ct = pd.crosstab(df[var1], df[var2])

    # Check if 2x2
    if ct.shape != (2, 2):
        return {
            "error": f"Fisher's Exact requires a 2x2 table, got {ct.shape}",
            "suggestion": "Use Chi-Square test for larger tables"
        }

    odds_ratio, p_val = sp_stats.fisher_exact(ct)

    # Also compute chi-square for comparison
    chi2, chi2_p, dof, expected = sp_stats.chi2_contingency(ct)
    min_expected = expected.min()

    return {
        "test": "Fisher's Exact Test",
        "observed": ct.to_dict(),
        "observed_str": ct.to_string(),
        "odds_ratio": round(odds_ratio, 4),
        "p_value": round(p_val, 4),
        "chi2_comparison": round(chi2, 4),
        "chi2_p": round(chi2_p, 4),
        "min_expected_cell": round(min_expected, 2),
        "recommendation": "Fisher's Exact is preferred when expected cell count < 5",
        "n": int(ct.sum().sum()),
    }


# ---------------------------------------------------------------------------
# 14. REPEATED MEASURES ANOVA
# ---------------------------------------------------------------------------

def repeated_measures_anova(df, subject_var, within_vars):
    """
    Repeated Measures ANOVA for within-subjects designs.
    within_vars: list of column names representing repeated measures (e.g., ['time1', 'time2', 'time3'])
    subject_var: column identifying subjects
    """
    # Reshape data to long format
    id_vars = [subject_var]
    value_vars = within_vars

    # Create long format
    long_data = pd.melt(
        df[id_vars + value_vars].dropna(),
        id_vars=id_vars,
        value_vars=value_vars,
        var_name='time',
        value_name='value'
    )
    long_data['value'] = pd.to_numeric(long_data['value'], errors='coerce')
    long_data = long_data.dropna()

    # Get group data
    groups = [grp['value'].values for name, grp in long_data.groupby('time')]
    k = len(groups)  # number of conditions
    n = len(df[subject_var].dropna().unique())  # number of subjects

    if k < 2:
        return {"error": "Need at least 2 time points for repeated measures"}

    # Compute SS components
    all_vals = long_data['value'].values
    grand_mean = all_vals.mean()
    N_total = len(all_vals)

    # SS Total
    ss_total = ((all_vals - grand_mean) ** 2).sum()

    # SS Between conditions (time)
    condition_means = [g.mean() for g in groups]
    ss_between = n * sum((m - grand_mean) ** 2 for m in condition_means)

    # SS Subjects
    subject_means = long_data.groupby(subject_var)['value'].mean()
    ss_subjects = k * ((subject_means - grand_mean) ** 2).sum()

    # SS Error (residual)
    ss_error = ss_total - ss_between - ss_subjects

    # Degrees of freedom
    df_between = k - 1
    df_subjects = n - 1
    df_error = (k - 1) * (n - 1)
    df_total = N_total - 1

    # Mean squares
    ms_between = ss_between / df_between if df_between > 0 else 0
    ms_error = ss_error / df_error if df_error > 0 else 0

    # F statistic
    f_stat = ms_between / ms_error if ms_error > 0 else 0
    p_val = 1 - sp_stats.f.cdf(f_stat, df_between, df_error) if f_stat > 0 else 1.0

    # Sphericity check (Mauchly's test approximation)
    # Using epsilon corrections
    epsilon_gg = min(1.0, max(0.5, 1 / (k - 1)))  # Simplified Greenhouse-Geisser

    # Corrected p-value
    p_val_gg = 1 - sp_stats.f.cdf(f_stat, df_between * epsilon_gg, df_error * epsilon_gg)

    # Condition summaries
    condition_stats = []
    for i, var in enumerate(within_vars):
        g = groups[i]
        condition_stats.append({
            "Condition": var,
            "N": len(g),
            "Mean": round(g.mean(), 4),
            "Std. Dev.": round(g.std(ddof=1), 4),
            "Std. Err.": round(sp_stats.sem(g), 4),
        })

    return {
        "test": "Repeated Measures ANOVA",
        "anova_table": {
            "Source": ["Between conditions", "Subjects", "Error", "Total"],
            "SS": [round(ss_between, 4), round(ss_subjects, 4), round(ss_error, 4), round(ss_total, 4)],
            "df": [df_between, df_subjects, df_error, df_total],
            "MS": [round(ms_between, 4), "", round(ms_error, 4), ""],
            "F": [round(f_stat, 4), "", "", ""],
            "p": [round(p_val, 4), "", "", ""],
        },
        "F": round(f_stat, 4),
        "p_value": round(p_val, 4),
        "p_value_GG": round(p_val_gg, 4),
        "epsilon_GG": round(epsilon_gg, 4),
        "condition_stats": condition_stats,
        "n_subjects": n,
        "n_conditions": k,
        "note": "Greenhouse-Geisser correction applied for sphericity violation",
    }


# ---------------------------------------------------------------------------
# 15. FRIEDMAN TEST (Non-parametric Repeated Measures)
# ---------------------------------------------------------------------------

def friedman_test(df, subject_var, within_vars):
    """
    Friedman Test - non-parametric alternative to Repeated Measures ANOVA.
    Used when normality assumption is violated.
    """
    # Get data matrix
    data = df[[subject_var] + within_vars].dropna()

    # Extract values for each condition
    groups = []
    for var in within_vars:
        groups.append(pd.to_numeric(data[var], errors='coerce').values)

    k = len(groups)
    n = len(groups[0])

    if k < 3:
        return {"error": "Friedman test requires at least 3 conditions"}

    # Perform Friedman test
    stat, p_val = sp_stats.friedmanchisquare(*groups)

    # Compute median ranks
    condition_stats = []
    for i, var in enumerate(within_vars):
        g = groups[i]
        condition_stats.append({
            "Condition": var,
            "N": len(g),
            "Median": round(np.median(g), 4),
            "Mean": round(g.mean(), 4),
            "Std. Dev.": round(g.std(ddof=1), 4),
        })

    # Effect size (Kendall's W)
    kendall_w = stat / (n * (k - 1)) if n * (k - 1) > 0 else 0

    return {
        "test": "Friedman Test",
        "chi2": round(stat, 4),
        "df": k - 1,
        "p_value": round(p_val, 4),
        "kendall_w": round(kendall_w, 4),
        "n_subjects": n,
        "n_conditions": k,
        "condition_stats": condition_stats,
        "interpretation": "Small" if kendall_w < 0.3 else "Medium" if kendall_w < 0.5 else "Large",
        "note": "Non-parametric alternative to Repeated Measures ANOVA",
    }


# ---------------------------------------------------------------------------
# 16. POST-HOC TESTS
# ---------------------------------------------------------------------------

def tukey_hsd(df, depvar, groupvar):
    """Tukey's Honestly Significant Difference post-hoc test."""
    temp = df[[depvar, groupvar]].dropna()
    temp[depvar] = pd.to_numeric(temp[depvar], errors='coerce')
    temp = temp.dropna()

    result = pairwise_tukeyhsd(temp[depvar], temp[groupvar], alpha=0.05)

    # Parse results
    comparisons = []
    for i in range(len(result.summary().data) - 1):
        row = result.summary().data[i + 1]
        comparisons.append({
            "Group1": str(row[0]),
            "Group2": str(row[1]),
            "Mean_Diff": round(float(row[2]), 4),
            "p_adj": round(float(row[3]), 4),
            "CI_Low": round(float(row[4]), 4),
            "CI_High": round(float(row[5]), 4),
            "Reject_H0": str(row[6]),
        })

    return {
        "test": "Tukey HSD",
        "comparisons": comparisons,
        "summary": str(result),
        "alpha": 0.05,
    }


def bonferroni_posthoc(df, depvar, groupvar, alpha=0.05):
    """Bonferroni-corrected pairwise comparisons."""
    temp = df[[depvar, groupvar]].dropna()
    temp[depvar] = pd.to_numeric(temp[depvar], errors='coerce')
    temp = temp.dropna()

    groups = temp[groupvar].unique()
    k = len(groups)
    n_comparisons = k * (k - 1) // 2
    alpha_corrected = alpha / n_comparisons

    comparisons = []
    for i in range(k):
        for j in range(i + 1, k):
            g1 = temp.loc[temp[groupvar] == groups[i], depvar]
            g2 = temp.loc[temp[groupvar] == groups[j], depvar]

            t_stat, p_val = sp_stats.ttest_ind(g1, g2)
            p_bonf = min(p_val * n_comparisons, 1.0)

            comparisons.append({
                "Group1": str(groups[i]),
                "Group2": str(groups[j]),
                "Mean1": round(g1.mean(), 4),
                "Mean2": round(g2.mean(), 4),
                "Mean_Diff": round(g1.mean() - g2.mean(), 4),
                "t": round(t_stat, 4),
                "p_raw": round(p_val, 4),
                "p_bonferroni": round(p_bonf, 4),
                "Significant": p_bonf < alpha,
            })

    return {
        "test": "Bonferroni Post-hoc",
        "comparisons": comparisons,
        "n_comparisons": n_comparisons,
        "alpha": alpha,
        "alpha_corrected": round(alpha_corrected, 6),
    }


# ---------------------------------------------------------------------------
# 17. SMART STATISTICAL ROUTER
# ---------------------------------------------------------------------------

# Temporal keywords for detecting paired/repeated measures
TEMPORAL_KEYWORDS = [
    'pre', 'post', 'before', 'after', 'baseline', 'followup', 'follow_up',
    'time1', 'time2', 'time3', 'time4', 't1', 't2', 't3', 't4',
    'week1', 'week2', 'week3', 'week4', 'w1', 'w2', 'w3', 'w4',
    'day1', 'day2', 'day3', 'day4', 'd1', 'd2', 'd3', 'd4',
    'visit1', 'visit2', 'visit3', 'v1', 'v2', 'v3',
    'month1', 'month2', 'month3', 'm1', 'm2', 'm3',
    'wave1', 'wave2', 'wave3',
    '_0', '_1', '_2', '_3',  # suffixes like score_0, score_1
    'initial', 'final', 'start', 'end',
]


def _classify_variable(col_series, col_name):
    """
    Classify a variable as Numerical/Continuous or Categorical/Nominal.
    Returns: 'continuous', 'categorical', or 'unknown'
    """
    if isinstance(col_series, pd.DataFrame):
        col_series = col_series.iloc[:, 0]

    n_total = len(col_series)
    n_valid = col_series.dropna().shape[0]

    if n_valid == 0:
        return 'unknown'

    # Try converting to numeric
    numeric = pd.to_numeric(col_series, errors='coerce')
    n_numeric = numeric.dropna().shape[0]
    numeric_ratio = n_numeric / n_valid

    n_unique = col_series.nunique()

    # Categorical indicators
    if n_unique <= 2:
        return 'categorical'  # Binary
    if n_unique <= 10 and numeric_ratio < 0.9:
        return 'categorical'
    if numeric_ratio < 0.5:
        return 'categorical'

    # Continuous indicators
    if numeric_ratio > 0.8 and n_unique > 15:
        return 'continuous'
    if numeric_ratio > 0.9 and n_unique > 10:
        return 'continuous'

    # Edge cases
    if n_unique <= 20 and n_unique / n_valid < 0.05:
        return 'categorical'  # Low cardinality ratio

    return 'continuous' if numeric_ratio > 0.7 else 'categorical'


def _detect_temporal_pattern(col_names):
    """
    Detect if columns have temporal keywords suggesting paired/repeated measures.
    Returns: list of columns that appear to be temporal measurements
    """
    temporal_cols = []
    for col in col_names:
        col_lower = str(col).lower()
        for keyword in TEMPORAL_KEYWORDS:
            if keyword in col_lower:
                temporal_cols.append(col)
                break
    return temporal_cols


def _detect_grouping_variable(df, selected_cols):
    """
    Detect which column is likely the grouping variable.
    Returns: (group_col, outcome_cols) or (None, selected_cols)
    """
    categorical_cols = []
    continuous_cols = []

    for col in selected_cols:
        vtype = _classify_variable(df[col], col)
        if vtype == 'categorical':
            categorical_cols.append(col)
        else:
            continuous_cols.append(col)

    # If one categorical and rest continuous, the categorical is likely the grouper
    if len(categorical_cols) == 1 and len(continuous_cols) >= 1:
        return categorical_cols[0], continuous_cols

    # If multiple categoricals, pick the one with fewest unique values as grouper
    if len(categorical_cols) > 1 and len(continuous_cols) >= 1:
        min_unique = float('inf')
        best_grouper = None
        for col in categorical_cols:
            nuniq = df[col].nunique()
            if 2 <= nuniq <= 10 and nuniq < min_unique:
                min_unique = nuniq
                best_grouper = col
        if best_grouper:
            remaining = [c for c in selected_cols if c != best_grouper]
            return best_grouper, remaining

    return None, selected_cols


def _check_normality(col_series, alpha=0.05):
    """
    Check if data is normally distributed using Shapiro-Wilk test.
    Returns: (is_normal, p_value, test_stat)
    """
    if isinstance(col_series, pd.DataFrame):
        col_series = col_series.iloc[:, 0]

    data = pd.to_numeric(col_series, errors='coerce').dropna()

    if len(data) < 3:
        return True, 1.0, None  # Assume normal if too few observations

    # Shapiro-Wilk is most powerful for n < 5000
    if len(data) <= 5000:
        try:
            stat, p = sp_stats.shapiro(data)
            return p > alpha, p, stat
        except:
            return True, 1.0, None
    else:
        # For large samples, use D'Agostino and Pearson's test
        try:
            stat, p = sp_stats.normaltest(data)
            return p > alpha, p, stat
        except:
            return True, 1.0, None


def _check_homogeneity_of_variance(groups, alpha=0.05):
    """Check equal variances using Levene's test."""
    if len(groups) < 2:
        return True, 1.0
    try:
        stat, p = sp_stats.levene(*groups)
        return p > alpha, p
    except:
        return True, 1.0


def select_statistical_test(df, selected_columns, subject_var=None, alpha=0.05):
    """
    SMART STATISTICAL ROUTER

    Automatically selects the most appropriate statistical test based on:
    1. Number and types of variables (continuous vs categorical)
    2. Normality of distributions
    3. Number of groups (2 vs >2)
    4. Independence (independent vs paired/repeated measures)
    5. Sample sizes (for Fisher's Exact vs Chi-Square)

    Args:
        df: pandas DataFrame
        selected_columns: list of column names to analyze
        subject_var: optional column identifying subjects (for repeated measures)
        alpha: significance level for assumption tests

    Returns:
        dict with recommended test, results, and reasoning
    """
    if not selected_columns or len(selected_columns) == 0:
        return {"error": "No columns selected for analysis"}

    # Classify all selected variables
    var_types = {}
    for col in selected_columns:
        var_types[col] = _classify_variable(df[col], col)

    continuous_vars = [c for c in selected_columns if var_types[c] == 'continuous']
    categorical_vars = [c for c in selected_columns if var_types[c] == 'categorical']

    # Detect temporal patterns
    temporal_cols = _detect_temporal_pattern(selected_columns)
    has_temporal = len(temporal_cols) >= 2

    result = {
        "variable_classification": var_types,
        "continuous_variables": continuous_vars,
        "categorical_variables": categorical_vars,
        "temporal_detected": temporal_cols,
        "reasoning": [],
        "test_name": None,
        "test_result": None,
        "posthoc_result": None,
    }

    # ==== CASE 1: All Continuous Variables (Correlation) ====
    if len(continuous_vars) >= 2 and len(categorical_vars) == 0:
        result["reasoning"].append("Multiple continuous variables detected -> Correlation analysis")

        # Check normality for Pearson vs Spearman
        all_normal = True
        for col in continuous_vars[:2]:  # Check first two
            is_normal, p, _ = _check_normality(df[col])
            if not is_normal:
                all_normal = False
                result["reasoning"].append(f"  {col} failed normality test (p={round(p, 4)})")

        method = "pearson" if all_normal else "spearman"
        result["reasoning"].append(f"  Using {method.title()} correlation")
        result["test_name"] = f"{method.title()} Correlation"
        result["test_result"] = correlation_matrix(df, continuous_vars, method=method)
        return result

    # ==== CASE 2: Two Categorical Variables (Chi-Square / Fisher) ====
    if len(categorical_vars) == 2 and len(continuous_vars) == 0:
        var1, var2 = categorical_vars
        ct = pd.crosstab(df[var1], df[var2])

        # Check for Fisher's Exact conditions
        _, _, _, expected = sp_stats.chi2_contingency(ct)
        min_expected = expected.min()

        if ct.shape == (2, 2) and min_expected < 5:
            result["reasoning"].append("2x2 table with expected cell count < 5 -> Fisher's Exact Test")
            result["test_name"] = "Fisher's Exact Test"
            result["test_result"] = fisher_exact_test(df, var1, var2)
        else:
            result["reasoning"].append("Categorical variables -> Chi-Square Test")
            if min_expected < 5:
                result["reasoning"].append(f"  WARNING: Min expected cell = {round(min_expected, 2)} < 5")
            result["test_name"] = "Chi-Square Test"
            result["test_result"] = chi_square_test(df, var1, var2)

        return result

    # ==== CASE 3: One Categorical (Group) + One Continuous (Outcome) ====
    if len(categorical_vars) == 1 and len(continuous_vars) == 1:
        group_var = categorical_vars[0]
        outcome_var = continuous_vars[0]
        n_groups = df[group_var].nunique()

        result["reasoning"].append(f"One grouping variable ({group_var}) with {n_groups} groups")
        result["reasoning"].append(f"One continuous outcome ({outcome_var})")

        # Get groups data
        groups = []
        group_names = []
        for name, grp in df.groupby(group_var):
            vals = pd.to_numeric(grp[outcome_var], errors='coerce').dropna()
            if len(vals) > 0:
                groups.append(vals.values)
                group_names.append(str(name))

        # Check normality for each group
        all_normal = True
        for i, g in enumerate(groups):
            is_normal, p, _ = _check_normality(pd.Series(g))
            if not is_normal:
                all_normal = False
                result["reasoning"].append(f"  Group '{group_names[i]}' failed normality (p={round(p, 4)})")

        # Check homogeneity of variance
        equal_var, lev_p = _check_homogeneity_of_variance(groups)
        if not equal_var:
            result["reasoning"].append(f"  Unequal variances detected (Levene p={round(lev_p, 4)})")

        # ==== 2 Groups ====
        if n_groups == 2:
            if all_normal:
                result["reasoning"].append("  Normal distributions -> Independent t-test")
                if not equal_var:
                    result["reasoning"].append("  Using Welch's t-test (unequal variances)")
                result["test_name"] = "Two-Sample t-test"
                result["test_result"] = ttest_two_sample(df, outcome_var, group_var, equal_var=equal_var)
            else:
                result["reasoning"].append("  Non-normal distributions -> Mann-Whitney U test")
                result["test_name"] = "Mann-Whitney U Test"
                result["test_result"] = mann_whitney_u(df, outcome_var, group_var)

        # ==== >2 Groups ====
        elif n_groups > 2:
            if all_normal:
                result["reasoning"].append("  Normal distributions -> One-way ANOVA")
                result["test_name"] = "One-way ANOVA"
                result["test_result"] = oneway_anova(df, outcome_var, group_var)

                # Auto trigger post-hoc if significant
                if result["test_result"].get("Prob > F", 1.0) < alpha:
                    result["reasoning"].append("  ANOVA significant -> Running Tukey HSD post-hoc")
                    result["posthoc_result"] = tukey_hsd(df, outcome_var, group_var)
            else:
                result["reasoning"].append("  Non-normal distributions -> Kruskal-Wallis test")
                result["test_name"] = "Kruskal-Wallis Test"
                result["test_result"] = kruskal_wallis(df, outcome_var, group_var)

                # Post-hoc for Kruskal-Wallis
                if result["test_result"].get("p", 1.0) < alpha:
                    result["reasoning"].append("  Kruskal-Wallis significant -> Running Bonferroni post-hoc")
                    result["posthoc_result"] = bonferroni_posthoc(df, outcome_var, group_var)

        return result

    # ==== CASE 4: Temporal/Paired Variables (Repeated Measures) ====
    if has_temporal and len(temporal_cols) >= 2:
        # All temporal columns should be continuous
        temporal_continuous = [c for c in temporal_cols if var_types.get(c, 'unknown') == 'continuous']

        if len(temporal_continuous) >= 2:
            result["reasoning"].append(f"Temporal pattern detected in columns: {temporal_continuous}")

            # Check normality of differences (for paired tests)
            if len(temporal_continuous) == 2:
                var1, var2 = temporal_continuous
                c1 = pd.to_numeric(df[var1], errors='coerce')
                c2 = pd.to_numeric(df[var2], errors='coerce')
                valid = c1.notna() & c2.notna()
                diff = c1[valid] - c2[valid]
                is_normal, p, _ = _check_normality(diff)

                if is_normal:
                    result["reasoning"].append("  Normal differences -> Paired t-test")
                    result["test_name"] = "Paired t-test"
                    result["test_result"] = ttest_paired(df, var1, var2)
                else:
                    result["reasoning"].append(f"  Non-normal differences (p={round(p, 4)}) -> Wilcoxon signed-rank")
                    result["test_name"] = "Wilcoxon Signed-Rank Test"
                    result["test_result"] = wilcoxon_signed_rank(df, var1, var2)

            elif len(temporal_continuous) >= 3:
                # Check normality for repeated measures
                all_normal = True
                for col in temporal_continuous:
                    is_normal, p, _ = _check_normality(df[col])
                    if not is_normal:
                        all_normal = False
                        result["reasoning"].append(f"  {col} failed normality (p={round(p, 4)})")

                if subject_var and subject_var in df.columns:
                    if all_normal:
                        result["reasoning"].append("  Normal distributions -> Repeated Measures ANOVA")
                        result["test_name"] = "Repeated Measures ANOVA"
                        result["test_result"] = repeated_measures_anova(df, subject_var, temporal_continuous)
                    else:
                        result["reasoning"].append("  Non-normal -> Friedman Test")
                        result["test_name"] = "Friedman Test"
                        result["test_result"] = friedman_test(df, subject_var, temporal_continuous)
                else:
                    result["reasoning"].append("  WARNING: No subject variable specified for repeated measures")
                    result["reasoning"].append("  Provide subject_var parameter for proper repeated measures analysis")
                    # Fall back to comparing first two time points
                    var1, var2 = temporal_continuous[0], temporal_continuous[1]
                    result["test_name"] = "Paired t-test (fallback)"
                    result["test_result"] = ttest_paired(df, var1, var2)

            return result

    # ==== CASE 5: Mixed - Detect grouper automatically ====
    if len(selected_columns) >= 2:
        group_var, outcome_vars = _detect_grouping_variable(df, selected_columns)

        if group_var and outcome_vars:
            result["reasoning"].append(f"Auto-detected grouping variable: {group_var}")
            result["reasoning"].append(f"Outcome variables: {outcome_vars}")

            # Recursively call with detected structure
            if len(outcome_vars) == 1:
                # Single outcome - use the standard analysis
                return select_statistical_test(df, [group_var, outcome_vars[0]], subject_var, alpha)
            else:
                # Multiple outcomes - analyze each
                result["test_name"] = "Multiple Outcome Analysis"
                result["test_result"] = {}
                for outcome in outcome_vars:
                    sub_result = select_statistical_test(df, [group_var, outcome], subject_var, alpha)
                    result["test_result"][outcome] = {
                        "test": sub_result.get("test_name"),
                        "result": sub_result.get("test_result"),
                    }
                return result

    # ==== CASE 6: Single Continuous Variable ====
    if len(continuous_vars) == 1 and len(categorical_vars) == 0:
        result["reasoning"].append("Single continuous variable -> Descriptive statistics")
        result["test_name"] = "Descriptive Statistics"
        result["test_result"] = descriptive_stats(df, continuous_vars, detail=True).to_dict('records')

        # Add normality test
        is_normal, p, stat = _check_normality(df[continuous_vars[0]])
        result["normality_test"] = {
            "is_normal": is_normal,
            "p_value": round(p, 4) if p else None,
            "statistic": round(stat, 4) if stat else None,
        }
        return result

    # ==== CASE 7: Single Categorical Variable ====
    if len(categorical_vars) == 1 and len(continuous_vars) == 0:
        result["reasoning"].append("Single categorical variable -> Frequency table")
        result["test_name"] = "Frequency Table"
        result["test_result"] = tabulate(df, categorical_vars[0]).to_dict('records')
        return result

    # ==== Fallback ====
    result["reasoning"].append("Could not determine appropriate test automatically")
    result["reasoning"].append("Please specify the analysis type manually")
    result["test_name"] = "Manual Selection Required"
    result["suggestion"] = {
        "if_comparing_groups": "Use ttest_two_sample or oneway_anova",
        "if_correlation": "Use correlation_matrix",
        "if_categorical": "Use chi_square_test",
        "if_paired": "Use ttest_paired or wilcoxon_signed_rank",
    }

    return result


def run_smart_analysis(df, selected_columns, subject_var=None, alpha=0.05):
    """
    Wrapper for select_statistical_test with additional validation and formatting.
    Returns user-friendly output with clear recommendations.
    """
    result = select_statistical_test(df, selected_columns, subject_var, alpha)

    # Format the output for display
    output = {
        "selected_test": result.get("test_name", "Unknown"),
        "reasoning": "\n".join(result.get("reasoning", [])),
        "variable_types": result.get("variable_classification", {}),
        "result": result.get("test_result", {}),
    }

    if result.get("posthoc_result"):
        output["posthoc"] = result.get("posthoc_result")
        output["posthoc_note"] = "Post-hoc test automatically triggered due to significant main effect"

    if result.get("normality_test"):
        output["normality"] = result.get("normality_test")

    return output


# ---------------------------------------------------------------------------
# 18. MASTER DISPATCHER
# ---------------------------------------------------------------------------

AVAILABLE_TESTS = {
    "descriptive": {
        "func": "descriptive_stats",
        "description": "Descriptive statistics (mean, SD, min, max, percentiles)",
        "stata_cmd": "summarize",
    },
    "tabulate": {
        "func": "tabulate",
        "description": "Frequency tables and cross-tabulations",
        "stata_cmd": "tabulate",
    },
    "normality": {
        "func": "normality_test",
        "description": "Normality test (D'Agostino-Pearson, Shapiro-Wilk)",
        "stata_cmd": "sktest / swilk",
    },
    "ttest_one": {
        "func": "ttest_one_sample",
        "description": "One-sample t-test",
        "stata_cmd": "ttest var == #",
    },
    "ttest_two": {
        "func": "ttest_two_sample",
        "description": "Two-sample t-test (independent groups)",
        "stata_cmd": "ttest var, by(group)",
    },
    "ttest_paired": {
        "func": "ttest_paired",
        "description": "Paired t-test",
        "stata_cmd": "ttest var1 == var2",
    },
    "oneway_anova": {
        "func": "oneway_anova",
        "description": "One-way ANOVA",
        "stata_cmd": "oneway depvar groupvar",
    },
    "twoway_anova": {
        "func": "twoway_anova",
        "description": "Two-way ANOVA (factorial)",
        "stata_cmd": "anova depvar factor1 factor2 factor1#factor2",
    },
    "chi_square": {
        "func": "chi_square_test",
        "description": "Chi-square test of independence",
        "stata_cmd": "tabulate var1 var2, chi2",
    },
    "regression": {
        "func": "linear_regression",
        "description": "OLS linear regression",
        "stata_cmd": "regress y x1 x2 ...",
    },
    "logistic": {
        "func": "logistic_regression",
        "description": "Logistic regression",
        "stata_cmd": "logit y x1 x2 ...",
    },
    "probit": {
        "func": "probit_regression",
        "description": "Probit regression",
        "stata_cmd": "probit y x1 x2 ...",
    },
    "mann_whitney": {
        "func": "mann_whitney_u",
        "description": "Mann-Whitney U / Wilcoxon rank-sum test",
        "stata_cmd": "ranksum var, by(group)",
    },
    "wilcoxon": {
        "func": "wilcoxon_signed_rank",
        "description": "Wilcoxon signed-rank test",
        "stata_cmd": "signrank var1 = var2",
    },
    "kruskal_wallis": {
        "func": "kruskal_wallis",
        "description": "Kruskal-Wallis H test",
        "stata_cmd": "kwallis var, by(group)",
    },
    "correlation": {
        "func": "correlation_matrix",
        "description": "Pearson / Spearman correlation matrix",
        "stata_cmd": "correlate / pwcorr / spearman",
    },
    "kaplan_meier": {
        "func": "kaplan_meier",
        "description": "Kaplan-Meier survival analysis",
        "stata_cmd": "sts graph / sts test",
    },
    "cox": {
        "func": "cox_regression",
        "description": "Cox proportional hazards regression",
        "stata_cmd": "stcox var1 var2 ...",
    },
    "power_ttest": {
        "func": "power_ttest",
        "description": "Power analysis for t-test",
        "stata_cmd": "power twomeans",
    },
    "power_anova": {
        "func": "power_anova",
        "description": "Power analysis for ANOVA",
        "stata_cmd": "power oneway",
    },
    "power_chi2": {
        "func": "power_chi2",
        "description": "Power analysis for chi-square",
        "stata_cmd": "power cmh",
    },
    "sample_size_means": {
        "func": "sample_size_means",
        "description": "Sample size for comparing means",
        "stata_cmd": "power twomeans",
    },
    "sample_size_proportions": {
        "func": "sample_size_proportions",
        "description": "Sample size for comparing proportions",
        "stata_cmd": "power twoproportions",
    },
    "fisher_exact": {
        "func": "fisher_exact_test",
        "description": "Fisher's Exact Test for 2x2 tables (small samples)",
        "stata_cmd": "tabulate var1 var2, exact",
    },
    "repeated_measures_anova": {
        "func": "repeated_measures_anova",
        "description": "Repeated Measures ANOVA (within-subjects)",
        "stata_cmd": "anova depvar subject time, repeated(time)",
    },
    "friedman": {
        "func": "friedman_test",
        "description": "Friedman Test (non-parametric repeated measures)",
        "stata_cmd": "friedman var1 var2 var3, id(subject)",
    },
    "tukey_hsd": {
        "func": "tukey_hsd",
        "description": "Tukey HSD post-hoc test",
        "stata_cmd": "oneway depvar groupvar, tukey",
    },
    "bonferroni": {
        "func": "bonferroni_posthoc",
        "description": "Bonferroni-corrected pairwise comparisons",
        "stata_cmd": "oneway depvar groupvar, bonferroni",
    },
    "smart_analysis": {
        "func": "run_smart_analysis",
        "description": "Auto-select appropriate test based on data",
        "stata_cmd": "auto",
    },
}


def list_available_tests():
    """Return list of all available statistical tests."""
    return {k: {"description": v["description"], "stata_cmd": v["stata_cmd"]}
            for k, v in AVAILABLE_TESTS.items()}
