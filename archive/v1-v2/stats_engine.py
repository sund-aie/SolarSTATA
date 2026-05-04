"""
SolarSTATA Statistical Engine  —  Pure computation, zero AI.

Every function takes a DataFrame (or scalars) and returns a plain dict.
scipy / statsmodels do the heavy lifting; we just wrap them with
Stata-style names and output keys.

Sections
--------
 1  Descriptive statistics
 2  T-tests
 3  ANOVA
 4  Chi-square & Fisher
 5  Regression (OLS, logistic, probit)
 6  Non-parametric tests
 7  Correlation
 8  Post-hoc tests
 9  Repeated measures
10  Power & sample-size
11  Survival analysis
12  Normality
13  Data utilities
14  Smart Statistical Router
"""

import warnings, re
import numpy as np
import pandas as pd
from scipy import stats as sp
from scipy.special import comb
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import statsmodels.api as sm
from statsmodels.formula.api import ols as smf_ols
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.diagnostic import het_breuschpagan, het_white
from statsmodels.stats.stattools import durbin_watson
from statsmodels.stats.outliers_influence import variance_inflation_factor

warnings.filterwarnings("ignore")

_R = lambda v, n=4: round(float(v), n) if v is not None and not np.isnan(v) else None

# ===================================================================
# 1. DESCRIPTIVE STATISTICS
# ===================================================================

def descriptive(df, variables=None, detail=False):
    """Stata `summarize [varlist] [, detail]`."""
    if variables is None:
        variables = df.select_dtypes(include=[np.number]).columns.tolist()
    rows = []
    for var in variables:
        col = pd.to_numeric(df[var], errors="coerce").dropna()
        if col.empty:
            continue
        r = dict(Variable=var, Obs=len(col), Mean=_R(col.mean(), 6),
                 SD=_R(col.std(ddof=1), 6), Min=_R(col.min(), 6), Max=_R(col.max(), 6))
        if detail:
            r.update(Variance=_R(col.var(ddof=1)), Skewness=_R(sp.skew(col, bias=False)),
                     Kurtosis=_R(sp.kurtosis(col, bias=False, fisher=False)),
                     p1=_R(np.percentile(col, 1)), p5=_R(np.percentile(col, 5)),
                     p10=_R(np.percentile(col, 10)), p25=_R(np.percentile(col, 25)),
                     p50=_R(np.percentile(col, 50)), p75=_R(np.percentile(col, 75)),
                     p90=_R(np.percentile(col, 90)), p95=_R(np.percentile(col, 95)),
                     p99=_R(np.percentile(col, 99)))
        rows.append(r)
    return pd.DataFrame(rows)


def tabulate(df, var1, var2=None):
    """Stata `tabulate` — frequency or cross-tab."""
    if var2 is None:
        freq = df[var1].value_counts().sort_index()
        total = freq.sum()
        return pd.DataFrame({var1: freq.index, "Freq.": freq.values,
                             "Percent": (freq.values / total * 100).round(2),
                             "Cum.": (freq.values.cumsum() / total * 100).round(2)})
    return pd.crosstab(df[var1], df[var2], margins=True, margins_name="Total")


# ===================================================================
# 2. T-TESTS
# ===================================================================

def ttest_one(df, variable, mu=0):
    col = pd.to_numeric(df[variable], errors="coerce").dropna()
    t, p = sp.ttest_1samp(col, mu)
    ci = sp.t.interval(0.95, df=len(col)-1, loc=col.mean(), scale=sp.sem(col))
    return dict(Variable=variable, Obs=len(col), Mean=_R(col.mean(), 6),
                SE=_R(sp.sem(col), 6), SD=_R(col.std(ddof=1), 6),
                CI_95=f"[{ci[0]:.6f}, {ci[1]:.6f}]",
                t=_R(t), df=len(col)-1, p_two=_R(p),
                p_left=_R(p/2 if t < 0 else 1 - p/2),
                p_right=_R(p/2 if t > 0 else 1 - p/2), mu_0=mu)


def ttest_two(df, variable, groupvar, equal_var=True):
    groups = df[groupvar].dropna().unique()
    if len(groups) != 2:
        return dict(error=f"Need exactly 2 groups, found {len(groups)}: {list(groups)}")
    g1 = pd.to_numeric(df.loc[df[groupvar] == groups[0], variable], errors="coerce").dropna()
    g2 = pd.to_numeric(df.loc[df[groupvar] == groups[1], variable], errors="coerce").dropna()
    t_eq, p_eq = sp.ttest_ind(g1, g2, equal_var=True)
    t_w, p_w = sp.ttest_ind(g1, g2, equal_var=False)
    n1, n2 = len(g1), len(g2)
    m1, m2 = g1.mean(), g2.mean()
    s1, s2 = g1.std(ddof=1), g2.std(ddof=1)
    se1, se2 = sp.sem(g1), sp.sem(g2)
    diff = m1 - m2
    sp2 = ((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2)
    se_pool = np.sqrt(sp2*(1/n1+1/n2))
    dof_eq = n1+n2-2
    dof_w = (se1**2+se2**2)**2 / (se1**4/(n1-1)+se2**4/(n2-1))
    ci = sp.t.interval(0.95, df=dof_eq, loc=diff, scale=se_pool)
    return dict(Group_1=str(groups[0]), n1=n1, mean1=_R(m1,6), se1=_R(se1,6),
                Group_2=str(groups[1]), n2=n2, mean2=_R(m2,6), se2=_R(se2,6),
                diff=_R(diff,6), SE=_R(se_pool,6),
                CI_95=f"[{ci[0]:.6f}, {ci[1]:.6f}]",
                t_equal=_R(t_eq), p_equal=_R(p_eq), df_equal=dof_eq,
                t_welch=_R(t_w), p_welch=_R(p_w), df_welch=_R(dof_w,2))


def ttest_paired(df, var1, var2):
    c1 = pd.to_numeric(df[var1], errors="coerce")
    c2 = pd.to_numeric(df[var2], errors="coerce")
    ok = c1.notna() & c2.notna()
    c1, c2 = c1[ok], c2[ok]
    d = c1 - c2
    t, p = sp.ttest_rel(c1, c2)
    ci = sp.t.interval(0.95, df=len(d)-1, loc=d.mean(), scale=sp.sem(d))
    return dict(Variable_1=var1, Variable_2=var2, Obs=len(d),
                Mean_diff=_R(d.mean(),6), SE=_R(sp.sem(d),6), SD=_R(d.std(ddof=1),6),
                CI_95=f"[{ci[0]:.6f}, {ci[1]:.6f}]",
                t=_R(t), df=len(d)-1, p=_R(p))


# ===================================================================
# 3. ANOVA
# ===================================================================

def oneway_anova(df, depvar, groupvar):
    groups, gnames = [], []
    for name, g in df.groupby(groupvar):
        v = pd.to_numeric(g[depvar], errors="coerce").dropna()
        if len(v) > 0:
            groups.append(v.values); gnames.append(str(name))
    if len(groups) < 2:
        return dict(error="Need at least 2 groups with data")
    f, p = sp.f_oneway(*groups)
    a = np.concatenate(groups); gm = a.mean(); N = len(a); k = len(groups)
    ssb = sum(len(g)*(g.mean()-gm)**2 for g in groups)
    ssw = sum(((g-g.mean())**2).sum() for g in groups)
    sst = ((a-gm)**2).sum()
    dfb, dfw, dft = k-1, N-k, N-1
    msb, msw = ssb/dfb, ssw/dfw
    bart_s, bart_p = sp.bartlett(*groups)
    lev_s, lev_p = sp.levene(*groups)
    gs = [dict(Group=gnames[i], N=len(g), Mean=_R(g.mean(),6), SD=_R(g.std(ddof=1),6))
          for i, g in enumerate(groups)]
    return dict(
        anova_table=dict(Source=["Between groups","Within groups","Total"],
                         SS=[_R(ssb),_R(ssw),_R(sst)], df=[dfb,dfw,dft],
                         MS=[_R(msb),_R(msw),""], F=[_R(f),"",""],
                         Prob=[_R(p),"",""]),
        group_stats=gs, F=_R(f), p=_R(p),
        bartlett=dict(chi2=_R(bart_s), p=_R(bart_p)),
        levene=dict(F=_R(lev_s), p=_R(lev_p)))


def twoway_anova(df, depvar, factor1, factor2, interaction=True):
    tmp = df[[depvar, factor1, factor2]].dropna().copy()
    tmp[depvar] = pd.to_numeric(tmp[depvar], errors="coerce"); tmp = tmp.dropna()
    formula = f"{depvar} ~ C({factor1})" + (f" * C({factor2})" if interaction else f" + C({factor2})")
    model = smf_ols(formula, data=tmp).fit()
    aov = anova_lm(model, typ=2)
    # Clean NaN from string representations
    aov_str = aov.fillna("").to_string()
    return dict(anova_table=aov.to_dict(), anova_str=aov_str,
                r2=_R(model.rsquared), adj_r2=_R(model.rsquared_adj),
                summary=model.summary().as_text())


# ===================================================================
# 4. CHI-SQUARE & FISHER
# ===================================================================

def chi_square(df, var1, var2):
    ct = pd.crosstab(df[var1], df[var2])
    chi2, p, dof, exp = sp.chi2_contingency(ct)
    n = ct.sum().sum(); k = min(ct.shape)-1
    cv = np.sqrt(chi2/(n*k)) if k > 0 else 0
    return dict(observed=ct.to_dict(), expected=pd.DataFrame(np.round(exp,2),
                index=ct.index, columns=ct.columns).to_dict(),
                chi2=_R(chi2), df=dof, p=_R(p), cramers_v=_R(cv), n=int(n),
                observed_str=ct.to_string(),
                expected_str=pd.DataFrame(np.round(exp,2), index=ct.index, columns=ct.columns).to_string())


def chi_square_gof(df, variable, expected_freq=None):
    obs = df[variable].value_counts().sort_index()
    if expected_freq is None:
        expected_freq = np.full(len(obs), obs.sum()/len(obs))
    chi2, p = sp.chisquare(obs.values, f_exp=expected_freq)
    return dict(chi2=_R(chi2), df=len(obs)-1, p=_R(p), observed=obs.to_dict())


def fisher_exact(df, var1, var2):
    ct = pd.crosstab(df[var1], df[var2])
    if ct.shape != (2,2):
        return dict(error=f"Fisher requires 2×2, got {ct.shape}",
                    suggestion="Use chi_square for larger tables")
    odds, p = sp.fisher_exact(ct)
    chi2, chi2_p, _, exp = sp.chi2_contingency(ct)
    return dict(test="Fisher's Exact", observed_str=ct.to_string(),
                odds_ratio=_R(odds), p=_R(p),
                chi2_comparison=_R(chi2), chi2_p=_R(chi2_p),
                min_expected=_R(exp.min(),2), n=int(ct.sum().sum()))


# ===================================================================
# 5. REGRESSION
# ===================================================================

def ols_regression(df, depvar, indepvars, robust=False):
    cols = [depvar]+indepvars
    tmp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if tmp.empty or len(tmp) < len(indepvars)+2:
        return dict(error="Insufficient observations")
    y = tmp[depvar]; X = sm.add_constant(tmp[indepvars])
    model = sm.OLS(y, X).fit(cov_type="HC1") if robust else sm.OLS(y, X).fit()
    vif = [dict(Variable=c, VIF=_R(variance_inflation_factor(X.values, i),2))
           for i, c in enumerate(X.columns) if c != "const"]
    coefs = {n: dict(coef=_R(model.params[n],6), se=_R(model.bse[n],6),
                     t=_R(model.tvalues[n]), p=_R(model.pvalues[n]),
                     ci_lo=_R(model.conf_int().loc[n,0],6),
                     ci_hi=_R(model.conf_int().loc[n,1],6))
             for n in model.params.index}
    return dict(summary=model.summary().as_text(), coefficients=coefs,
                r2=_R(model.rsquared), adj_r2=_R(model.rsquared_adj),
                f=_R(model.fvalue), f_p=_R(model.f_pvalue), n=int(model.nobs),
                vif=vif, dw=_R(durbin_watson(model.resid)),
                aic=_R(model.aic), bic=_R(model.bic))


def logistic_regression(df, depvar, indepvars):
    cols = [depvar]+indepvars
    tmp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    y = tmp[depvar]; X = sm.add_constant(tmp[indepvars])
    model = sm.Logit(y, X).fit(disp=0)
    mfx = model.get_margeff(at="mean")
    coefs = {n: dict(coef=_R(model.params[n],6), se=_R(model.bse[n],6),
                     z=_R(model.tvalues[n]), p=_R(model.pvalues[n]),
                     OR=_R(np.exp(model.params[n])))
             for n in model.params.index}
    return dict(summary=model.summary().as_text(), coefficients=coefs,
                pseudo_r2=_R(model.prsquared), ll=_R(model.llf),
                aic=_R(model.aic), bic=_R(model.bic), n=int(model.nobs),
                marginal_effects=mfx.summary_frame().to_string())


def probit_regression(df, depvar, indepvars):
    cols = [depvar]+indepvars
    tmp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    y = tmp[depvar]; X = sm.add_constant(tmp[indepvars])
    model = sm.Probit(y, X).fit(disp=0)
    mfx = model.get_margeff(at="mean")
    return dict(summary=model.summary().as_text(),
                pseudo_r2=_R(model.prsquared), n=int(model.nobs),
                marginal_effects=mfx.summary_frame().to_string())


# ===================================================================
# 6. NON-PARAMETRIC TESTS
# ===================================================================

def mann_whitney(df, variable, groupvar):
    grps = df[groupvar].dropna().unique()
    if len(grps) != 2:
        return dict(error=f"Need 2 groups, found {len(grps)}")
    g1 = pd.to_numeric(df.loc[df[groupvar]==grps[0], variable], errors="coerce").dropna()
    g2 = pd.to_numeric(df.loc[df[groupvar]==grps[1], variable], errors="coerce").dropna()
    u, p = sp.mannwhitneyu(g1, g2, alternative="two-sided")
    return dict(U=_R(u), p=_R(p), Group_1=str(grps[0]), n1=len(g1),
                Group_2=str(grps[1]), n2=len(g2), test="Mann-Whitney U")


def wilcoxon_signed(df, var1, var2):
    c1 = pd.to_numeric(df[var1], errors="coerce")
    c2 = pd.to_numeric(df[var2], errors="coerce")
    ok = c1.notna() & c2.notna()
    s, p = sp.wilcoxon(c1[ok], c2[ok])
    return dict(T=_R(s), p=_R(p), n=int(ok.sum()))


def kruskal_wallis(df, depvar, groupvar):
    grps, names = [], []
    for name, g in df.groupby(groupvar):
        v = pd.to_numeric(g[depvar], errors="coerce").dropna()
        if len(v) > 0: grps.append(v.values); names.append(str(name))
    h, p = sp.kruskal(*grps)
    return dict(H=_R(h), df=len(grps)-1, p=_R(p), groups=names, test="Kruskal-Wallis H")


# ===================================================================
# 7. CORRELATION
# ===================================================================

def correlation(df, variables, method="pearson"):
    tmp = df[variables].apply(pd.to_numeric, errors="coerce")
    corr = tmp.corr(method=method)
    n = len(tmp.dropna())
    pmat = pd.DataFrame(np.ones((len(variables),len(variables))),
                        index=variables, columns=variables)
    for i, v1 in enumerate(variables):
        for j, v2 in enumerate(variables):
            if i != j:
                ok = tmp[[v1,v2]].dropna()
                if len(ok) > 2:
                    fn = sp.spearmanr if method == "spearman" else sp.pearsonr
                    _, p = fn(ok[v1], ok[v2])
                    pmat.iloc[i,j] = round(p, 4)
    return dict(correlation=corr.round(4).to_dict(), correlation_str=corr.round(4).to_string(),
                p_values=pmat.round(4).to_dict(), p_str=pmat.round(4).to_string(),
                method=method, n=n)


# ===================================================================
# 8. POST-HOC TESTS
# ===================================================================

def tukey_hsd(df, depvar, groupvar):
    tmp = df[[depvar, groupvar]].dropna()
    tmp[depvar] = pd.to_numeric(tmp[depvar], errors="coerce"); tmp = tmp.dropna()
    res = pairwise_tukeyhsd(tmp[depvar], tmp[groupvar], alpha=0.05)
    comps = []
    for row in res.summary().data[1:]:
        comps.append(dict(Group1=str(row[0]), Group2=str(row[1]),
                          Mean_Diff=_R(float(row[2])), p_adj=_R(float(row[3])),
                          CI_Low=_R(float(row[4])), CI_High=_R(float(row[5])),
                          Reject=str(row[6])))
    return dict(test="Tukey HSD", comparisons=comps, summary=str(res), alpha=0.05)


def bonferroni(df, depvar, groupvar, alpha=0.05):
    tmp = df[[depvar, groupvar]].dropna()
    tmp[depvar] = pd.to_numeric(tmp[depvar], errors="coerce"); tmp = tmp.dropna()
    grps = tmp[groupvar].unique(); k = len(grps); nc = k*(k-1)//2
    comps = []
    for i in range(k):
        for j in range(i+1, k):
            g1 = tmp.loc[tmp[groupvar]==grps[i], depvar]
            g2 = tmp.loc[tmp[groupvar]==grps[j], depvar]
            t, p_raw = sp.ttest_ind(g1, g2)
            pb = min(p_raw*nc, 1.0)
            comps.append(dict(Group1=str(grps[i]), Group2=str(grps[j]),
                              Mean1=_R(g1.mean()), Mean2=_R(g2.mean()),
                              Mean_Diff=_R(g1.mean()-g2.mean()),
                              t=_R(t), p_raw=_R(p_raw), p_bonf=_R(pb),
                              Significant=pb < alpha))
    return dict(test="Bonferroni", comparisons=comps, n_comparisons=nc,
                alpha=alpha, alpha_corrected=_R(alpha/nc, 6))


# ===================================================================
# 9. REPEATED MEASURES
# ===================================================================

def repeated_anova(df, subject_var, within_vars):
    long = pd.melt(df[[subject_var]+within_vars].dropna(),
                   id_vars=[subject_var], value_vars=within_vars,
                   var_name="time", value_name="value")
    long["value"] = pd.to_numeric(long["value"], errors="coerce"); long = long.dropna()
    grps = [g["value"].values for _, g in long.groupby("time")]
    k = len(grps); n = df[subject_var].nunique()
    if k < 2: return dict(error="Need ≥2 time points")
    a = long["value"].values; gm = a.mean()
    sst = ((a-gm)**2).sum()
    ssb = n*sum((g.mean()-gm)**2 for g in grps)
    ss_subj = k*((long.groupby(subject_var)["value"].mean()-gm)**2).sum()
    sse = sst-ssb-ss_subj
    dfb, dfe = k-1, (k-1)*(n-1)
    msb = ssb/dfb if dfb else 0; mse = sse/dfe if dfe else 0
    f = msb/mse if mse else 0
    p = 1-sp.f.cdf(f, dfb, dfe) if f else 1.0
    eps = min(1.0, max(0.5, 1/(k-1)))
    p_gg = 1-sp.f.cdf(f, dfb*eps, dfe*eps)
    cs = [dict(Condition=within_vars[i], N=len(g), Mean=_R(g.mean()),
               SD=_R(g.std(ddof=1)), SE=_R(sp.sem(g))) for i, g in enumerate(grps)]
    return dict(test="Repeated Measures ANOVA", F=_R(f), p=_R(p), p_GG=_R(p_gg),
                epsilon_GG=_R(eps), condition_stats=cs, n_subjects=n, n_conditions=k,
                anova_table=dict(Source=["Between conditions","Subjects","Error","Total"],
                                 SS=[_R(ssb),_R(ss_subj),_R(sse),_R(sst)],
                                 df=[dfb,n-1,dfe,len(a)-1],
                                 MS=[_R(msb),"",_R(mse),""],
                                 F=[_R(f),"","",""], p=[_R(p),"","",""]))


def friedman(df, subject_var, within_vars):
    data = df[[subject_var]+within_vars].dropna()
    grps = [pd.to_numeric(data[v], errors="coerce").values for v in within_vars]
    k = len(grps); n = len(grps[0])
    if k < 3: return dict(error="Friedman needs ≥3 conditions")
    chi2, p = sp.friedmanchisquare(*grps)
    w = chi2/(n*(k-1)) if n*(k-1) else 0
    cs = [dict(Condition=within_vars[i], N=len(g), Median=_R(np.median(g)),
               Mean=_R(g.mean()), SD=_R(g.std(ddof=1))) for i, g in enumerate(grps)]
    return dict(test="Friedman", chi2=_R(chi2), df=k-1, p=_R(p), kendall_w=_R(w),
                n_subjects=n, n_conditions=k, condition_stats=cs,
                effect="Small" if w<0.3 else "Medium" if w<0.5 else "Large")


# ===================================================================
# 10. POWER & SAMPLE SIZE
# ===================================================================

def power_ttest(n=None, delta=None, sd=1, alpha=0.05, power=None):
    from scipy.stats import t as tdist
    if power is None and n and delta:
        se = sd*np.sqrt(2.0/n); ncp = abs(delta)/se
        crit = tdist.ppf(1-alpha/2, df=2*n-2)
        pw = 1-tdist.cdf(crit-ncp, 2*n-2)+tdist.cdf(-crit-ncp, 2*n-2)
        return dict(power=_R(pw), n=n, delta=delta, sd=sd, alpha=alpha)
    if n is None and delta and power:
        for nt in range(4, 100000):
            se = sd*np.sqrt(2.0/nt); ncp = abs(delta)/se
            crit = tdist.ppf(1-alpha/2, df=2*nt-2)
            pw = 1-tdist.cdf(crit-ncp, 2*nt-2)+tdist.cdf(-crit-ncp, 2*nt-2)
            if pw >= power:
                return dict(n_per_group=nt, total_n=2*nt, power=_R(pw),
                            delta=delta, sd=sd, alpha=alpha)
        return dict(error="No solution in range")
    return dict(error="Supply (n,delta,sd) for power or (delta,sd,power) for n")


def power_anova(k, n=None, f_effect=None, alpha=0.05, power=None):
    from scipy.stats import f as fdist, ncf
    if power is None and n and f_effect:
        lam = n*k*f_effect**2; df1=k-1; df2=k*(n-1)
        pw = 1-ncf.cdf(fdist.ppf(1-alpha,df1,df2), df1, df2, lam)
        return dict(power=_R(pw), n_per_group=n, total_n=n*k, k=k,
                    f_effect=f_effect, alpha=alpha)
    if n is None and f_effect and power:
        for nt in range(3, 50000):
            lam = nt*k*f_effect**2; df1=k-1; df2=k*(nt-1)
            pw = 1-ncf.cdf(fdist.ppf(1-alpha,df1,df2), df1, df2, lam)
            if pw >= power:
                return dict(n_per_group=nt, total_n=nt*k, power=_R(pw),
                            k=k, f_effect=f_effect, alpha=alpha)
        return dict(error="No solution in range")
    return dict(error="Supply appropriate parameters")


def power_chi2(w, n=None, df=1, alpha=0.05, power=None):
    from scipy.stats import chi2 as chi2d, ncx2
    if power is None and n:
        lam = n*w**2; pw = 1-ncx2.cdf(chi2d.ppf(1-alpha,df), df, lam)
        return dict(power=_R(pw), n=n, w=w, df=df, alpha=alpha)
    if n is None and power:
        for nt in range(5, 100000):
            lam = nt*w**2; pw = 1-ncx2.cdf(chi2d.ppf(1-alpha,df), df, lam)
            if pw >= power:
                return dict(n=nt, power=_R(pw), w=w, df=df, alpha=alpha)
        return dict(error="No solution in range")
    return dict(error="Supply appropriate parameters")


def sample_size_means(delta, sd, alpha=0.05, power=0.80, ratio=1):
    from scipy.stats import norm
    za = norm.ppf(1-alpha/2); zb = norm.ppf(power)
    n1 = ((za+zb)**2 * sd**2 * (1+1/ratio)) / delta**2
    n2 = n1/ratio
    return dict(n1=int(np.ceil(n1)), n2=int(np.ceil(n2)),
                total=int(np.ceil(n1)+np.ceil(n2)),
                delta=delta, sd=sd, alpha=alpha, power=power, ratio=ratio)


def sample_size_proportions(p1, p2, alpha=0.05, power=0.80, ratio=1):
    from scipy.stats import norm
    za = norm.ppf(1-alpha/2); zb = norm.ppf(power)
    pb = (p1+ratio*p2)/(1+ratio)
    n1 = ((za*np.sqrt((1+1/ratio)*pb*(1-pb)) +
           zb*np.sqrt(p1*(1-p1)+p2*(1-p2)/ratio))**2) / (p1-p2)**2
    n2 = n1/ratio
    return dict(n1=int(np.ceil(n1)), n2=int(np.ceil(n2)),
                total=int(np.ceil(n1)+np.ceil(n2)),
                p1=p1, p2=p2, alpha=alpha, power=power)


# ===================================================================
# 11. SURVIVAL ANALYSIS
# ===================================================================

def kaplan_meier(df, time_var, event_var, group_var=None):
    try:
        from lifelines import KaplanMeierFitter
        from lifelines.statistics import logrank_test
    except ImportError:
        return dict(error="lifelines package required")
    tmp = df[[time_var, event_var]+([] if group_var is None else [group_var])].dropna()
    tmp[time_var] = pd.to_numeric(tmp[time_var], errors="coerce")
    tmp[event_var] = pd.to_numeric(tmp[event_var], errors="coerce"); tmp = tmp.dropna()
    res = {}
    if group_var is None:
        kmf = KaplanMeierFitter(); kmf.fit(tmp[time_var], tmp[event_var])
        res["survival_table"] = kmf.survival_function_.to_string()
        res["median"] = str(kmf.median_survival_time_); res["n"] = len(tmp)
    else:
        grps = tmp[group_var].unique(); tables={}; medians={}
        for g in grps:
            m = tmp[group_var]==g; kmf = KaplanMeierFitter()
            kmf.fit(tmp.loc[m, time_var], tmp.loc[m, event_var], label=str(g))
            tables[str(g)] = kmf.survival_function_.to_string()
            medians[str(g)] = str(kmf.median_survival_time_)
        res["survival_tables"]=tables; res["medians"]=medians
        if len(grps)==2:
            m1=tmp[group_var]==grps[0]; m2=tmp[group_var]==grps[1]
            lr = logrank_test(tmp.loc[m1,time_var], tmp.loc[m2,time_var],
                              tmp.loc[m1,event_var], tmp.loc[m2,event_var])
            res["logrank"] = dict(stat=_R(lr.test_statistic), p=_R(lr.p_value))
    return res


def cox_regression(df, time_var, event_var, covariates):
    try:
        from lifelines import CoxPHFitter
    except ImportError:
        return dict(error="lifelines package required")
    cols = [time_var, event_var]+covariates
    tmp = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    cph = CoxPHFitter(); cph.fit(tmp, duration_col=time_var, event_col=event_var)
    coefs = {r: dict(coef=_R(cph.summary.loc[r,"coef"],6),
                     HR=_R(cph.summary.loc[r,"exp(coef)"]),
                     se=_R(cph.summary.loc[r,"se(coef)"],6),
                     z=_R(cph.summary.loc[r,"z"]), p=_R(cph.summary.loc[r,"p"]))
             for r in cph.summary.index}
    return dict(summary=cph.summary.to_string(), coefficients=coefs,
                concordance=_R(cph.concordance_index_), ll=_R(cph.log_likelihood_), n=len(tmp))


# ===================================================================
# 12. NORMALITY
# ===================================================================

def normality(df, variable):
    col = pd.to_numeric(df[variable], errors="coerce").dropna()
    sk_z, sk_p = sp.skewtest(col)
    ku_z, ku_p = sp.kurtosistest(col)
    chi2 = sk_z**2 + ku_z**2
    p_comb = 1 - sp.chi2.cdf(chi2, df=2)
    sw_w, sw_p = sp.shapiro(col) if len(col) <= 5000 else (np.nan, np.nan)
    return dict(Variable=variable, Obs=len(col),
                Skew_z=_R(sk_z), Skew_p=_R(sk_p),
                Kurt_z=_R(ku_z), Kurt_p=_R(ku_p),
                chi2=_R(chi2), p_combined=_R(p_comb),
                SW_W=_R(sw_w) if not np.isnan(sw_w) else None,
                SW_p=_R(sw_p) if not np.isnan(sw_p) else None)


# ===================================================================
# 13. DATA UTILITIES
# ===================================================================

def detect_variable_types(df):
    rows = []
    for i, col in enumerate(df.columns):
        s = df.iloc[:, i]
        if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
        n_total = len(s); n_miss = int(s.isna().sum()); n_valid = n_total - n_miss
        n_uniq = int(s.nunique())
        try:
            num = pd.to_numeric(s, errors="coerce")
        except (TypeError, AttributeError):
            num = pd.Series([np.nan]*n_total)
        n_num = int(num.notna().sum())
        ratio = n_num / max(n_valid, 1)
        if ratio > 0.8 and n_uniq > 10:
            vtype = "continuous"
        elif n_uniq <= 20 or ratio <= 0.5:
            vtype = "categorical"
        else:
            vtype = "continuous"
        ex = str(s.dropna().iloc[0]) if n_valid > 0 else "N/A"
        rows.append(dict(Variable=col, Type=vtype, N=n_valid,
                         Missing=n_miss, Unique=n_uniq, Example=ex))
    return pd.DataFrame(rows)


def clean_data(df):
    c = df.copy()
    for i in range(len(c.columns)):
        s = c.iloc[:, i]
        if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
        try:
            if s.dtype == object: c.iloc[:, i] = s.str.strip()
        except AttributeError:
            pass
    c.columns = [str(x).strip().replace(" ", "_") for x in c.columns]
    return c


# ===================================================================
# 14. SMART STATISTICAL ROUTER
# ===================================================================

_TEMPORAL = ['pre','post','before','after','baseline','followup','follow_up',
    'time1','time2','time3','time4','t1','t2','t3','t4',
    'week1','week2','week3','w1','w2','w3',
    'day1','day2','day3','d1','d2','d3',
    'visit1','visit2','visit3','v1','v2','v3',
    'month1','month2','month3','m1','m2','m3',
    '_0','_1','_2','_3','initial','final','start','end']


def _classify(s, name):
    if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
    n_valid = s.dropna().shape[0]
    if n_valid == 0: return "unknown"
    num = pd.to_numeric(s, errors="coerce"); r = num.notna().sum()/n_valid; u = s.nunique()
    if u <= 2: return "categorical"
    if u <= 10 and r < 0.9: return "categorical"
    if r < 0.5: return "categorical"
    if r > 0.8 and u > 15: return "continuous"
    if r > 0.9 and u > 10: return "continuous"
    return "continuous" if r > 0.7 else "categorical"


def _temporal_cols(cols):
    out = []
    for c in cols:
        cl = str(c).lower()
        if any(kw in cl for kw in _TEMPORAL): out.append(c)
    return out


def _find_grouper(df, cols):
    cats = [c for c in cols if _classify(df[c], c) == "categorical"]
    conts = [c for c in cols if _classify(df[c], c) == "continuous"]
    if len(cats) == 1 and conts: return cats[0], conts
    if len(cats) > 1 and conts:
        best = min(cats, key=lambda c: df[c].nunique() if 2 <= df[c].nunique() <= 10 else 999, default=None)
        if best: return best, [c for c in cols if c != best]
    return None, cols


def _is_normal(s, alpha=0.05):
    d = pd.to_numeric(s, errors="coerce").dropna()
    if len(d) < 3: return True, 1.0
    try:
        _, p = sp.shapiro(d) if len(d) <= 5000 else sp.normaltest(d)
        return p > alpha, p
    except: return True, 1.0


def _var_equal(groups, alpha=0.05):
    if len(groups) < 2: return True, 1.0
    try:
        _, p = sp.levene(*groups); return p > alpha, p
    except: return True, 1.0


def smart_analysis(df, columns, subject_var=None, alpha=0.05):
    """Auto-select the right test based on variable types and assumptions."""
    if not columns: return dict(error="No columns selected")
    vt = {c: _classify(df[c], c) for c in columns}
    conts = [c for c in columns if vt[c] == "continuous"]
    cats = [c for c in columns if vt[c] == "categorical"]
    temps = _temporal_cols(columns)
    res = dict(variable_types=vt, continuous=conts, categorical=cats,
               temporal=temps, reasoning=[], test_name=None, test_result=None, posthoc=None)
    R = res["reasoning"]

    # All continuous → correlation
    if len(conts) >= 2 and not cats:
        R.append("Multiple continuous variables → Correlation")
        ok = all(_is_normal(df[c])[0] for c in conts[:2])
        method = "pearson" if ok else "spearman"
        R.append(f"Using {method.title()}")
        res["test_name"] = f"{method.title()} Correlation"
        res["test_result"] = correlation(df, conts, method); return res

    # Two categorical → chi-square / Fisher
    if len(cats) == 2 and not conts:
        ct = pd.crosstab(df[cats[0]], df[cats[1]])
        _, _, _, exp = sp.chi2_contingency(ct)
        if ct.shape == (2,2) and exp.min() < 5:
            R.append("2×2 with expected<5 → Fisher's Exact")
            res["test_name"] = "Fisher's Exact"; res["test_result"] = fisher_exact(df, cats[0], cats[1])
        else:
            R.append("Categorical → Chi-Square")
            res["test_name"] = "Chi-Square"; res["test_result"] = chi_square(df, cats[0], cats[1])
        return res

    # One cat + one cont → t-test / ANOVA or non-parametric
    if len(cats) == 1 and len(conts) == 1:
        gv, ov = cats[0], conts[0]; ng = df[gv].nunique()
        R.append(f"Grouping: {gv} ({ng} groups), Outcome: {ov}")
        grps = [pd.to_numeric(g[ov], errors="coerce").dropna().values
                for _, g in df.groupby(gv) if len(pd.to_numeric(g[ov], errors="coerce").dropna()) > 0]
        ok = all(_is_normal(pd.Series(g))[0] for g in grps)
        eq, _ = _var_equal(grps)
        if ng == 2:
            if ok:
                R.append("Normal → t-test" + (" (Welch)" if not eq else ""))
                res["test_name"] = "Two-Sample t-test"
                res["test_result"] = ttest_two(df, ov, gv, equal_var=eq)
            else:
                R.append("Non-normal → Mann-Whitney U")
                res["test_name"] = "Mann-Whitney U"
                res["test_result"] = mann_whitney(df, ov, gv)
        elif ng > 2:
            if ok:
                R.append("Normal → One-way ANOVA")
                res["test_name"] = "One-way ANOVA"
                res["test_result"] = oneway_anova(df, ov, gv)
                if res["test_result"].get("p", 1) < alpha:
                    R.append("Significant → Tukey HSD")
                    res["posthoc"] = tukey_hsd(df, ov, gv)
            else:
                R.append("Non-normal → Kruskal-Wallis")
                res["test_name"] = "Kruskal-Wallis"
                res["test_result"] = kruskal_wallis(df, ov, gv)
                if res["test_result"].get("p", 1) < alpha:
                    R.append("Significant → Bonferroni post-hoc")
                    res["posthoc"] = bonferroni(df, ov, gv)
        return res

    # Temporal / paired
    if len(temps) >= 2:
        tc = [c for c in temps if vt.get(c) == "continuous"]
        if len(tc) == 2:
            v1, v2 = tc
            d = pd.to_numeric(df[v1], errors="coerce") - pd.to_numeric(df[v2], errors="coerce")
            ok, _ = _is_normal(d.dropna())
            if ok:
                R.append("Paired normal → Paired t-test")
                res["test_name"] = "Paired t-test"; res["test_result"] = ttest_paired(df, v1, v2)
            else:
                R.append("Paired non-normal → Wilcoxon")
                res["test_name"] = "Wilcoxon Signed-Rank"; res["test_result"] = wilcoxon_signed(df, v1, v2)
            return res
        if len(tc) >= 3 and subject_var:
            ok = all(_is_normal(df[c])[0] for c in tc)
            if ok:
                R.append("Repeated normal → RM-ANOVA")
                res["test_name"] = "Repeated Measures ANOVA"
                res["test_result"] = repeated_anova(df, subject_var, tc)
            else:
                R.append("Repeated non-normal → Friedman")
                res["test_name"] = "Friedman"; res["test_result"] = friedman(df, subject_var, tc)
            return res

    # Auto-detect grouper
    if len(columns) >= 2:
        gv, ovs = _find_grouper(df, columns)
        if gv and ovs:
            R.append(f"Auto grouper: {gv}")
            if len(ovs) == 1:
                return smart_analysis(df, [gv, ovs[0]], subject_var, alpha)
            res["test_name"] = "Multiple Outcomes"
            res["test_result"] = {o: smart_analysis(df, [gv, o], subject_var, alpha) for o in ovs}
            return res

    # Single variable
    if len(conts) == 1 and not cats:
        R.append("Single continuous → Descriptive")
        res["test_name"] = "Descriptive"
        res["test_result"] = descriptive(df, conts, detail=True).to_dict("records")
        return res
    if len(cats) == 1 and not conts:
        R.append("Single categorical → Frequency")
        res["test_name"] = "Frequency"; res["test_result"] = tabulate(df, cats[0]).to_dict("records")
        return res

    R.append("Could not auto-detect — please choose manually")
    res["test_name"] = "Manual Selection Required"
    return res


# ===================================================================
# TEST CATALOG
# ===================================================================

AVAILABLE_TESTS = {
    "descriptive":     dict(fn="descriptive",          desc="Descriptive statistics",            stata="summarize"),
    "tabulate":        dict(fn="tabulate",             desc="Frequency / cross-tab",             stata="tabulate"),
    "normality":       dict(fn="normality",            desc="Normality (Shapiro-Wilk, sktest)",  stata="sktest / swilk"),
    "ttest_one":       dict(fn="ttest_one",            desc="One-sample t-test",                 stata="ttest var == #"),
    "ttest_two":       dict(fn="ttest_two",            desc="Two-sample t-test",                 stata="ttest var, by(grp)"),
    "ttest_paired":    dict(fn="ttest_paired",         desc="Paired t-test",                     stata="ttest v1 == v2"),
    "oneway_anova":    dict(fn="oneway_anova",         desc="One-way ANOVA",                     stata="oneway y g"),
    "twoway_anova":    dict(fn="twoway_anova",         desc="Two-way ANOVA",                     stata="anova y a b a#b"),
    "chi_square":      dict(fn="chi_square",           desc="Chi-square independence",           stata="tab v1 v2, chi2"),
    "fisher_exact":    dict(fn="fisher_exact",         desc="Fisher's Exact (2×2)",              stata="tab v1 v2, exact"),
    "regression":      dict(fn="ols_regression",       desc="OLS regression",                    stata="regress y x1 x2"),
    "logistic":        dict(fn="logistic_regression",  desc="Logistic regression",               stata="logit y x1 x2"),
    "probit":          dict(fn="probit_regression",    desc="Probit regression",                 stata="probit y x1 x2"),
    "mann_whitney":    dict(fn="mann_whitney",         desc="Mann-Whitney U",                    stata="ranksum"),
    "wilcoxon":        dict(fn="wilcoxon_signed",      desc="Wilcoxon signed-rank",              stata="signrank"),
    "kruskal_wallis":  dict(fn="kruskal_wallis",       desc="Kruskal-Wallis H",                  stata="kwallis"),
    "correlation":     dict(fn="correlation",          desc="Correlation matrix",                stata="pwcorr"),
    "tukey_hsd":       dict(fn="tukey_hsd",            desc="Tukey HSD post-hoc",                stata="oneway y g, tukey"),
    "bonferroni":      dict(fn="bonferroni",           desc="Bonferroni post-hoc",               stata="oneway y g, bonf"),
    "repeated_anova":  dict(fn="repeated_anova",       desc="Repeated measures ANOVA",           stata="anova y s t, rep(t)"),
    "friedman":        dict(fn="friedman",             desc="Friedman test",                     stata="friedman"),
    "kaplan_meier":    dict(fn="kaplan_meier",         desc="Kaplan-Meier survival",             stata="sts graph"),
    "cox":             dict(fn="cox_regression",       desc="Cox PH regression",                 stata="stcox"),
    "power_ttest":     dict(fn="power_ttest",          desc="Power for t-test",                  stata="power twomeans"),
    "power_anova":     dict(fn="power_anova",          desc="Power for ANOVA",                   stata="power oneway"),
    "power_chi2":      dict(fn="power_chi2",           desc="Power for χ²",                      stata="power cmh"),
    "sample_size_means":       dict(fn="sample_size_means",       desc="Sample size (means)",    stata="power twomeans"),
    "sample_size_proportions": dict(fn="sample_size_proportions", desc="Sample size (props)",    stata="power twoprop"),
    "smart_analysis":  dict(fn="smart_analysis",       desc="Auto-select test",                  stata="auto"),
}

def list_tests():
    return {k: dict(desc=v["desc"], stata=v["stata"]) for k, v in AVAILABLE_TESTS.items()}
