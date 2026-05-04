"""
SolarSTATA AI Brain
AI-powered statistical analysis engine with internet research capabilities.

Modules
-------
 1  Text Parsing        -- extract Mean/SD from text, Cohen's d, sample-size
 2  Proposal Context    -- RAG storage / variable extraction / citation check
 3  Web Research        -- PubMed + CrossRef literature search
 4  Data Intelligence   -- structure detection, test suggestions
 5  Smart Cleaning      -- MultiIndex, header promotion, dedup, type coercion
 6  AI Analysis Engine  -- master analysis, automated fallback, quick_analyze,
                           AI-assisted sample-size calculation

AI calls are routed through agent_core (never import ollama directly).
"""

import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.formula.api import ols
from scipy import stats as sp_stats
from scipy.stats import norm
import sys
import io
import json
import re
import requests

import stats_engine as se

# ---------------------------------------------------------------------------
# Agent core bridge -- graceful degradation when agent_core is absent
# ---------------------------------------------------------------------------
try:
    from agent_core import call_agent, is_ollama_available
except ImportError:
    def call_agent(prompt, system_prompt=None, timeout=120):
        return {"success": False, "error": "agent_core not available"}

    def is_ollama_available():
        return False


# =========================================================================
# 1. TEXT PARSING MODULE -- extract Mean/SD from text
# =========================================================================

def extract_mean_sd_from_text(text):
    """
    Parse free-form text and extract Mean / Standard-Deviation pairs.

    Recognised patterns
    -------------------
    * ``Mean = X, SD = Y``  /  ``Mean: X, SD: Y``
    * ``M=X (SD=Y)``  /  ``M = X (SD = Y)``
    * ``X +/- Y``  (or ``X +- Y``)
    * ``<group label>: X (Y)``
    * Table rows: ``Control | 5.2 | 1.3``

    Returns a de-duplicated list of dicts::

        [{"group": str, "mean": float, "sd": float, "source": str}, ...]
    """
    results = []

    # Pattern 1: Mean = X, SD = Y  or  Mean: X, SD: Y
    pat1 = (
        r'[Mm]ean\s*[=:]\s*([\d.]+)\s*[,;]?\s*'
        r'(?:SD|sd|S\.D\.|Std\.?\s*Dev\.?)\s*[=:]\s*([\d.]+)'
    )
    for m in re.finditer(pat1, text):
        results.append({
            "group": "extracted",
            "mean": float(m.group(1)),
            "sd": float(m.group(2)),
            "source": m.group(0),
        })

    # Pattern 2: M=X (SD=Y)  or  M = X (SD = Y)
    pat2 = r'M\s*=\s*([\d.]+)\s*\((?:SD|sd)\s*=\s*([\d.]+)\)'
    for m in re.finditer(pat2, text):
        results.append({
            "group": "extracted",
            "mean": float(m.group(1)),
            "sd": float(m.group(2)),
            "source": m.group(0),
        })

    # Pattern 3: X +/- Y  or  X +- Y  (mean +/- SD)
    pat3 = r'([\d.]+)\s*[+-]+/?[+-]*\s*([\d.]+)'
    for m in re.finditer(pat3, text):
        mean_val = float(m.group(1))
        sd_val = float(m.group(2))
        if 0 < sd_val < mean_val * 10:
            results.append({
                "group": "extracted",
                "mean": mean_val,
                "sd": sd_val,
                "source": m.group(0),
            })

    # Pattern 4: labelled groups --  "Control: 5.2 (1.3)"
    pat4 = (
        r'([A-Za-z]+\s*(?:\d+)?(?:\s*group)?)\s*[:\-]\s*'
        r'(?:[Mm]ean\s*)?(\d+\.?\d*)\s*[\(\s,]*'
        r'(?:SD|sd|S\.D\.)?\s*[=:]?\s*(\d+\.?\d*)'
    )
    for m in re.finditer(pat4, text, re.IGNORECASE):
        try:
            group = m.group(1).strip()
            mean_val = float(m.group(2))
            sd_val = float(m.group(3))
            if 0 < sd_val < mean_val * 10:
                results.append({
                    "group": group,
                    "mean": mean_val,
                    "sd": sd_val,
                    "source": m.group(0),
                })
        except (ValueError, IndexError):
            pass

    # Pattern 5: table-like rows  (control | 5.2 | 1.3)
    for line in text.split('\n'):
        m = re.search(
            r'(control|experimental|treatment|placebo|'
            r'group\s*\d*|intervention)'
            r'\s*[:\|\t,]+\s*([\d.]+)\s*[:\|\t,]+\s*([\d.]+)',
            line, re.IGNORECASE,
        )
        if m:
            try:
                results.append({
                    "group": m.group(1).strip(),
                    "mean": float(m.group(2)),
                    "sd": float(m.group(3)),
                    "source": line.strip(),
                })
            except ValueError:
                pass

    # De-duplicate on (mean, sd)
    seen = set()
    unique = []
    for r in results:
        key = (round(r["mean"], 4), round(r["sd"], 4))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def calculate_cohens_d(mean1, sd1, mean2, sd2, n1=None, n2=None):
    """
    Cohen's d effect size between two groups.

    If *n1* and *n2* are provided the pooled SD uses the classic weighted
    formula; otherwise the root-mean-square of the two SDs is used.
    """
    try:
        if n1 and n2:
            pooled_sd = np.sqrt(
                ((n1 - 1) * sd1 ** 2 + (n2 - 1) * sd2 ** 2) / (n1 + n2 - 2)
            )
        else:
            pooled_sd = np.sqrt((sd1 ** 2 + sd2 ** 2) / 2)
        if pooled_sd == 0:
            return 0.0
        return round(abs(mean1 - mean2) / pooled_sd, 4)
    except Exception:
        return 0.0


def calculate_sample_size_from_text(text, alpha=0.05, power=0.80):
    """
    Parse *text* for two Mean/SD pairs and return the required
    sample-size using the normal-approximation formula.

    Formula:  N_per_group = 2 * sigma^2 * (Z_{alpha/2} + Z_beta)^2 / delta^2
    """
    extracted = extract_mean_sd_from_text(text)

    if len(extracted) < 2:
        return {
            "error": "Could not extract at least 2 groups with Mean/SD values",
            "extracted_values": extracted,
            "hint": (
                "Text should contain values like 'Mean = X, SD = Y' "
                "for each group"
            ),
        }

    g1, g2 = extracted[0], extracted[1]
    mean1, sd1 = g1["mean"], g1["sd"]
    mean2, sd2 = g2["mean"], g2["sd"]

    cohens_d = calculate_cohens_d(mean1, sd1, mean2, sd2)
    pooled_sd = np.sqrt((sd1 ** 2 + sd2 ** 2) / 2)
    delta = abs(mean1 - mean2)

    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)

    if delta > 0:
        n_per_group = int(
            np.ceil(2 * pooled_sd ** 2 * (z_alpha + z_beta) ** 2 / delta ** 2)
        )
    else:
        n_per_group = None

    return {
        "group1": {
            "name": g1.get("group", "Group 1"),
            "mean": mean1,
            "sd": sd1,
            "source": g1.get("source", ""),
        },
        "group2": {
            "name": g2.get("group", "Group 2"),
            "mean": mean2,
            "sd": sd2,
            "source": g2.get("source", ""),
        },
        "effect_size": {
            "cohens_d": cohens_d,
            "interpretation": (
                "Small" if cohens_d < 0.5
                else "Medium" if cohens_d < 0.8
                else "Large"
            ),
        },
        "calculation": {
            "mean_difference": round(delta, 4),
            "pooled_sd": round(pooled_sd, 4),
            "alpha": alpha,
            "power": power,
            "z_alpha": round(z_alpha, 4),
            "z_beta": round(z_beta, 4),
            "n_per_group": n_per_group,
            "total_n": n_per_group * 2 if n_per_group else None,
            "formula": "N = 2 * sigma^2 * (Z_alpha/2 + Z_beta)^2 / delta^2",
        },
        "all_extracted": extracted,
    }


# =========================================================================
# 2. PROPOSAL CONTEXT MODULE (RAG)
# =========================================================================

_proposal_context = {
    "text": "",
    "variables": {},
    "methodology": "",
    "citations": [],
}


def set_proposal_context(text):
    """
    Store research-proposal text and extract structured elements.

    Extracts
    --------
    * Variable names (via heuristic regex)
    * Methodology section (first 100--500 char fragment after keyword)
    * In-text citations  ``(Author, 2020)`` or ``Author (2020)``
    """
    global _proposal_context

    _proposal_context["text"] = text

    # ---- variables ----
    var_patterns = [
        r'(?:variable|measure|assess|evaluate|compare)\s+'
        r'([A-Za-z_][A-Za-z0-9_\s]+)',
        r'([A-Za-z_][A-Za-z0-9_]+)\s+(?:levels?|values?|scores?)',
        r'(?:group\s*\d*|control|treatment|experimental|'
        r'intervention|placebo)',
    ]
    variables = []
    for pat in var_patterns:
        variables.extend(re.findall(pat, text, re.IGNORECASE))
    _proposal_context["variables"] = list(
        set(v.strip() for v in variables if len(v.strip()) > 2)
    )

    # ---- methodology ----
    meth = re.search(
        r'(?:method(?:ology)?|procedure|design)[:\s]+(.{100,500})',
        text, re.IGNORECASE | re.DOTALL,
    )
    if meth:
        _proposal_context["methodology"] = meth.group(1).strip()

    # ---- citations ----
    cite_pats = [
        r'\(([A-Za-z]+(?:\s+et\s+al\.?)?,?\s*\d{4})\)',
        r'([A-Za-z]+(?:\s+et\s+al\.?)?\s*\(\d{4}\))',
    ]
    citations = []
    for pat in cite_pats:
        citations.extend(re.findall(pat, text))
    _proposal_context["citations"] = list(set(citations))

    return {
        "stored": True,
        "text_length": len(text),
        "variables_detected": _proposal_context["variables"],
        "citations_found": len(_proposal_context["citations"]),
        "methodology_extracted": bool(_proposal_context["methodology"]),
    }


def get_proposal_context():
    """Return the currently stored proposal context dict."""
    return _proposal_context


def map_variables_to_data(df, proposal_text=""):
    """
    Cross-reference proposal variables with dataframe columns.

    Returns a dict with ``mappings`` (proposal_variable -> data_column)
    plus lists of unmapped items on each side.
    """
    ctx = get_proposal_context()
    if proposal_text:
        set_proposal_context(proposal_text)
        ctx = get_proposal_context()

    data_columns = [str(c).lower() for c in df.columns]
    proposal_vars = [v.lower() for v in ctx.get("variables", [])]

    mappings = []
    for pvar in proposal_vars:
        best_match = None
        best_score = 0
        for dcol in data_columns:
            score = 0
            if pvar in dcol or dcol in pvar:
                score = len(set(pvar.split()) & set(dcol.split())) + 1
            elif any(word in dcol for word in pvar.split()):
                score = 0.5
            if score > best_score:
                best_score = score
                best_match = dcol
        if best_match and best_score > 0:
            mappings.append({
                "proposal_variable": pvar,
                "data_column": best_match,
                "confidence": "high" if best_score > 1 else "medium",
            })

    mapped_pvars = {m["proposal_variable"] for m in mappings}
    mapped_dcols = {m["data_column"] for m in mappings}
    return {
        "mappings": mappings,
        "unmapped_proposal_vars": [
            v for v in proposal_vars if v not in mapped_pvars
        ],
        "unmapped_data_cols": [
            c for c in data_columns if c not in mapped_dcols
        ],
    }


def check_references(proposal_text=""):
    """
    Analyse the citations found in the proposal and return quality
    indicators plus improvement suggestions.
    """
    ctx = get_proposal_context()
    if proposal_text:
        set_proposal_context(proposal_text)
        ctx = get_proposal_context()

    citations = ctx.get("citations", [])

    analysis = {
        "total_citations": len(citations),
        "citations_list": citations,
        "suggestions": [],
        "quality_indicators": {},
    }

    if len(citations) < 5:
        analysis["suggestions"].append(
            "Consider adding more references (minimum 10-15 for most research)"
        )

    years = []
    for cite in citations:
        ym = re.search(r'\d{4}', cite)
        if ym:
            years.append(int(ym.group()))

    if years:
        avg_year = sum(years) / len(years)
        oldest = min(years)
        newest = max(years)
        analysis["quality_indicators"] = {
            "average_year": round(avg_year, 1),
            "oldest_reference": oldest,
            "newest_reference": newest,
            "years_span": newest - oldest,
        }
        if avg_year < 2018:
            analysis["suggestions"].append(
                "Consider updating references - average year is quite old"
            )
        if newest < 2022:
            analysis["suggestions"].append(
                "Add more recent references (2022-2024)"
            )

    return analysis


# =========================================================================
# 3. WEB RESEARCH MODULE
# =========================================================================

def search_literature(query, max_results=5):
    """
    Search PubMed (E-utilities) and CrossRef for academic papers matching
    *query*.  Returns a combined list of result dicts.

    Each dict has at least: ``source``, ``title``, ``authors``, ``year``,
    ``journal``.  PubMed entries also have ``pmid``; CrossRef entries have
    ``doi``.
    """
    results = []

    # ---- PubMed ----
    try:
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }
        resp = requests.get(search_url, params=params, timeout=10)
        if resp.status_code == 200:
            ids = resp.json().get("esearchresult", {}).get("idlist", [])
            if ids:
                sum_url = (
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
                    "esummary.fcgi"
                )
                sum_params = {
                    "db": "pubmed",
                    "id": ",".join(ids),
                    "retmode": "json",
                }
                sum_resp = requests.get(sum_url, params=sum_params, timeout=10)
                if sum_resp.status_code == 200:
                    sum_data = sum_resp.json().get("result", {})
                    for pid in ids:
                        article = sum_data.get(pid, {})
                        if isinstance(article, dict):
                            results.append({
                                "source": "PubMed",
                                "pmid": pid,
                                "title": article.get("title", "N/A"),
                                "journal": article.get(
                                    "fulljournalname", "N/A"
                                ),
                                "year": article.get("pubdate", "N/A")[:4],
                                "authors": article.get(
                                    "sortfirstauthor", "N/A"
                                ),
                            })
    except Exception as exc:
        results.append({"source": "PubMed", "error": str(exc)})

    # ---- CrossRef ----
    try:
        cr_url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "rows": max_results,
            "sort": "relevance",
        }
        headers = {"User-Agent": "SolarSTATA/1.0 (research tool)"}
        resp = requests.get(cr_url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                title_list = item.get("title", ["N/A"])
                title = title_list[0] if title_list else "N/A"
                authors = item.get("author", [])
                author_str = "; ".join(
                    f"{a.get('family', '')}, {a.get('given', '')}"
                    for a in authors[:3]
                )
                year = ""
                dp = item.get(
                    "published-print",
                    item.get("published-online", {}),
                )
                if dp and "date-parts" in dp and dp["date-parts"]:
                    parts = dp["date-parts"][0]
                    if parts:
                        year = str(parts[0])
                ct = item.get("container-title", ["N/A"])
                results.append({
                    "source": "CrossRef",
                    "title": title,
                    "authors": author_str,
                    "year": year,
                    "doi": item.get("DOI", "N/A"),
                    "journal": ct[0] if ct else "N/A",
                })
    except Exception as exc:
        results.append({"source": "CrossRef", "error": str(exc)})

    return results


def search_sample_size_references(study_type, test_type, subject_type=""):
    """
    Search literature for sample-size references matching the study
    design.  Returns literature hits plus general recommendations.
    """
    query = f"sample size {test_type} {study_type} {subject_type}".strip()
    try:
        lit = search_literature(query, max_results=5)
    except Exception:
        lit = []

    recommendations = {
        "pilot_study": (
            "Recommended: 12-30 per group (Julious, 2005)"
        ),
        "rct_two_arm": (
            "Use power analysis: typically 30-100+ per arm "
            "depending on effect size"
        ),
        "survey": (
            "Consider design effect; typically 384 for 95% CI, "
            "50% proportion"
        ),
        "case_control": (
            "Match ratio 1:1 to 1:4; use Kelsey formula"
        ),
        "cohort": (
            "Depends on incidence; use Schoenfeld formula for "
            "survival outcomes"
        ),
    }

    return {
        "literature": lit,
        "general_recommendations": recommendations,
        "search_query": query,
    }


# =========================================================================
# 4. DATA INTELLIGENCE MODULE
# =========================================================================

def analyze_data_structure(df):
    """
    Inspect *df* and return a rich dict describing variable types,
    group candidates, outcome candidates, time candidates,
    repeated-measures indicators, and missing-data summary.

    Uses ``stats_engine.detect_variable_types`` under the hood.
    """
    try:
        info = se.detect_variable_types(df)
    except Exception:
        info = pd.DataFrame()

    n_rows, n_cols = df.shape

    try:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    except Exception:
        numeric_cols = []

    if not info.empty:
        categorical_cols = info[info["Type"] == "categorical"]["Variable"].tolist()
        continuous_cols = info[info["Type"] == "continuous"]["Variable"].tolist()
    else:
        categorical_cols = []
        continuous_cols = list(numeric_cols)

    # Group candidates (2..20 unique values)
    group_candidates = []
    for i, col in enumerate(df.columns):
        try:
            col_series = df.iloc[:, i]
            nunique = int(col_series.nunique())
            if 2 <= nunique <= 20:
                uvals = col_series.dropna().unique().tolist()[:10]
                uvals = [
                    str(v) if not isinstance(v, (int, float, str)) else v
                    for v in uvals
                ]
                group_candidates.append({
                    "column": str(col),
                    "n_groups": nunique,
                    "groups": uvals,
                })
        except Exception:
            pass

    # Outcome candidates (continuous with many unique values)
    outcome_candidates = []
    for c in continuous_cols:
        try:
            col_idx = list(df.columns).index(c)
            if int(df.iloc[:, col_idx].nunique()) > 10:
                outcome_candidates.append(c)
        except Exception:
            pass

    # Time candidates
    time_keywords = [
        "time", "date", "day", "week", "month", "year",
        "baseline", "follow", "pre", "post",
    ]
    time_candidates = []
    for col in df.columns:
        cl = str(col).lower()
        if any(t in cl for t in time_keywords):
            time_candidates.append(str(col))

    # Repeated measures hint
    repeated_kw = [
        "time", "visit", "day", "baseline", "immersion",
        "pre", "post", "week",
    ]
    has_repeated = any(
        any(t in str(c).lower() for t in repeated_kw) for c in df.columns
    )

    # Missing data summary
    missing_summary = {}
    for i, col in enumerate(df.columns):
        try:
            n_miss = int(df.iloc[:, i].isna().sum())
            if n_miss > 0:
                missing_summary[str(col)] = n_miss
        except Exception:
            pass

    return {
        "n_observations": n_rows,
        "n_variables": n_cols,
        "numeric_columns": [str(c) for c in numeric_cols],
        "categorical_columns": [str(c) for c in categorical_cols],
        "continuous_columns": [str(c) for c in continuous_cols],
        "group_candidates": group_candidates,
        "outcome_candidates": outcome_candidates,
        "time_candidates": time_candidates,
        "has_repeated_measures": has_repeated,
        "variable_info": info.to_dict("records") if not info.empty else [],
        "missing_summary": missing_summary,
    }


def suggest_tests(data_analysis, proposal_text=""):
    """
    Suggest statistical tests appropriate for the data structure
    described in *data_analysis* (as returned by
    ``analyze_data_structure``).

    Proposal text is scanned for keyword boosts (e.g. "chi-square",
    "ANOVA").
    """
    suggestions = []
    da = data_analysis

    # Always start with descriptives
    suggestions.append({
        "test": "descriptive",
        "reason": "Always start with descriptive statistics to understand your data",
        "priority": 1,
    })

    # Grouping + continuous outcome -> parametric / non-parametric
    if da.get("group_candidates") and da.get("outcome_candidates"):
        for gc in da["group_candidates"]:
            n_groups = gc["n_groups"]
            if n_groups == 2:
                suggestions.append({
                    "test": "ttest_two",
                    "reason": (
                        f"Compare means between 2 groups "
                        f"({gc['column']})"
                    ),
                    "params": {"groupvar": gc["column"]},
                    "priority": 2,
                })
                suggestions.append({
                    "test": "mann_whitney",
                    "reason": (
                        f"Non-parametric alternative if normality "
                        f"assumption violated ({gc['column']})"
                    ),
                    "params": {"groupvar": gc["column"]},
                    "priority": 3,
                })
            elif n_groups > 2:
                suggestions.append({
                    "test": "oneway_anova",
                    "reason": (
                        f"Compare means across {n_groups} groups "
                        f"({gc['column']})"
                    ),
                    "params": {"groupvar": gc["column"]},
                    "priority": 2,
                })
                suggestions.append({
                    "test": "kruskal_wallis",
                    "reason": (
                        f"Non-parametric alternative for {n_groups} "
                        f"groups ({gc['column']})"
                    ),
                    "params": {"groupvar": gc["column"]},
                    "priority": 3,
                })

    # Two categorical -> chi-square
    cats = da.get("categorical_columns", [])
    if len(cats) >= 2:
        suggestions.append({
            "test": "chi_square",
            "reason": "Test association between categorical variables",
            "params": {"var1": cats[0], "var2": cats[1]},
            "priority": 2,
        })

    # Multiple continuous -> correlation / regression
    cont = da.get("continuous_columns", [])
    if len(cont) >= 2:
        suggestions.append({
            "test": "correlation",
            "reason": "Examine relationships between continuous variables",
            "priority": 2,
        })
        if len(cont) >= 3:
            suggestions.append({
                "test": "regression",
                "reason": "Model outcome as function of predictors",
                "priority": 3,
            })

    # Keyword boosting from proposal
    proposal_lower = (proposal_text or "").lower()
    keyword_test_map = {
        "chi-square": "chi_square",
        "chi square": "chi_square",
        "chi2": "chi_square",
        "anova": "oneway_anova",
        "one-way": "oneway_anova",
        "one way": "oneway_anova",
        "two-way anova": "twoway_anova",
        "two way anova": "twoway_anova",
        "t-test": "ttest_two",
        "t test": "ttest_two",
        "regression": "regression",
        "linear regression": "regression",
        "logistic": "logistic",
        "logit": "logistic",
        "survival": "kaplan_meier",
        "kaplan": "kaplan_meier",
        "cox": "cox",
        "mann-whitney": "mann_whitney",
        "wilcoxon": "wilcoxon",
        "kruskal": "kruskal_wallis",
        "sample size": "sample_size_means",
        "power": "power_ttest",
        "correlation": "correlation",
        "spearman": "correlation",
    }
    for keyword, test in keyword_test_map.items():
        if keyword in proposal_lower:
            if not any(s["test"] == test for s in suggestions):
                suggestions.append({
                    "test": test,
                    "reason": f"Mentioned in proposal: '{keyword}'",
                    "priority": 1,
                })

    suggestions.sort(key=lambda x: x["priority"])
    return suggestions


# =========================================================================
# 5. SMART CLEANING MODULE
# =========================================================================

def _flatten_column(col):
    """Flatten a possibly-tuple MultiIndex column name to a string."""
    if isinstance(col, tuple):
        parts = []
        for p in col:
            s = str(p).strip()
            if s and s.lower() != "nan" and "unnamed" not in s.lower():
                parts.append(s)
        return " - ".join(parts) if parts else "Col"
    s = str(col).strip()
    if s.lower() == "nan" or "unnamed" in s.lower():
        return "Col"
    return s


def _deduplicate_columns(columns):
    """Return a list of unique string column names (appending _1, _2, ...)."""
    seen = {}
    out = []
    for col in columns:
        col = _flatten_column(col)
        if col in seen:
            seen[col] += 1
            out.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            out.append(col)
    return out


def _build_headers_from_rows(df):
    """
    For Excel files read with ``header=None``, inspect the first few
    rows: if they look like text headers (merged group labels +
    sub-headers) combine them into meaningful column names and drop them
    from the data.
    """
    if len(df) < 2:
        return df

    header_rows = []
    for row_idx in range(min(3, len(df))):
        row = df.iloc[row_idx]
        non_null = row.dropna()
        if len(non_null) == 0:
            continue
        str_count = sum(1 for v in non_null if isinstance(v, str))
        if str_count / len(non_null) > 0.6:
            header_rows.append(row_idx)
        else:
            break

    if not header_rows:
        return df

    n_cols = len(df.columns)
    col_names = [""] * n_cols

    for row_idx in header_rows:
        row = df.iloc[row_idx]
        last_val = ""
        for i in range(n_cols):
            val = row.iloc[i]
            if pd.notna(val) and str(val).strip():
                last_val = str(val).strip()
            if last_val:
                if col_names[i]:
                    col_names[i] += " - " + last_val
                else:
                    col_names[i] = last_val

    if all(c == "" for c in col_names):
        return df

    df = df.copy()
    df.columns = col_names
    df = df.iloc[max(header_rows) + 1:].reset_index(drop=True)
    return df


def smart_clean(df_raw):
    """
    Intelligently clean a raw DataFrame regardless of its original
    format.

    Pipeline
    --------
    0. Flatten MultiIndex columns
    1. Build column names from header rows (Excel integer columns)
    2. De-duplicate column names
    3. Drop completely empty rows / columns
    4. Promote first row if it still looks like a header
    5. Clean string values (strip, map nan-likes)
    6. Coerce numeric columns
    7. Drop duplicate rows
    8. Final column-name de-duplication
    """
    df = df_raw.copy()

    # Step 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [_flatten_column(c) for c in df.columns]

    # Step 1
    if all(isinstance(c, (int, np.integer)) for c in df.columns):
        df = _build_headers_from_rows(df)

    # Step 2
    df.columns = _deduplicate_columns(df.columns)

    # Step 3
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")

    # Step 4 -- promote first row to header when column names are generic
    if len(df) > 0:
        first_row = df.iloc[0]
        non_null = first_row.dropna()
        if len(non_null) > 0:
            is_header = all(isinstance(v, str) for v in non_null.values)
            cols_bad = any(
                "Unnamed" in str(c) or str(c) == "Col"
                for c in df.columns
            )
            if is_header and cols_bad:
                new_cols = [
                    str(v).strip() if pd.notna(v) else f"Col_{i}"
                    for i, v in enumerate(first_row)
                ]
                df.columns = _deduplicate_columns(new_cols)
                df = df.iloc[1:].reset_index(drop=True)

    # Steps 5 + 6 -- rebuild column-by-column for modern pandas compat
    new_data = {}
    for i, col_name in enumerate(df.columns):
        col_series = df.iloc[:, i].copy()
        if isinstance(col_series, pd.DataFrame):
            col_series = col_series.iloc[:, 0]

        # Clean strings
        try:
            is_obj = col_series.dtype == object
        except AttributeError:
            is_obj = False

        if is_obj:
            col_series = col_series.astype(str).str.strip()
            col_series = col_series.replace({
                "nan": np.nan, "": np.nan, "None": np.nan,
                "NaN": np.nan, "none": np.nan, "NaT": np.nan,
            })

        # Numeric coercion
        try:
            numeric_col = pd.to_numeric(col_series, errors="coerce")
            if numeric_col.notna().sum() / max(len(df), 1) > 0.5:
                col_series = numeric_col
        except (TypeError, AttributeError, ValueError):
            pass

        new_data[col_name] = col_series.values

    df = pd.DataFrame(new_data)

    # Step 7
    df = df.drop_duplicates().reset_index(drop=True)

    # Step 8
    df.columns = _deduplicate_columns(list(df.columns))

    return df


def clean_side_by_side_data(df_raw, n_groups=None):
    """
    Brute-force cleaning for side-by-side grouped data (common layout
    in dental research Excel sheets).

    Auto-detects the number of groups and melts the wide layout into a
    long DataFrame with columns ``Group``, ``TimeA``, ``TimeB``, ...
    """
    try:
        n_cols = len(df_raw.columns)

        if n_groups is None:
            cols_per_group = None
            for possible_width in [3, 4, 2, 5]:
                if (n_cols - 1) % possible_width == 0:
                    n_groups = (n_cols - 1) // possible_width
                    cols_per_group = possible_width
                    break
            if cols_per_group is None:
                cols_per_group = 3
                n_groups = max(1, (n_cols - 1) // cols_per_group)
        else:
            cols_per_group = max(1, (n_cols - 1) // n_groups)

        dfs = []
        current_col = 1

        for gn in range(1, n_groups + 1):
            if current_col + cols_per_group > n_cols + 1:
                break

            raw_name = str(df_raw.columns[current_col])
            if "Unnamed" in raw_name or raw_name == "nan":
                group_name = f"GROUP {gn}"
            else:
                group_name = raw_name

            chunk = df_raw.iloc[1:, current_col:current_col + cols_per_group].copy()
            col_names = [
                f"Time{chr(65 + i)}" for i in range(cols_per_group)
            ]
            chunk.columns = col_names
            chunk["Group"] = group_name
            dfs.append(chunk)
            current_col += cols_per_group

        if not dfs:
            return None

        clean_df = pd.concat(dfs, ignore_index=True)
        for col in clean_df.columns:
            if col != "Group":
                clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")
        clean_df.dropna(subset=[clean_df.columns[0]], inplace=True)
        return clean_df

    except Exception as exc:
        print(f"[ai_brain] clean_side_by_side_data error: {exc}")
        return None


# =========================================================================
# 6. AI ANALYSIS ENGINE
# =========================================================================

def build_analysis_prompt(df, data_analysis, proposal_text="",
                          suggested_tests=None, literature=None,
                          user_question=""):
    """
    Assemble the large prompt sent to the AI model.  Includes data
    overview, proposal context, literature hits, and code-generation
    rules.
    """
    data_sample = df.head(10).to_string()
    col_info = "\n".join(
        f"  - {v['Variable']}: {v['Type']} "
        f"(N={v['N']}, Missing={v['Missing']}, Unique={v['Unique']})"
        for v in data_analysis.get("variable_info", [])
    )

    tests_info = ""
    if suggested_tests:
        tests_info = "\n".join(
            f"  - {s['test']}: {s['reason']}"
            for s in suggested_tests[:10]
        )

    lit_info = ""
    if literature:
        for paper in literature[:5]:
            if "error" not in paper:
                lit_info += (
                    f"  - {paper.get('title', 'N/A')} "
                    f"({paper.get('year', 'N/A')}) - "
                    f"{paper.get('journal', 'N/A')}\n"
                )

    prompt = (
        "You are an Expert Biostatistician AI integrated into SolarSTATA, "
        "a Stata 19-equivalent statistical software.\n\n"
        "=== DATA OVERVIEW ===\n"
        f"Observations: {data_analysis.get('n_observations', '?')}\n"
        f"Variables: {data_analysis.get('n_variables', '?')}\n\n"
        f"Column Information:\n{col_info}\n\n"
        f"Data Sample (first 10 rows):\n{data_sample}\n\n"
        f"Numeric columns: {data_analysis.get('numeric_columns', [])}\n"
        f"Categorical columns: {data_analysis.get('categorical_columns', [])}\n"
        f"Group candidates: "
        f"{json.dumps(data_analysis.get('group_candidates', []), default=str)}\n"
    )

    if proposal_text:
        prompt += f"\n=== RESEARCH PROPOSAL ===\n{proposal_text}\n"
    if user_question:
        prompt += f"\n=== USER QUESTION ===\n{user_question}\n"
    if tests_info:
        prompt += f"\n=== SUGGESTED STATISTICAL TESTS ===\n{tests_info}\n"
    if lit_info:
        prompt += f"\n=== RELEVANT LITERATURE ===\n{lit_info}\n"

    prompt += """
=== YOUR MISSION ===
1. Analyze the data and proposal comprehensively
2. Select the MOST APPROPRIATE statistical tests with justification
3. Generate Python code to execute the analysis using `stats_engine` functions
4. Provide clear interpretation of results

=== CODE RULES ===
- The dataframe is available as `df`
- `stats_engine` is imported as `se`
- Available functions: se.descriptive(), se.oneway_anova(), se.twoway_anova(),
  se.ttest_one(), se.ttest_two(), se.ttest_paired(),
  se.chi_square(), se.ols_regression(), se.logistic_regression(),
  se.mann_whitney(), se.kruskal_wallis(), se.correlation(),
  se.kaplan_meier(), se.cox_regression(), se.normality(),
  se.power_ttest(), se.power_anova(), se.sample_size_means(),
  se.sample_size_proportions()
- pandas as pd, numpy as np, scipy.stats are available
- Print ALL results clearly with headers
- End with a "=== INTERPRETATION ===" section explaining findings

Return ONLY valid Python code inside a ```python``` block.
"""
    return prompt


# ---------------------------------------------------------------------------
# Master analysis entry-point
# ---------------------------------------------------------------------------

def analyze_data(dataframe, proposal_text="", user_question="",
                 do_research=True):
    """
    Master analysis pipeline:

    1. Smart-clean the data
    2. Analyse structure (detect_variable_types, group/outcome candidates)
    3. (Optional) literature search
    4. Suggest tests
    5. Build prompt, call AI via ``agent_core.call_agent``
    6. Execute generated code in a sandboxed ``exec``
    7. Fall back to ``run_automated_analysis`` on any failure
    """
    code_to_run = "# Error in generation"
    captured_output = ""
    error_message = None
    research_results = None
    suggestions = None
    data_info = None

    try:
        # ---- STEP 1: CLEAN DATA ----
        print("[SolarSTATA] Cleaning data...")
        try:
            clean_df = smart_clean(dataframe)
            if clean_df is None or clean_df.empty:
                clean_df = dataframe.copy()
        except Exception:
            clean_df = dataframe.copy()

        # ---- STEP 2: ANALYSE STRUCTURE ----
        print("[SolarSTATA] Analyzing data structure...")
        data_info = analyze_data_structure(clean_df)

        # ---- STEP 3: LITERATURE SEARCH ----
        if do_research and (proposal_text or user_question):
            print("[SolarSTATA] Searching literature...")
            search_q = (proposal_text[:200] if proposal_text
                        else user_question[:200])
            try:
                research_results = search_literature(search_q, max_results=3)
            except Exception as exc:
                research_results = [{"error": str(exc)}]

        # ---- STEP 4: SUGGEST TESTS ----
        print("[SolarSTATA] Determining appropriate statistical tests...")
        suggestions = suggest_tests(
            data_info, (proposal_text + " " + user_question).strip()
        )

        # ---- STEP 5: BUILD PROMPT & CALL AI ----
        prompt = build_analysis_prompt(
            clean_df, data_info, proposal_text,
            suggestions, research_results, user_question,
        )

        print("[SolarSTATA] AI is analyzing (this may take a moment)...")

        if not is_ollama_available():
            print(
                "[SolarSTATA] AI model not available, "
                "running automated analysis..."
            )
            return run_automated_analysis(
                clean_df, data_info, suggestions, proposal_text,
            )

        try:
            ai_result = call_agent(
                prompt,
                system_prompt=(
                    "You are an expert biostatistician. Generate precise, "
                    "executable Python code for statistical analysis. "
                    "Always use the stats_engine (se) module functions."
                ),
                timeout=180,
            )
            if not ai_result.get("success"):
                raise RuntimeError(
                    ai_result.get("error", "Unknown agent error")
                )
            ai_response = ai_result["response"]

        except Exception as exc:
            print(
                f"[SolarSTATA] AI model unavailable ({exc}), "
                "running automated analysis..."
            )
            return run_automated_analysis(
                clean_df, data_info, suggestions, proposal_text,
            )

        # ---- STEP 6: EXTRACT & EXECUTE CODE ----
        if ai_response:
            if "```python" in ai_response:
                code_to_run = ai_response.split("```python")[1].split("```")[0]
            elif "```" in ai_response:
                code_to_run = ai_response.split("```")[1].split("```")[0]
            else:
                code_to_run = ai_response

            # Sanitise
            code_to_run = code_to_run.replace("markdown(", "print(")
            code_to_run = code_to_run.replace("display(", "print(")
            lines = code_to_run.split("\n")
            cleaned_lines = [
                l for l in lines
                if not l.strip().startswith("import ")
                and not l.strip().startswith("from ")
            ]
            code_to_run = "\n".join(cleaned_lines)

            output_buffer = io.StringIO()
            original_stdout = sys.stdout
            sys.stdout = output_buffer

            try:
                local_env = {
                    "pd": pd,
                    "np": np,
                    "sm": sm,
                    "ols": ols,
                    "se": se,
                    "df": clean_df,
                    "print": print,
                    "stats": sp_stats,
                }
                exec(code_to_run, local_env)
            except Exception as exc:
                error_message = f"Execution Error: {exc}"
                sys.stdout = original_stdout
                return run_automated_analysis(
                    clean_df, data_info, suggestions, proposal_text,
                )
            finally:
                captured_output = output_buffer.getvalue()
                sys.stdout = original_stdout

    except Exception as exc:
        error_message = f"Critical System Error: {exc}"

    return {
        "generated_code": code_to_run,
        "stdout": captured_output,
        "error": error_message,
        "data_info": data_info,
        "suggestions": suggestions,
        "research": research_results,
    }


# ---------------------------------------------------------------------------
# Automated (non-AI) fallback
# ---------------------------------------------------------------------------

def run_automated_analysis(df, data_info, suggestions, proposal_text=""):
    """
    Run the suggested tests directly (no AI).  Called when
    Ollama / agent_core is unavailable or when AI code execution fails.
    """
    output_parts = []
    code_parts = []
    errors = []

    output_parts.append("=" * 60)
    output_parts.append("  SOLARSTATA AUTOMATED STATISTICAL ANALYSIS")
    output_parts.append("=" * 60)

    # --- Descriptive statistics ---
    try:
        numeric_cols = data_info.get("numeric_columns", [])
        if numeric_cols:
            desc = se.descriptive(df, numeric_cols, detail=True)
            output_parts.append("\n--- DESCRIPTIVE STATISTICS ---")
            output_parts.append(desc.to_string())
            code_parts.append("se.descriptive(df, detail=True)")
    except Exception as exc:
        errors.append(f"Descriptive stats: {exc}")

    # --- Run each suggested test ---
    for suggestion in (suggestions or []):
        test = suggestion["test"]
        try:
            if test == "oneway_anova":
                for gc in data_info.get("group_candidates", []):
                    for oc in data_info.get("outcome_candidates", []):
                        result = se.oneway_anova(df, oc, gc["column"])
                        output_parts.append(
                            f"\n--- ONE-WAY ANOVA: {oc} by "
                            f"{gc['column']} ---"
                        )
                        output_parts.append(
                            f"F = {result.get('F')}, "
                            f"p = {result.get('p')}"
                        )
                        p_val = result.get("p")
                        if p_val is not None and p_val < 0.05:
                            output_parts.append(
                                ">>> SIGNIFICANT DIFFERENCE DETECTED"
                            )
                        else:
                            output_parts.append(
                                ">>> No significant difference"
                            )
                        for gs in result.get("group_stats", []):
                            output_parts.append(
                                f"  {gs.get('Group')}: "
                                f"Mean={gs.get('Mean')}, "
                                f"SD={gs.get('SD')}, "
                                f"N={gs.get('N')}"
                            )
                        bart = result.get("bartlett", {})
                        lev = result.get("levene", {})
                        if bart:
                            output_parts.append(
                                f"  Bartlett's test: "
                                f"chi2={bart.get('chi2')}, "
                                f"p={bart.get('p')}"
                            )
                        if lev:
                            output_parts.append(
                                f"  Levene's test: "
                                f"F={lev.get('F')}, "
                                f"p={lev.get('p')}"
                            )
                        break
                    break

            elif test == "ttest_two":
                for gc in data_info.get("group_candidates", []):
                    if gc["n_groups"] == 2:
                        for oc in data_info.get("outcome_candidates", []):
                            result = se.ttest_two(df, oc, gc["column"])
                            output_parts.append(
                                f"\n--- TWO-SAMPLE T-TEST: {oc} "
                                f"by {gc['column']} ---"
                            )
                            output_parts.append(
                                f"  {result.get('Group_1')}: "
                                f"mean={result.get('mean1')}, "
                                f"n={result.get('n1')}"
                            )
                            output_parts.append(
                                f"  {result.get('Group_2')}: "
                                f"mean={result.get('mean2')}, "
                                f"n={result.get('n2')}"
                            )
                            output_parts.append(
                                f"  t(equal) = {result.get('t_equal')}, "
                                f"p = {result.get('p_equal')}"
                            )
                            output_parts.append(
                                f"  t(Welch) = {result.get('t_welch')}, "
                                f"p = {result.get('p_welch')}"
                            )
                            break
                        break

            elif test == "chi_square":
                cats = data_info.get("categorical_columns", [])
                if len(cats) >= 2:
                    result = se.chi_square(df, cats[0], cats[1])
                    output_parts.append(
                        f"\n--- CHI-SQUARE TEST: "
                        f"{cats[0]} x {cats[1]} ---"
                    )
                    output_parts.append(
                        f"  chi2 = {result.get('chi2')}, "
                        f"df = {result.get('df')}, "
                        f"p = {result.get('p')}"
                    )
                    output_parts.append(
                        f"  Cramer's V = {result.get('cramers_v')}"
                    )

            elif test == "correlation":
                cont = data_info.get("continuous_columns", [])
                if len(cont) >= 2:
                    result = se.correlation(df, cont[:6])
                    output_parts.append("\n--- CORRELATION MATRIX ---")
                    output_parts.append(
                        result.get("correlation_str", str(result))
                    )

            elif test == "normality":
                for nc in data_info.get("numeric_columns", [])[:5]:
                    try:
                        result = se.normality(df, nc)
                        output_parts.append(
                            f"\n--- NORMALITY TEST: {nc} ---"
                        )
                        output_parts.append(
                            f"  Skewness z={result.get('Skew_z')}, "
                            f"p={result.get('Skew_p')}"
                        )
                        output_parts.append(
                            f"  Kurtosis z={result.get('Kurt_z')}, "
                            f"p={result.get('Kurt_p')}"
                        )
                        output_parts.append(
                            f"  Shapiro-Wilk W={result.get('SW_W')}, "
                            f"p={result.get('SW_p')}"
                        )
                    except Exception:
                        pass

            elif test == "mann_whitney":
                for gc in data_info.get("group_candidates", []):
                    if gc["n_groups"] == 2:
                        for oc in data_info.get("outcome_candidates", []):
                            result = se.mann_whitney(df, oc, gc["column"])
                            output_parts.append(
                                f"\n--- MANN-WHITNEY U: {oc} by "
                                f"{gc['column']} ---"
                            )
                            output_parts.append(
                                f"  U = {result.get('U')}, "
                                f"p = {result.get('p')}"
                            )
                            break
                        break

            elif test == "kruskal_wallis":
                for gc in data_info.get("group_candidates", []):
                    if gc["n_groups"] > 2:
                        for oc in data_info.get("outcome_candidates", []):
                            result = se.kruskal_wallis(df, oc, gc["column"])
                            output_parts.append(
                                f"\n--- KRUSKAL-WALLIS: {oc} by "
                                f"{gc['column']} ---"
                            )
                            output_parts.append(
                                f"  H = {result.get('H')}, "
                                f"df = {result.get('df')}, "
                                f"p = {result.get('p')}"
                            )
                            break
                        break

        except Exception as exc:
            errors.append(f"{test}: {exc}")

    output_parts.append("\n" + "=" * 60)
    output_parts.append("  END OF ANALYSIS")
    output_parts.append("=" * 60)

    return {
        "generated_code": "\n".join(code_parts),
        "stdout": "\n".join(output_parts),
        "error": "; ".join(errors) if errors else None,
        "data_info": data_info,
        "suggestions": suggestions,
        "research": None,
    }


# ---------------------------------------------------------------------------
# Quick single-test helper
# ---------------------------------------------------------------------------

def quick_analyze(df, test_name, **kwargs):
    """
    Run a single named statistical test from ``stats_engine`` and
    return its result dict.
    """
    try:
        func = getattr(se, test_name, None)
        if func is None:
            return {"error": f"Unknown test: {test_name}"}
        return func(df, **kwargs)
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# AI-assisted sample size
# ---------------------------------------------------------------------------

def calculate_sample_size(study_info):
    """
    Calculate required sample size for the study described by
    *study_info* dict.

    Uses the ``stats_engine`` power / sample-size formulas and
    supplements with a literature search for context.
    """
    study_type = study_info.get("study_type", "")
    test_type = study_info.get("test_type", "")
    effect_size = study_info.get("effect_size", None)
    alpha = study_info.get("alpha", 0.05)
    power = study_info.get("power", 0.80)
    sd = study_info.get("sd", None)
    p1 = study_info.get("p1", None)
    p2 = study_info.get("p2", None)
    k_groups = study_info.get("k_groups", 2)

    results = {"input": study_info}

    # Literature search
    try:
        lit = search_sample_size_references(study_type, test_type)
        results["literature"] = lit
    except Exception:
        results["literature"] = None

    # Parametric calculation
    try:
        if test_type in ("t-test", "ttest", "two-sample"):
            if effect_size and sd:
                results["calculation"] = se.sample_size_means(
                    effect_size, sd, alpha, power,
                )
            elif effect_size:
                results["calculation"] = se.power_ttest(
                    delta=effect_size, sd=1.0, power=power, alpha=alpha,
                )
        elif test_type in ("anova", "one-way", "oneway"):
            if effect_size:
                results["calculation"] = se.power_anova(
                    k=k_groups, f_effect=effect_size,
                    alpha=alpha, power=power,
                )
        elif test_type in ("chi-square", "chi2", "proportion"):
            if p1 is not None and p2 is not None:
                results["calculation"] = se.sample_size_proportions(
                    p1, p2, alpha, power,
                )
            elif effect_size:
                results["calculation"] = se.power_chi2(
                    w=effect_size, df=k_groups - 1,
                    alpha=alpha, power=power,
                )
    except Exception as exc:
        results["calculation_error"] = str(exc)

    results["effect_size_conventions"] = {
        "t-test (Cohen's d)": {"small": 0.2, "medium": 0.5, "large": 0.8},
        "ANOVA (Cohen's f)": {"small": 0.10, "medium": 0.25, "large": 0.40},
        "Chi-square (Cohen's w)": {"small": 0.10, "medium": 0.30, "large": 0.50},
        "Correlation (r)": {"small": 0.10, "medium": 0.30, "large": 0.50},
    }

    return results
