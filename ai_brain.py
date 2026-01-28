"""
SolarSTATA AI Brain
AI-powered statistical analysis engine with internet research capabilities.
Uses Ollama (LLaMA) for reasoning and web search for literature review.
"""

import ollama
import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.formula.api import ols
import sys
import io
import json
import re
import requests
from bs4 import BeautifulSoup
import stats_engine as se

# ---------------------------------------------------------------------------
# WEB RESEARCH MODULE
# ---------------------------------------------------------------------------

def search_literature(query, max_results=5):
    """
    Search for academic papers and statistical references online.
    Uses public APIs (PubMed, CrossRef) to find relevant literature.
    Returns structured results for AI context.
    """
    results = []

    # --- PubMed Search (biomedical literature) ---
    try:
        pubmed_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }
        resp = requests.get(pubmed_url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            ids = data.get("esearchresult", {}).get("idlist", [])
            if ids:
                # Fetch article summaries
                summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                sum_params = {
                    "db": "pubmed",
                    "id": ",".join(ids),
                    "retmode": "json",
                }
                sum_resp = requests.get(summary_url, params=sum_params, timeout=10)
                if sum_resp.status_code == 200:
                    sum_data = sum_resp.json().get("result", {})
                    for pid in ids:
                        article = sum_data.get(pid, {})
                        if isinstance(article, dict):
                            results.append({
                                "source": "PubMed",
                                "pmid": pid,
                                "title": article.get("title", "N/A"),
                                "journal": article.get("fulljournalname", "N/A"),
                                "year": article.get("pubdate", "N/A")[:4],
                                "authors": article.get("sortfirstauthor", "N/A"),
                            })
    except Exception as e:
        results.append({"source": "PubMed", "error": str(e)})

    # --- CrossRef Search (broader academic literature) ---
    try:
        crossref_url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "rows": max_results,
            "sort": "relevance",
        }
        headers = {"User-Agent": "SolarSTATA/1.0 (research tool)"}
        resp = requests.get(crossref_url, params=params, headers=headers, timeout=10)
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
                dp = item.get("published-print", item.get("published-online", {}))
                if dp and "date-parts" in dp and dp["date-parts"]:
                    year = str(dp["date-parts"][0][0]) if dp["date-parts"][0] else ""
                results.append({
                    "source": "CrossRef",
                    "title": title,
                    "authors": author_str,
                    "year": year,
                    "doi": item.get("DOI", "N/A"),
                    "journal": item.get("container-title", ["N/A"])[0] if item.get("container-title") else "N/A",
                })
    except Exception as e:
        results.append({"source": "CrossRef", "error": str(e)})

    return results


def search_sample_size_references(study_type, test_type, subject_type=""):
    """
    Search for sample size references in literature for similar studies.
    Returns recommendations based on published research.
    """
    query = f"sample size {test_type} {study_type} {subject_type}".strip()
    lit = search_literature(query, max_results=5)

    # Also build a statistical recommendation
    recommendations = {
        "pilot_study": "Recommended: 12-30 per group (Julious, 2005)",
        "rct_two_arm": "Use power analysis: typically 30-100+ per arm depending on effect size",
        "survey": "Consider design effect; typically 384 for 95% CI, 50% proportion",
        "case_control": "Match ratio 1:1 to 1:4; use Kelsey formula",
        "cohort": "Depends on incidence; use Schoenfeld formula for survival outcomes",
    }

    return {
        "literature": lit,
        "general_recommendations": recommendations,
        "search_query": query,
    }


# ---------------------------------------------------------------------------
# DATA INTELLIGENCE MODULE
# ---------------------------------------------------------------------------

def analyze_data_structure(df):
    """
    Intelligently analyze a dataframe to understand its structure,
    variable types, and suggest appropriate statistical tests.
    Uses positional indexing throughout to handle duplicate column names.
    """
    info = se.detect_variable_types(df)
    n_rows, n_cols = df.shape
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = info[info["Type"] == "categorical"]["Variable"].tolist()
    continuous_cols = info[info["Type"] == "continuous"]["Variable"].tolist()

    # Detect potential grouping variables (use iloc for safety)
    group_candidates = []
    for i, col in enumerate(df.columns):
        try:
            col_series = df.iloc[:, i]
            nunique = int(col_series.nunique())
            if 2 <= nunique <= 20:
                unique_vals = col_series.dropna().unique().tolist()[:10]
                # Convert numpy types to native Python for JSON serialization
                unique_vals = [str(v) if not isinstance(v, (int, float, str)) else v
                               for v in unique_vals]
                group_candidates.append({
                    "column": str(col), "n_groups": nunique,
                    "groups": unique_vals,
                })
        except Exception:
            pass

    # Detect potential outcome variables (continuous with high unique count)
    outcome_candidates = []
    for c in continuous_cols:
        try:
            col_idx = list(df.columns).index(c)
            if int(df.iloc[:, col_idx].nunique()) > 10:
                outcome_candidates.append(c)
        except Exception:
            pass

    # Detect potential time variables
    time_candidates = []
    for col in df.columns:
        col_lower = str(col).lower()
        if any(t in col_lower for t in ["time", "date", "day", "week", "month", "year",
                                         "baseline", "follow", "pre", "post"]):
            time_candidates.append(str(col))

    # Detect paired/repeated measures structure
    has_repeated = any(
        any(t in str(c).lower() for t in ["time", "visit", "day", "baseline", "immersion"])
        for c in df.columns
    )

    # Build missing summary using iloc
    missing_summary = {}
    for i, col in enumerate(df.columns):
        n_miss = int(df.iloc[:, i].isna().sum())
        if n_miss > 0:
            missing_summary[str(col)] = n_miss

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
        "variable_info": info.to_dict("records"),
        "missing_summary": missing_summary,
    }


def suggest_tests(data_analysis, proposal_text=""):
    """
    Based on data structure and optional proposal text,
    suggest the most appropriate statistical tests.
    """
    suggestions = []
    da = data_analysis

    # Always suggest descriptive stats
    suggestions.append({
        "test": "descriptive",
        "reason": "Always start with descriptive statistics to understand your data",
        "priority": 1,
    })

    # If there are grouping variables and continuous outcomes
    if da["group_candidates"] and da["outcome_candidates"]:
        for gc in da["group_candidates"]:
            n_groups = gc["n_groups"]
            if n_groups == 2:
                suggestions.append({
                    "test": "ttest_two",
                    "reason": f"Compare means between 2 groups ({gc['column']})",
                    "params": {"groupvar": gc["column"]},
                    "priority": 2,
                })
                suggestions.append({
                    "test": "mann_whitney",
                    "reason": f"Non-parametric alternative if normality assumption violated ({gc['column']})",
                    "params": {"groupvar": gc["column"]},
                    "priority": 3,
                })
            elif n_groups > 2:
                suggestions.append({
                    "test": "oneway_anova",
                    "reason": f"Compare means across {n_groups} groups ({gc['column']})",
                    "params": {"groupvar": gc["column"]},
                    "priority": 2,
                })
                suggestions.append({
                    "test": "kruskal_wallis",
                    "reason": f"Non-parametric alternative for {n_groups} groups ({gc['column']})",
                    "params": {"groupvar": gc["column"]},
                    "priority": 3,
                })

    # If there are categorical variables for chi-square
    cats = da["categorical_columns"]
    if len(cats) >= 2:
        suggestions.append({
            "test": "chi_square",
            "reason": f"Test association between categorical variables",
            "params": {"var1": cats[0], "var2": cats[1]},
            "priority": 2,
        })

    # If there are multiple continuous variables for regression
    if len(da["continuous_columns"]) >= 2:
        suggestions.append({
            "test": "correlation",
            "reason": "Examine relationships between continuous variables",
            "priority": 2,
        })
        if len(da["continuous_columns"]) >= 3:
            suggestions.append({
                "test": "regression",
                "reason": "Model outcome as function of predictors",
                "priority": 3,
            })

    # If proposal mentions specific tests, boost them
    proposal_lower = proposal_text.lower()
    keyword_test_map = {
        "chi-square": "chi_square", "chi square": "chi_square", "chi2": "chi_square",
        "anova": "oneway_anova", "one-way": "oneway_anova", "one way": "oneway_anova",
        "two-way anova": "twoway_anova", "two way anova": "twoway_anova",
        "t-test": "ttest_two", "t test": "ttest_two",
        "regression": "regression", "linear regression": "regression",
        "logistic": "logistic", "logit": "logistic",
        "survival": "kaplan_meier", "kaplan": "kaplan_meier", "cox": "cox",
        "mann-whitney": "mann_whitney", "wilcoxon": "wilcoxon",
        "kruskal": "kruskal_wallis",
        "sample size": "sample_size_means", "power": "power_ttest",
        "correlation": "correlation", "spearman": "correlation",
    }
    for keyword, test in keyword_test_map.items():
        if keyword in proposal_lower:
            exists = any(s["test"] == test for s in suggestions)
            if not exists:
                suggestions.append({
                    "test": test,
                    "reason": f"Mentioned in proposal: '{keyword}'",
                    "priority": 1,
                })

    suggestions.sort(key=lambda x: x["priority"])
    return suggestions


# ---------------------------------------------------------------------------
# SMART CLEANING MODULE
# ---------------------------------------------------------------------------

def _flatten_column(col):
    """Flatten a column name: handle MultiIndex tuples, Unnamed markers, etc."""
    if isinstance(col, tuple):
        # MultiIndex column - join non-empty, non-Unnamed parts
        parts = []
        for part in col:
            s = str(part).strip()
            if s and s.lower() != "nan" and "unnamed" not in s.lower():
                parts.append(s)
        return " - ".join(parts) if parts else f"Col"
    s = str(col).strip()
    if s.lower() == "nan" or "unnamed" in s.lower():
        return "Col"
    return s


def _deduplicate_columns(columns):
    """Flatten and make column names unique by appending _1, _2, etc."""
    seen = {}
    new_cols = []
    for col in columns:
        col = _flatten_column(col)
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    return new_cols


def _build_headers_from_rows(df):
    """
    For Excel files with merged group headers + sub-headers,
    scan first rows and build meaningful column names.
    E.g. Row0='GROUP 1 (COW MILK)', Row1='BASELINE' => 'GROUP 1 (COW MILK) - BASELINE'
    """
    if len(df) < 2:
        return df

    # Check if the first 1-2 rows are header-like (mostly strings, few/no numbers)
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

    # Build column names from header rows
    n_cols = len(df.columns)
    col_names = [""] * n_cols

    for row_idx in header_rows:
        row = df.iloc[row_idx]
        # Forward-fill: merged cells in Excel show value in first col, NaN in rest
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

    # If all column names are empty, fall back
    if all(c == "" for c in col_names):
        return df

    # Set new column names and drop header rows
    df = df.copy()
    df.columns = col_names
    df = df.iloc[max(header_rows) + 1:].reset_index(drop=True)
    return df


def smart_clean(df_raw):
    """
    Intelligently clean data regardless of format.
    Handles wide format, side-by-side groups, messy headers, duplicate columns,
    MultiIndex columns from merged Excel cells, etc.
    """
    df = df_raw.copy()

    # Step 0: Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [_flatten_column(col) for col in df.columns]

    # Step 1: If columns are just integers (header=None read), build headers from rows
    if all(isinstance(c, (int, np.integer)) for c in df.columns):
        df = _build_headers_from_rows(df)

    # Step 2: Deduplicate column names
    df.columns = _deduplicate_columns(df.columns)

    # Step 3: Remove completely empty rows/cols
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")

    # Step 4: If first row still looks like a header (all strings), promote it
    if len(df) > 0:
        first_row = df.iloc[0]
        non_null = first_row.dropna()
        if len(non_null) > 0:
            is_header = all(isinstance(v, str) for v in non_null.values)
            col_names_are_bad = any("Unnamed" in str(c) or "Col" == str(c) for c in df.columns)
            if is_header and col_names_are_bad:
                new_cols = [str(v).strip() if pd.notna(v) else f"Col_{i}" for i, v in enumerate(first_row)]
                df.columns = _deduplicate_columns(new_cols)
                df = df.iloc[1:].reset_index(drop=True)

    # Step 5 & 6: Clean string values + convert to numeric where possible
    # Rebuild column-by-column to avoid iloc assignment issues in modern pandas
    new_data = {}
    for i, col_name in enumerate(df.columns):
        col_series = df.iloc[:, i].copy()

        # Ensure col_series is truly a Series (guard against edge cases)
        if isinstance(col_series, pd.DataFrame):
            col_series = col_series.iloc[:, 0]

        # Clean strings
        try:
            is_object = col_series.dtype == object
        except AttributeError:
            is_object = False

        if is_object:
            col_series = col_series.astype(str).str.strip()
            col_series = col_series.replace({"nan": np.nan, "": np.nan, "None": np.nan,
                                              "NaN": np.nan, "none": np.nan, "NaT": np.nan})

        # Try numeric conversion
        try:
            numeric_col = pd.to_numeric(col_series, errors="coerce")
            if numeric_col.notna().sum() / max(len(df), 1) > 0.5:
                col_series = numeric_col
        except (TypeError, AttributeError, ValueError):
            pass

        new_data[col_name] = col_series.values

    df = pd.DataFrame(new_data)

    # Step 7: Remove duplicate rows
    df = df.drop_duplicates().reset_index(drop=True)

    # Step 8: Final deduplication of column names
    df.columns = _deduplicate_columns(list(df.columns))

    return df


def clean_side_by_side_data(df_raw, n_groups=None):
    """
    BRUTE FORCE CLEANING for side-by-side grouped data.
    Auto-detects number of groups if not specified.
    """
    try:
        n_cols = len(df_raw.columns)

        # Try to detect group structure
        if n_groups is None:
            # Look for repeating patterns in column names
            for possible_width in [3, 4, 2, 5]:
                if (n_cols - 1) % possible_width == 0:
                    n_groups = (n_cols - 1) // possible_width
                    cols_per_group = possible_width
                    break
            else:
                # Default to 3 columns per group
                cols_per_group = 3
                n_groups = max(1, (n_cols - 1) // cols_per_group)
        else:
            cols_per_group = max(1, (n_cols - 1) // n_groups)

        dfs = []
        current_col = 1

        for group_num in range(1, n_groups + 1):
            if current_col + cols_per_group > n_cols + 1:
                break

            raw_name = str(df_raw.columns[current_col])
            if "Unnamed" in raw_name or raw_name == "nan":
                group_name = f"GROUP {group_num}"
            else:
                group_name = raw_name

            chunk = df_raw.iloc[1:, current_col:current_col + cols_per_group].copy()

            col_names = []
            for i in range(cols_per_group):
                if i == 0:
                    col_names.append("TimeA")
                elif i == 1:
                    col_names.append("TimeB")
                elif i == 2:
                    col_names.append("TimeC")
                else:
                    col_names.append(f"Time{chr(65+i)}")
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

    except Exception as e:
        print(f"Cleaning Error: {e}")
        return None


# ---------------------------------------------------------------------------
# AI ANALYSIS ENGINE
# ---------------------------------------------------------------------------

def build_analysis_prompt(df, data_analysis, proposal_text="", suggested_tests=None,
                          literature=None, user_question=""):
    """
    Build a comprehensive prompt for the AI model that includes
    data context, literature references, and specific instructions.
    """
    data_sample = df.head(10).to_string()
    col_info = "\n".join(
        f"  - {v['Variable']}: {v['Type']} (N={v['N']}, Missing={v['Missing']}, Unique={v['Unique']})"
        for v in data_analysis["variable_info"]
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
                lit_info += f"  - {paper.get('title', 'N/A')} ({paper.get('year', 'N/A')}) - {paper.get('journal', 'N/A')}\n"

    prompt = f"""You are an Expert Biostatistician AI integrated into SolarSTATA, a Stata 19-equivalent statistical software.

=== DATA OVERVIEW ===
Observations: {data_analysis['n_observations']}
Variables: {data_analysis['n_variables']}

Column Information:
{col_info}

Data Sample (first 10 rows):
{data_sample}

Numeric columns: {data_analysis['numeric_columns']}
Categorical columns: {data_analysis['categorical_columns']}
Group candidates: {json.dumps(data_analysis['group_candidates'], default=str)}
"""

    if proposal_text:
        prompt += f"""
=== RESEARCH PROPOSAL ===
{proposal_text}
"""

    if user_question:
        prompt += f"""
=== USER QUESTION ===
{user_question}
"""

    if tests_info:
        prompt += f"""
=== SUGGESTED STATISTICAL TESTS ===
{tests_info}
"""

    if lit_info:
        prompt += f"""
=== RELEVANT LITERATURE ===
{lit_info}
"""

    prompt += """
=== YOUR MISSION ===
1. Analyze the data and proposal comprehensively
2. Select the MOST APPROPRIATE statistical tests with justification
3. Generate Python code to execute the analysis using `stats_engine` functions
4. Provide clear interpretation of results

=== CODE RULES ===
- The dataframe is available as `df`
- `stats_engine` is imported as `se`
- Available functions: se.descriptive_stats(), se.oneway_anova(), se.twoway_anova(),
  se.ttest_one_sample(), se.ttest_two_sample(), se.ttest_paired(),
  se.chi_square_test(), se.linear_regression(), se.logistic_regression(),
  se.mann_whitney_u(), se.kruskal_wallis(), se.correlation_matrix(),
  se.kaplan_meier(), se.cox_regression(), se.normality_test(),
  se.power_ttest(), se.power_anova(), se.sample_size_means(),
  se.sample_size_proportions()
- pandas as pd, numpy as np, scipy.stats are available
- Print ALL results clearly with headers
- End with a "=== INTERPRETATION ===" section explaining findings

Return ONLY valid Python code inside a ```python``` block.
"""
    return prompt


def analyze_data(dataframe, proposal_text="", user_question="", do_research=True):
    """
    Master analysis function:
    1. Smart-cleans data
    2. Analyzes structure
    3. Searches literature (if enabled)
    4. Suggests tests
    5. Runs AI for code generation
    6. Executes analysis
    """
    code_to_run = "# Error in generation"
    captured_output = ""
    error_message = None
    research_results = None
    suggestions = None
    data_info = None

    try:
        # --- STEP 1: CLEAN DATA ---
        print("[SolarSTATA] Cleaning data...")
        clean_df = smart_clean(dataframe)
        if clean_df is None or clean_df.empty:
            clean_df = dataframe.copy()

        # --- STEP 2: ANALYZE STRUCTURE ---
        print("[SolarSTATA] Analyzing data structure...")
        data_info = analyze_data_structure(clean_df)

        # --- STEP 3: LITERATURE SEARCH ---
        if do_research and (proposal_text or user_question):
            print("[SolarSTATA] Searching literature...")
            search_query = proposal_text[:200] if proposal_text else user_question[:200]
            try:
                research_results = search_literature(search_query, max_results=3)
            except Exception as e:
                research_results = [{"error": str(e)}]

        # --- STEP 4: SUGGEST TESTS ---
        print("[SolarSTATA] Determining appropriate statistical tests...")
        suggestions = suggest_tests(data_info, proposal_text + " " + user_question)

        # --- STEP 5: BUILD PROMPT & CALL AI ---
        prompt = build_analysis_prompt(
            clean_df, data_info, proposal_text,
            suggestions, research_results, user_question,
        )

        print("[SolarSTATA] AI is analyzing (this may take a moment)...")
        try:
            response = ollama.chat(model="llama3.2", messages=[
                {"role": "system", "content": "You are an expert biostatistician. Generate precise, executable Python code for statistical analysis. Always use the stats_engine (se) module functions."},
                {"role": "user", "content": prompt},
            ])
            ai_response = response["message"]["content"]
        except Exception as e:
            # If Ollama is not available, run suggested tests directly
            print(f"[SolarSTATA] AI model unavailable ({e}), running automated analysis...")
            ai_response = None
            return run_automated_analysis(clean_df, data_info, suggestions, proposal_text)

        # --- STEP 6: EXTRACT & EXECUTE CODE ---
        if ai_response:
            if "```python" in ai_response:
                code_to_run = ai_response.split("```python")[1].split("```")[0]
            elif "```" in ai_response:
                code_to_run = ai_response.split("```")[1].split("```")[0]
            else:
                code_to_run = ai_response

            # Clean up
            code_to_run = code_to_run.replace("markdown(", "print(")
            code_to_run = code_to_run.replace("display(", "print(")
            # Remove any import lines that might conflict
            lines = code_to_run.split("\n")
            cleaned_lines = [l for l in lines if not l.strip().startswith("import ") and not l.strip().startswith("from ")]
            code_to_run = "\n".join(cleaned_lines)

            output_buffer = io.StringIO()
            original_stdout = sys.stdout
            sys.stdout = output_buffer

            try:
                local_env = {
                    "pd": pd, "np": np, "sm": sm, "ols": ols,
                    "se": se, "df": clean_df, "print": print,
                    "stats": __import__("scipy").stats,
                }
                exec(code_to_run, local_env)
            except Exception as e:
                error_message = f"Execution Error: {e}"
                # Fallback to automated analysis
                sys.stdout = original_stdout
                return run_automated_analysis(clean_df, data_info, suggestions, proposal_text)
            finally:
                captured_output = output_buffer.getvalue()
                sys.stdout = original_stdout

    except Exception as e:
        error_message = f"Critical System Error: {e}"

    return {
        "generated_code": code_to_run,
        "stdout": captured_output,
        "error": error_message,
        "data_info": data_info,
        "suggestions": suggestions,
        "research": research_results,
    }


def run_automated_analysis(df, data_info, suggestions, proposal_text=""):
    """
    Fallback: run statistical analysis without AI,
    using the suggested tests from data analysis.
    """
    output_parts = []
    code_parts = []
    errors = []

    output_parts.append("=" * 60)
    output_parts.append("  SOLARSTATA AUTOMATED STATISTICAL ANALYSIS")
    output_parts.append("=" * 60)

    # Always run descriptive stats
    try:
        numeric_cols = data_info.get("numeric_columns", [])
        if numeric_cols:
            desc = se.descriptive_stats(df, numeric_cols, detail=True)
            output_parts.append("\n--- DESCRIPTIVE STATISTICS ---")
            output_parts.append(desc.to_string())
            code_parts.append("se.descriptive_stats(df, detail=True)")
    except Exception as e:
        errors.append(f"Descriptive stats: {e}")

    # Run suggested tests
    for suggestion in (suggestions or []):
        test = suggestion["test"]
        try:
            if test == "oneway_anova":
                for gc in data_info.get("group_candidates", []):
                    for oc in data_info.get("outcome_candidates", []):
                        result = se.oneway_anova(df, oc, gc["column"])
                        output_parts.append(f"\n--- ONE-WAY ANOVA: {oc} by {gc['column']} ---")
                        output_parts.append(f"F = {result['F']}, p = {result['Prob > F']}")
                        if result["Prob > F"] < 0.05:
                            output_parts.append(">>> SIGNIFICANT DIFFERENCE DETECTED")
                        else:
                            output_parts.append(">>> No significant difference")
                        for gs in result["group_stats"]:
                            output_parts.append(f"  {gs['Group']}: Mean={gs['Mean']}, SD={gs['Std. Dev.']}, N={gs['N']}")
                        output_parts.append(f"  Bartlett's test: chi2={result['bartlett']['chi2']}, p={result['bartlett']['p']}")
                        output_parts.append(f"  Levene's test: F={result['levene']['F']}, p={result['levene']['p']}")
                        break
                    break

            elif test == "ttest_two":
                for gc in data_info.get("group_candidates", []):
                    if gc["n_groups"] == 2:
                        for oc in data_info.get("outcome_candidates", []):
                            result = se.ttest_two_sample(df, oc, gc["column"])
                            output_parts.append(f"\n--- TWO-SAMPLE T-TEST: {oc} by {gc['column']} ---")
                            output_parts.append(f"  {result.get('Group_1')}: mean={result.get('mean1')}, n={result.get('n1')}")
                            output_parts.append(f"  {result.get('Group_2')}: mean={result.get('mean2')}, n={result.get('n2')}")
                            output_parts.append(f"  t(equal var) = {result.get('t_equal_var')}, p = {result.get('p_equal_var')}")
                            output_parts.append(f"  t(Welch) = {result.get('t_welch')}, p = {result.get('p_welch')}")
                            break
                        break

            elif test == "chi_square":
                cats = data_info.get("categorical_columns", [])
                if len(cats) >= 2:
                    result = se.chi_square_test(df, cats[0], cats[1])
                    output_parts.append(f"\n--- CHI-SQUARE TEST: {cats[0]} x {cats[1]} ---")
                    output_parts.append(f"  chi2 = {result['chi2']}, df = {result['df']}, p = {result['Pr']}")
                    output_parts.append(f"  Cramer's V = {result['cramers_v']}")

            elif test == "correlation":
                cont = data_info.get("continuous_columns", [])
                if len(cont) >= 2:
                    result = se.correlation_matrix(df, cont[:6])
                    output_parts.append("\n--- CORRELATION MATRIX ---")
                    output_parts.append(result["correlation_str"])

            elif test == "normality":
                for nc in data_info.get("numeric_columns", [])[:5]:
                    try:
                        result = se.normality_test(df, nc)
                        output_parts.append(f"\n--- NORMALITY TEST: {nc} ---")
                        output_parts.append(f"  Skewness z={result['Skewness_z']}, p={result['Skewness_p']}")
                        output_parts.append(f"  Kurtosis z={result['Kurtosis_z']}, p={result['Kurtosis_p']}")
                        output_parts.append(f"  Shapiro-Wilk W={result['Shapiro-Wilk_W']}, p={result['Shapiro-Wilk_p']}")
                    except Exception:
                        pass

            elif test == "mann_whitney":
                for gc in data_info.get("group_candidates", []):
                    if gc["n_groups"] == 2:
                        for oc in data_info.get("outcome_candidates", []):
                            result = se.mann_whitney_u(df, oc, gc["column"])
                            output_parts.append(f"\n--- MANN-WHITNEY U: {oc} by {gc['column']} ---")
                            output_parts.append(f"  U = {result['U']}, p = {result['p']}")
                            break
                        break

            elif test == "kruskal_wallis":
                for gc in data_info.get("group_candidates", []):
                    if gc["n_groups"] > 2:
                        for oc in data_info.get("outcome_candidates", []):
                            result = se.kruskal_wallis(df, oc, gc["column"])
                            output_parts.append(f"\n--- KRUSKAL-WALLIS: {oc} by {gc['column']} ---")
                            output_parts.append(f"  H = {result['H']}, df = {result['df']}, p = {result['p']}")
                            break
                        break

        except Exception as e:
            errors.append(f"{test}: {e}")

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


def quick_analyze(df, test_name, **kwargs):
    """
    Run a single specific statistical test.
    Used by the UI for direct test execution.
    """
    try:
        func = getattr(se, test_name, None)
        if func is None:
            return {"error": f"Unknown test: {test_name}"}
        result = func(df, **kwargs)
        return result
    except Exception as e:
        return {"error": str(e)}


def calculate_sample_size(study_info):
    """
    AI-assisted sample size calculation.
    Uses mathematical formulas + literature search for context.
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

    # Literature search for reference
    try:
        lit = search_sample_size_references(study_type, test_type)
        results["literature"] = lit
    except Exception:
        results["literature"] = None

    # Calculate based on test type
    if test_type in ["t-test", "ttest", "two-sample"]:
        if effect_size and sd:
            delta = effect_size
            calc = se.sample_size_means(delta, sd, alpha, power)
            results["calculation"] = calc
        elif effect_size:
            # Cohen's d convention
            calc = se.power_ttest(delta=effect_size, sd=1.0, power=power, alpha=alpha)
            results["calculation"] = calc
    elif test_type in ["anova", "one-way", "oneway"]:
        if effect_size:
            calc = se.power_anova(k=k_groups, f_effect=effect_size, alpha=alpha, power=power)
            results["calculation"] = calc
    elif test_type in ["chi-square", "chi2", "proportion"]:
        if p1 and p2:
            calc = se.sample_size_proportions(p1, p2, alpha, power)
            results["calculation"] = calc
        elif effect_size:
            calc = se.power_chi2(w=effect_size, df=k_groups-1, alpha=alpha, power=power)
            results["calculation"] = calc

    # Standard effect size conventions
    results["effect_size_conventions"] = {
        "t-test (Cohen's d)": {"small": 0.2, "medium": 0.5, "large": 0.8},
        "ANOVA (Cohen's f)": {"small": 0.10, "medium": 0.25, "large": 0.40},
        "Chi-square (Cohen's w)": {"small": 0.10, "medium": 0.30, "large": 0.50},
        "Correlation (r)": {"small": 0.10, "medium": 0.30, "large": 0.50},
    }

    return results
