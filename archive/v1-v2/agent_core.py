"""
SolarSTATA Agent Core -- 3-Stage Pipeline
==========================================
The AI organizes the mess. The Code calculates the truth. The AI explains the result.

Pipeline Architecture
---------------------
  Stage 1  (AI / Python fallback)  -- Data Organizer
  Stage 2  (Pure Python)           -- Statistical Calculator
  Stage 3  (AI / Python fallback)  -- Report Generator

When Ollama is unavailable, Python-based fallbacks handle Stages 1 and 3
seamlessly so the pipeline always produces results.
"""

import subprocess
import json
import re
import io
import pandas as pd
import numpy as np
from scipy.stats import f_oneway
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import threading
import queue
from typing import Optional, Dict, List, Any

# ---------------------------------------------------------------------------
# Optional dependency: Ollama Python client
# ---------------------------------------------------------------------------
try:
    import ollama
    HAS_OLLAMA_CLIENT = True
except ImportError:
    HAS_OLLAMA_CLIENT = False
    print("[Agent] ollama Python client not installed. AI features will use Python fallbacks.")

# ---------------------------------------------------------------------------
# Optional dependency: DuckDuckGo search
# ---------------------------------------------------------------------------
try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False
    print("[Agent] duckduckgo-search not installed. Run: pip install duckduckgo-search")

# ---------------------------------------------------------------------------
# Optional dependency: PDF parsing
# ---------------------------------------------------------------------------
try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    print("[Agent] PyPDF2 not installed. Run: pip install PyPDF2")


# ===========================================================================
# 1. OLLAMA MANAGEMENT
# ===========================================================================

_current_model = "llama3.2"


def check_ollama_running() -> bool:
    """Check if the Ollama service is running by invoking ``ollama list``."""
    if not HAS_OLLAMA_CLIENT:
        return False
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


# Cached result -- checked once per session, then remembered
_ollama_available: Optional[bool] = None


def is_ollama_available() -> bool:
    """Return *True* if Ollama is reachable (result is cached after first check)."""
    global _ollama_available
    if _ollama_available is None:
        _ollama_available = check_ollama_running()
        if not _ollama_available:
            print("[Agent] Ollama not available. Using Python fallbacks for Stage 1 & 3.")
        else:
            print("[Agent] Ollama is available.")
    return _ollama_available


def reset_ollama_check():
    """Clear the cached availability flag so the next call re-probes."""
    global _ollama_available
    _ollama_available = None


def set_model(model_name: str):
    """Select which Ollama model to use for AI stages."""
    global _current_model
    _current_model = model_name


def get_model() -> str:
    """Return the currently selected Ollama model name."""
    return _current_model


def get_available_models() -> List[str]:
    """Query Ollama for locally-pulled models; returns ``['llama3.2']`` on failure."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return ["llama3.2"]

        lines = result.stdout.strip().split("\n")
        models: List[str] = []
        for line in lines[1:]:  # skip header row
            if line.strip():
                parts = line.split()
                if parts:
                    name = parts[0]
                    if ":latest" in name:
                        name = name.replace(":latest", "")
                    models.append(name)
        return models if models else ["llama3.2"]
    except Exception as exc:
        print(f"[Agent] Error listing models: {exc}")
        return ["llama3.2"]


def call_agent(prompt: str, system_prompt: str = None, timeout: int = 120) -> Dict:
    """
    Call Ollama in a background thread with a hard *timeout*.

    Returns
    -------
    dict  ``{"success": bool, "response": str, "error": str}``
    """
    if not HAS_OLLAMA_CLIENT:
        return {"success": False, "response": "", "error": "Ollama Python client not installed"}

    if not is_ollama_available():
        return {"success": False, "response": "", "error": "Ollama server not available"}

    result_queue: queue.Queue = queue.Queue()

    def _call():
        try:
            messages: List[Dict] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            resp = ollama.chat(model=_current_model, messages=messages)
            result_queue.put({"success": True, "response": resp["message"]["content"], "error": ""})
        except Exception as exc:
            result_queue.put({"success": False, "response": "", "error": str(exc)})

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        return {"success": False, "response": "", "error": f"Timeout after {timeout} seconds"}

    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return {"success": False, "response": "", "error": "No response received"}


# ===========================================================================
# 2. SUMMARY ROW FILTERING
# ===========================================================================

_SUMMARY_KEYWORDS = [
    "mean", "sd", "average", "std", "se", "sem",
    "total", "sum", "median", "count", "n",
]


def _is_summary_keyword(text: str) -> bool:
    """Return *True* if *text* contains any summary-statistic keyword."""
    text_lower = text.lower().strip()
    for kw in _SUMMARY_KEYWORDS:
        if kw in text_lower:
            return True
    return False


def _filter_summary_rows(raw_text: str) -> str:
    """Remove lines whose first token is a summary keyword (mean, sd, ...)."""
    out_lines: List[str] = []
    for line in raw_text.split("\n"):
        stripped = line.strip().lower()
        if not stripped:
            out_lines.append(line)
            continue

        first_token = re.split(r"[\t,\s]+", stripped)[0]
        if first_token in _SUMMARY_KEYWORDS:
            continue  # skip this summary row

        out_lines.append(line)
    return "\n".join(out_lines)


# ===========================================================================
# 3. STAGE 1 -- AI DATA ORGANIZER  (with Python fallback)
# ===========================================================================

STAGE1_ORGANIZER_PROMPT = """You are a data extraction specialist for dental research studies.
Your job is to convert messy spreadsheet data into a clean, standardized JSON format.

CRITICAL INSTRUCTIONS:
1. Find ALL raw observation data (individual measurements).
2. Identify the GROUP each value belongs to (e.g., "Control", "Cow Milk", "Soy Milk").
3. If there are TIME POINTS or CONDITIONS, identify those too (e.g., "Baseline", "Day 7").
4. Extract each individual numerical value.

ABSOLUTELY IGNORE (summary statistics, NOT raw data):
- Rows labelled Mean, Average, Avg
- Rows labelled SD, Std Dev, StDev, Standard Deviation
- Rows labelled SEM, SE, Standard Error
- Rows labelled N=, n=, Count, Total, Sum
- Rows labelled Min, Max, Range, Median
- Any calculated / aggregated values at the bottom of columns

OUTPUT FORMAT -- array of observation objects (JSON only, no other text):
[
    {"group": "Control", "time_point": "Baseline", "value": 466.4},
    {"group": "Control", "time_point": "Baseline", "value": 472.1},
    {"group": "Cow Milk", "time_point": "Day 7", "value": 389.2}
]

If there are NO time points, use "All" as the time_point value.
Output ONLY valid JSON array.  No explanations, no markdown, just JSON."""


# ---- helper parsers for the Python fallback ----

def _try_parse_columns(lines: List[str], delimiter) -> List[Dict]:
    """
    Attempt to read *lines* as column-oriented data where the first row
    contains group names and subsequent rows contain numeric values.

    *delimiter*: ``'\\t'``, ``','``, or ``None`` (whitespace split).
    """
    if not lines:
        return []

    # Split header
    if delimiter:
        headers = [h.strip() for h in lines[0].split(delimiter) if h.strip()]
    else:
        headers = lines[0].split()

    if not headers:
        return []

    # If every header is numeric, this is not really a header row
    numeric_count = 0
    for h in headers:
        try:
            float(h.replace(",", ""))
            numeric_count += 1
        except (ValueError, TypeError):
            pass
    if numeric_count == len(headers):
        return []

    # Identify which columns are group names (non-numeric, non-summary)
    group_headers: List[str] = []
    group_indices: List[int] = []
    for i, h in enumerate(headers):
        try:
            float(h.replace(",", ""))
            continue  # numeric -- not a group name
        except (ValueError, TypeError):
            pass
        if h and not _is_summary_keyword(h):
            group_headers.append(h)
            group_indices.append(i)

    if len(group_headers) < 2:
        return []

    observations: List[Dict] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        if delimiter:
            values = [v.strip() for v in line.split(delimiter)]
        else:
            values = line.split()

        for idx, group in zip(group_indices, group_headers):
            if idx >= len(values):
                continue
            val_str = values[idx].strip().replace(",", "")
            if not val_str or _is_summary_keyword(val_str):
                continue
            try:
                val = float(val_str)
                if np.isfinite(val):
                    observations.append({"group": group, "time_point": "All", "value": val})
            except (ValueError, TypeError):
                continue

    return observations


def _try_parse_with_pandas(raw_text: str) -> List[Dict]:
    """Use pandas ``read_csv`` with several separators to extract observations."""
    observations: List[Dict] = []

    for sep in ["\t", ",", r"\s+"]:
        try:
            df = pd.read_csv(io.StringIO(raw_text), sep=sep, engine="python")
            if df.empty or len(df.columns) < 2:
                continue

            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

            # Case 1: all (or most) columns are numeric with string headers -> groups as columns
            if len(numeric_cols) >= 2:
                for col in numeric_cols:
                    col_name = str(col)
                    if _is_summary_keyword(col_name):
                        continue
                    for val in df[col].dropna():
                        try:
                            v = float(val)
                            if np.isfinite(v):
                                observations.append({"group": col_name, "time_point": "All", "value": v})
                        except (ValueError, TypeError):
                            continue
                if len(observations) >= 3:
                    return observations
                observations = []

            # Case 2: first column is a group label, remaining columns are values
            if non_numeric_cols and numeric_cols:
                group_col = non_numeric_cols[0]
                for _, row in df.iterrows():
                    group = str(row[group_col]).strip()
                    if _is_summary_keyword(group):
                        continue
                    for col in numeric_cols:
                        try:
                            v = float(row[col])
                            if np.isfinite(v):
                                observations.append({"group": group, "time_point": str(col), "value": v})
                        except (ValueError, TypeError):
                            continue
                if len(observations) >= 3:
                    return observations
                observations = []

        except Exception:
            continue

    return observations


def stage1_python_fallback(raw_text: str, progress_callback=None) -> Dict:
    """
    Stage 1 fallback: parse tabular data into observations using pure Python.

    Strategies tried in order:
        1. Tab-separated with headers
        2. Comma-separated with headers
        3. Whitespace-separated (Excel copy-paste)
        4. pandas auto-detection

    Returns
    -------
    dict  with keys ``success``, ``observations``, ``summary``, ``fallback``
    """
    if progress_callback:
        progress_callback("stage1", "Parsing Data (Python)...")

    filtered_text = _filter_summary_rows(raw_text)
    lines = [l for l in filtered_text.strip().split("\n") if l.strip()]

    if not lines:
        return {"success": False, "error": "No data found in input", "stage": 1}

    observations: List[Dict] = []

    # Strategy 1 -- tab-separated
    obs = _try_parse_columns(lines, "\t")
    if obs and len(obs) >= 3:
        observations = obs

    # Strategy 2 -- comma-separated
    if not observations:
        obs = _try_parse_columns(lines, ",")
        if obs and len(obs) >= 3:
            observations = obs

    # Strategy 3 -- whitespace-separated
    if not observations:
        obs = _try_parse_columns(lines, None)
        if obs and len(obs) >= 3:
            observations = obs

    # Strategy 4 -- pandas auto
    if not observations:
        obs = _try_parse_with_pandas(filtered_text)
        if obs and len(obs) >= 3:
            observations = obs

    if len(observations) < 3:
        return {
            "success": False,
            "error": (
                f"Python parser found only {len(observations)} values. "
                "Data may need a different format. Try tab-separated columns with group headers."
            ),
            "stage": 1,
            "fallback": True,
        }

    groups_found = sorted(set(o["group"] for o in observations))

    return {
        "success": True,
        "observations": observations,
        "summary": {
            "total": len(observations),
            "groups": groups_found,
            "n_groups": len(groups_found),
        },
        "fallback": True,
    }


def stage1_ai_organizer(raw_text: str, progress_callback=None) -> Dict:
    """
    Stage 1: use the AI to convert messy spreadsheet text into clean JSON observations.

    Falls back to :func:`stage1_python_fallback` when Ollama is unavailable or
    the AI call fails.
    """
    if not is_ollama_available():
        return stage1_python_fallback(raw_text, progress_callback)

    if progress_callback:
        progress_callback("stage1", "AI Organizing Data...")

    filtered_text = _filter_summary_rows(raw_text)

    prompt = (
        "Analyze this raw spreadsheet data and extract all individual observations.\n\n"
        f"RAW DATA:\n{filtered_text}\n\n"
        "Extract every raw numerical value with its group and time point.\n"
        'Output as JSON array: [{"group": "X", "time_point": "Y", "value": Z}, ...]\n'
        'If no time points exist, use "All" as the time_point.'
    )

    result = call_agent(prompt, STAGE1_ORGANIZER_PROMPT, timeout=180)

    if not result["success"]:
        print(f"[Agent] AI Organizer failed: {result.get('error')}. Falling back to Python parser.")
        return stage1_python_fallback(raw_text, progress_callback)

    # Parse the JSON array from the AI response
    response = result["response"]
    try:
        json_match = re.search(r"\[[\s\S]*\]", response)
        if not json_match:
            return {"success": False, "error": "AI could not parse data structure", "stage": 1,
                    "raw_response": response}

        raw_observations = json.loads(json_match.group())
        if not isinstance(raw_observations, list) or len(raw_observations) == 0:
            return {"success": False, "error": "AI returned empty or invalid array", "stage": 1}

        # Clean and validate
        clean: List[Dict] = []
        for obs in raw_observations:
            if not isinstance(obs, dict):
                continue
            group = str(obs.get("group", "")).strip()
            time_point = str(obs.get("time_point", "All")).strip()
            value = obs.get("value")

            if _is_summary_keyword(group):
                continue
            if value is None:
                continue
            try:
                value = float(value)
            except (ValueError, TypeError):
                continue
            if not np.isfinite(value):
                continue

            clean.append({
                "group": group or "Unknown",
                "time_point": time_point or "All",
                "value": value,
            })

        if len(clean) < 3:
            return {
                "success": False,
                "error": (
                    f"AI found only {len(clean)} valid observations. "
                    "Please check your Excel sheet has actual raw data, not just summary statistics."
                ),
                "stage": 1,
            }

        groups_found = sorted(set(o["group"] for o in clean))

        return {
            "success": True,
            "observations": clean,
            "summary": {
                "total": len(clean),
                "groups": groups_found,
                "n_groups": len(groups_found),
            },
        }

    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"JSON parsing failed: {exc}", "stage": 1,
                "raw_response": response}


# ===========================================================================
# 4. STAGE 2 -- PYTHON CALCULATOR  (pure math, no AI)
# ===========================================================================

def stage2_calculator(observations: List[Dict], progress_callback=None) -> Dict:
    """
    Stage 2: deterministic statistical engine.

    * Validates N >= 3 per group
    * Descriptive statistics (n, mean, std, sem, ci_95)
    * One-Way ANOVA  (``scipy.stats.f_oneway``)
    * Tukey HSD post-hoc (``statsmodels``)
    * Power analysis (Cohen's f, observed power, recommended N)

    Returns
    -------
    dict  with keys ``success``, ``descriptive``, ``anova``, ``posthoc``,
          ``power_analysis``
    """
    if progress_callback:
        progress_callback("stage2", "Running Statistical Engine...")

    alpha = 0.05
    df = pd.DataFrame(observations)
    groups = df["group"].unique().tolist()
    time_points = df["time_point"].unique().tolist()

    # ---------- validation ----------
    group_counts = df.groupby("group").size()
    validation_errors: List[str] = []
    for group, count in group_counts.items():
        if count < 3:
            validation_errors.append(f"'{group}': N={count} (minimum 3 required)")

    if validation_errors:
        return {
            "success": False,
            "error": "Insufficient observations per group.",
            "details": validation_errors,
            "hint": (
                "Found "
                + ", ".join(f"{g}={c}" for g, c in group_counts.items())
                + ". Ensure summary rows (Mean/SD) are excluded."
            ),
            "stage": 2,
        }

    if len(groups) < 2:
        return {
            "success": False,
            "error": f"Need at least 2 groups for comparison, found only: {groups}",
            "stage": 2,
        }

    # ---------- descriptive statistics ----------
    from scipy.stats import t as t_dist

    descriptive: Dict[str, Dict] = {}
    for group in groups:
        vals = df.loc[df["group"] == group, "value"]
        n = len(vals)
        mean_val = float(vals.mean())
        std_val = float(vals.std(ddof=1))
        sem_val = std_val / np.sqrt(n)

        t_crit = t_dist.ppf(1 - alpha / 2, df=n - 1)
        ci_lo = mean_val - t_crit * sem_val
        ci_hi = mean_val + t_crit * sem_val

        descriptive[group] = {
            "n": n,
            "mean": round(mean_val, 4),
            "std": round(std_val, 4),
            "sem": round(sem_val, 4),
            "ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        }

    # ---------- One-Way ANOVA ----------
    group_arrays = [df.loc[df["group"] == g, "value"].values for g in groups]
    f_stat, p_value = f_oneway(*group_arrays)

    # Guard NaN
    if np.isnan(f_stat):
        f_stat_out = None
    else:
        f_stat_out = round(float(f_stat), 4)

    if np.isnan(p_value):
        p_value_out = None
        significant = False
    else:
        p_value_out = round(float(p_value), 6)
        significant = p_value < alpha

    anova_result: Dict[str, Any] = {
        "F_statistic": f_stat_out,
        "p_value": p_value_out,
        "significant": significant,
        "conclusion": (
            "Significant difference between groups"
            if significant
            else "No significant difference between groups"
        ),
        "alpha": alpha,
    }

    # ---------- Tukey HSD post-hoc ----------
    posthoc_result: Optional[Dict] = None
    if significant and len(groups) >= 2:
        try:
            all_values = df["value"].tolist()
            all_labels = df["group"].tolist()
            tukey = pairwise_tukeyhsd(all_values, all_labels, alpha=alpha)

            comparisons: List[Dict] = []
            for row in tukey.summary().data[1:]:
                comparisons.append({
                    "group1": str(row[0]),
                    "group2": str(row[1]),
                    "mean_diff": round(float(row[2]), 4),
                    "p_adj": round(float(row[3]), 6),
                    "significant": bool(row[6]) if isinstance(row[6], bool) else str(row[6]) == "True",
                })

            posthoc_result = {"comparisons": comparisons}
        except Exception as exc:
            posthoc_result = {"error": f"Tukey HSD failed: {exc}"}

    # ---------- power analysis ----------
    power_result: Optional[Dict] = None
    try:
        grand_mean = float(df["value"].mean())
        between_var = sum(
            descriptive[g]["n"] * (descriptive[g]["mean"] - grand_mean) ** 2
            for g in groups
        ) / (len(groups) - 1)

        within_var = float(df.groupby("group")["value"].var(ddof=1).mean())

        if within_var > 0:
            cohens_f = float(np.sqrt(between_var / within_var))
            cohens_f = round(cohens_f, 4)

            if cohens_f < 0.10:
                effect_interp = "negligible"
            elif cohens_f < 0.25:
                effect_interp = "small"
            elif cohens_f < 0.40:
                effect_interp = "medium"
            else:
                effect_interp = "large"

            avg_n = int(df.groupby("group").size().mean())
            total_n = len(df)

            from scipy.stats import f as f_dist_rv
            df_between = len(groups) - 1
            df_within = total_n - len(groups)
            ncp = cohens_f ** 2 * total_n

            f_crit = f_dist_rv.ppf(1 - alpha, df_between, df_within)
            observed_power = float(1 - f_dist_rv.cdf(f_crit, df_between, df_within, ncp))
            observed_power = round(observed_power, 4)

            # Recommended N for 80 % power
            target_power = 0.80
            if observed_power < target_power and cohens_f > 0:
                from scipy.stats import norm
                z_alpha = norm.ppf(1 - alpha / 2)
                z_beta = norm.ppf(target_power)
                recommended_n = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (cohens_f ** 2)))
            else:
                recommended_n = avg_n

            power_result = {
                "effect_size_f": cohens_f,
                "effect_interpretation": effect_interp,
                "observed_power": observed_power,
                "current_n_per_group": avg_n,
                "adequate_power": observed_power >= 0.80,
                "recommended_n_per_group": recommended_n,
                "power_note": (
                    "Power >= 0.80 is generally considered adequate"
                    if observed_power >= 0.80
                    else f"Consider increasing to N={recommended_n} per group for 80% power"
                ),
            }
    except Exception as exc:
        power_result = {"error": f"Power analysis failed: {exc}"}

    # ---------- assemble ----------
    return {
        "success": True,
        "descriptive": descriptive,
        "anova": anova_result,
        "posthoc": posthoc_result,
        "power_analysis": power_result,
    }


# ===========================================================================
# 5. STAGE 3 -- AI REPORTER  (with Python fallback)
# ===========================================================================

# ---- Test-type keyword banks for context-aware interpretation ----

_HIGHER_BETTER_KEYWORDS = [
    "microhardness", "hardness", "vickers", "knoop",
    "shear bond", "bond strength", "tensile", "compressive",
    "flexural", "mpa", "adhesion", "retention",
    "survival", "success rate", "efficacy", "strength",
]

_LOWER_BETTER_KEYWORDS = [
    "crystal violet", "absorbance", "biofilm", "bacterial", "cfu",
    "roughness", "ra", "surface roughness", "wear", "abrasion",
    "microleakage", "leakage", "gap", "marginal", "porosity",
    "cytotoxicity", "inflammation", "pain",
]


def _detect_test_type(context: str, hint: str = None) -> Dict:
    """
    Determine whether higher or lower values indicate a better outcome.

    Returns ``{"category": "higher_better"|"lower_better"|"unknown",
               "detected_type": str|None}``
    """
    if hint:
        hint_lower = hint.lower()
        if hint_lower in ("higher", "higher_better", "strength", "hardness", "bond"):
            return {"category": "higher_better", "detected_type": hint}
        if hint_lower in ("lower", "lower_better", "biofilm", "roughness", "wear"):
            return {"category": "lower_better", "detected_type": hint}

    context_lower = (context or "").lower()

    for kw in _HIGHER_BETTER_KEYWORDS:
        if kw in context_lower:
            return {"category": "higher_better", "detected_type": kw}

    for kw in _LOWER_BETTER_KEYWORDS:
        if kw in context_lower:
            return {"category": "lower_better", "detected_type": kw}

    return {"category": "unknown", "detected_type": None}


# ---- Python fallback report ----

def stage3_python_fallback(stats_results: Dict, proposal_context: str = "",
                           test_type_hint: str = None,
                           progress_callback=None) -> str:
    """
    Stage 3 fallback: build a professional plain-text report using templates
    when Ollama is not available.
    """
    if progress_callback:
        progress_callback("stage3", "Generating Report (Python)...")

    lines: List[str] = []
    lines.append("=" * 64)
    lines.append("  STATISTICAL ANALYSIS REPORT")
    lines.append("=" * 64)

    test_info = _detect_test_type(proposal_context, test_type_hint)
    category = test_info["category"]
    detected = test_info["detected_type"]

    if detected:
        label = "higher = better" if category == "higher_better" else (
            "lower = better" if category == "lower_better" else "neutral"
        )
        lines.append(f"  Test Type: {detected} ({label})")
    lines.append("")

    # ---- descriptive table ----
    desc = stats_results.get("descriptive", {})
    if desc:
        lines.append("-" * 64)
        lines.append("  DESCRIPTIVE STATISTICS")
        lines.append("-" * 64)
        lines.append(
            f"  {'Group':<20} {'N':>5} {'Mean':>10} {'SD':>10} {'SEM':>10} {'95% CI':>20}"
        )
        lines.append("  " + "-" * 58)
        for group, s in desc.items():
            ci = s.get("ci_95", [None, None])
            if ci[0] is not None:
                ci_str = f"[{ci[0]:.2f}, {ci[1]:.2f}]"
            else:
                ci_str = "N/A"
            lines.append(
                f"  {group:<20} {s['n']:>5} {s['mean']:>10.4f} "
                f"{s['std']:>10.4f} {s['sem']:>10.4f} {ci_str:>20}"
            )
        lines.append("")

    # ---- ANOVA table ----
    anova = stats_results.get("anova", {})
    if anova:
        lines.append("-" * 64)
        lines.append("  ONE-WAY ANOVA")
        lines.append("-" * 64)
        f_stat = anova.get("F_statistic", "N/A")
        p_val = anova.get("p_value", "N/A")
        sig = anova.get("significant", False)

        lines.append(f"  F-statistic: {f_stat}")
        lines.append(f"  p-value:     {p_val}")

        if isinstance(p_val, (int, float)):
            if p_val < 0.001:
                lines.append("  Result:      *** HIGHLY SIGNIFICANT (p < 0.001)")
            elif p_val < 0.01:
                lines.append("  Result:      ** VERY SIGNIFICANT (p < 0.01)")
            elif p_val < 0.05:
                lines.append("  Result:      * SIGNIFICANT (p < 0.05)")
            else:
                lines.append("  Result:      Not significant (p >= 0.05)")
        lines.append("")

        # Directional interpretation
        if sig and desc:
            sorted_groups = sorted(desc.items(), key=lambda x: x[1]["mean"], reverse=True)
            if category == "higher_better":
                best = sorted_groups[0][0]
                lines.append(
                    f"  Interpretation: {best} showed the highest mean, "
                    "indicating superior performance."
                )
            elif category == "lower_better":
                best = sorted_groups[-1][0]
                lines.append(
                    f"  Interpretation: {best} showed the lowest mean, "
                    "indicating superior performance."
                )
            else:
                lines.append("  Interpretation: Significant differences exist between groups.")
        elif not sig:
            lines.append("  Interpretation: No statistically significant differences between groups.")
        lines.append("")

    # ---- Tukey HSD comparisons ----
    posthoc = stats_results.get("posthoc")
    if posthoc and posthoc.get("comparisons"):
        lines.append("-" * 64)
        lines.append("  POST-HOC: TUKEY HSD PAIRWISE COMPARISONS")
        lines.append("-" * 64)
        lines.append(f"  {'Comparison':<30} {'Diff':>8} {'p-adj':>10} {'Sig':>6}")
        lines.append("  " + "-" * 54)
        for comp in posthoc["comparisons"]:
            if comp["significant"] and comp["p_adj"] < 0.001:
                sig_mark = "***"
            elif comp["significant"] and comp["p_adj"] < 0.01:
                sig_mark = "**"
            elif comp["significant"]:
                sig_mark = "*"
            else:
                sig_mark = ""
            pair = f"{comp['group1']} vs {comp['group2']}"
            lines.append(
                f"  {pair:<30} {comp['mean_diff']:>8.4f} "
                f"{comp['p_adj']:>10.6f} {sig_mark:>6}"
            )
        lines.append("")

        sig_pairs = [c for c in posthoc["comparisons"] if c["significant"]]
        if sig_pairs:
            lines.append(f"  Significant pairs ({len(sig_pairs)}):")
            for c in sig_pairs:
                lines.append(f"    - {c['group1']} vs {c['group2']} (p = {c['p_adj']:.6f})")
        else:
            lines.append("  No pairwise comparisons reached significance.")
        lines.append("")

    # ---- Power analysis ----
    power = stats_results.get("power_analysis")
    if power and not power.get("error"):
        lines.append("-" * 64)
        lines.append("  POWER ANALYSIS")
        lines.append("-" * 64)
        lines.append(f"  Effect size (Cohen's f): {power.get('effect_size_f', 'N/A')}")
        lines.append(f"  Effect interpretation:   {power.get('effect_interpretation', 'N/A')}")
        lines.append(f"  Observed power:          {power.get('observed_power', 'N/A')}")
        lines.append(f"  Current N per group:     {power.get('current_n_per_group', 'N/A')}")
        if not power.get("adequate_power", True):
            lines.append(f"  Recommended N per group: {power.get('recommended_n_per_group', 'N/A')}")
            lines.append(f"  Note: {power.get('power_note', '')}")
        else:
            lines.append("  Power is adequate (>= 0.80)")
        lines.append("")

    lines.append("=" * 64)
    lines.append("  [Report generated by Python fallback -- Ollama not available]")
    lines.append("=" * 64)

    return "\n".join(lines)


# ---- AI reporter ----

_STAGE3_REPORTER_PROMPT = """You are a dental research statistician writing results for an academic paper.

STRICT RULES:
1. Use ONLY the exact statistics provided -- NEVER invent or modify numbers.
2. Report p-values, F-statistics, means, and SDs exactly as given.
3. Clearly state which comparisons are significant (p < 0.05).
4. Apply the correct interpretation based on the test type.

{test_type_instruction}

Write a professional academic paragraph suitable for the Results section.
Be specific: state exact p-values, mean differences, and group comparisons.
Do NOT include methodology -- only results interpretation."""


def stage3_ai_reporter(stats_results: Dict, proposal_context: str = "",
                       test_type_hint: str = None,
                       progress_callback=None) -> str:
    """
    Stage 3: AI-generated professional statistical report.

    Falls back to :func:`stage3_python_fallback` when Ollama is unavailable.
    """
    if not is_ollama_available():
        return stage3_python_fallback(stats_results, proposal_context, test_type_hint,
                                      progress_callback)

    if progress_callback:
        progress_callback("stage3", "Generating Report...")

    test_info = _detect_test_type(proposal_context, test_type_hint)
    category = test_info["category"]
    detected = test_info.get("detected_type", "unknown test")

    if category == "higher_better":
        test_instruction = (
            f"TEST TYPE: {detected} (HIGHER values = BETTER)\n"
            "- The group with HIGHEST mean has the best performance\n"
            "- Significant increases indicate improvement"
        )
    elif category == "lower_better":
        test_instruction = (
            f"TEST TYPE: {detected} (LOWER values = BETTER)\n"
            "- The group with LOWEST mean has the best performance\n"
            "- Significant decreases indicate improvement"
        )
    else:
        test_instruction = (
            "TEST TYPE: Unknown -- interpret neutrally\n"
            "- Report significant differences without implying which is 'better'"
        )

    system_prompt = _STAGE3_REPORTER_PROMPT.format(test_type_instruction=test_instruction)

    # Build a concise stats summary for the AI
    anova = stats_results.get("anova", {})
    stats_text = (
        "STATISTICAL RESULTS (use these exact numbers):\n\n"
        f"ANOVA: F = {anova.get('F_statistic')}, p = {anova.get('p_value')}\n"
        f"Result: {'SIGNIFICANT' if anova.get('significant') else 'Not significant'}\n\n"
        "DESCRIPTIVE STATISTICS:\n"
    )
    for group, s in stats_results.get("descriptive", {}).items():
        stats_text += f"  {group}: Mean = {s['mean']}, SD = {s['std']}, N = {s['n']}\n"

    posthoc = stats_results.get("posthoc")
    if posthoc and posthoc.get("comparisons"):
        stats_text += "\nPOST-HOC COMPARISONS (Tukey HSD):\n"
        for comp in posthoc["comparisons"]:
            sig = "***" if comp["significant"] else ""
            stats_text += (
                f"  {comp['group1']} vs {comp['group2']}: "
                f"diff = {comp['mean_diff']}, p = {comp['p_adj']} {sig}\n"
            )

    pa = stats_results.get("power_analysis")
    if pa and not pa.get("error"):
        stats_text += (
            f"\nPOWER ANALYSIS: Observed power = {pa['observed_power']} "
            f"({pa['effect_interpretation']} effect)\n"
        )

    prompt = (
        "Write a professional academic results paragraph.\n\n"
        f"{stats_text}\n"
        "RESEARCH CONTEXT:\n"
        f"{proposal_context if proposal_context else 'Dental materials research study comparing groups.'}\n\n"
        "Generate a clear, professional interpretation using the exact statistics above."
    )

    result = call_agent(prompt, system_prompt, timeout=180)

    if result["success"]:
        return result["response"]

    print(f"[Agent] AI Reporter failed: {result.get('error')}. Falling back to Python report.")
    return stage3_python_fallback(stats_results, proposal_context, test_type_hint, progress_callback)


# ===========================================================================
# 6. PIPELINE ORCHESTRATION
# ===========================================================================

def run_3stage_pipeline(raw_text: str, proposal_context: str = "",
                        test_type_hint: str = None,
                        progress_callback=None) -> Dict:
    """
    Execute the complete 3-stage pipeline:

    1. AI (or Python) organises raw text into observations.
    2. Python computes ANOVA, Tukey HSD, descriptive stats, power.
    3. AI (or Python) generates a professional report.

    Returns
    -------
    dict  with keys ``success``, ``stage1``, ``stage2``, ``stage3``, ``failed_stage``
    """
    pipeline: Dict[str, Any] = {
        "success": False,
        "stage1": None,
        "stage2": None,
        "stage3": None,
    }

    # ===== Stage 1 =====
    stage1 = stage1_ai_organizer(raw_text, progress_callback)
    pipeline["stage1"] = stage1

    if not stage1.get("success"):
        pipeline["error"] = stage1.get("error", "Stage 1 failed")
        pipeline["failed_stage"] = 1
        return pipeline

    # ===== Stage 2 =====
    stage2 = stage2_calculator(stage1["observations"], progress_callback)
    pipeline["stage2"] = stage2

    if not stage2.get("success"):
        pipeline["error"] = stage2.get("error", "Stage 2 failed")
        pipeline["failed_stage"] = 2
        return pipeline

    # ===== Stage 3 =====
    report = stage3_ai_reporter(
        stage2,
        proposal_context=proposal_context,
        test_type_hint=test_type_hint,
        progress_callback=progress_callback,
    )
    pipeline["stage3"] = {
        "test_type": _detect_test_type(proposal_context, test_type_hint),
        "report": report,
    }

    if progress_callback:
        progress_callback("complete", "Analysis Complete")

    pipeline["success"] = True
    return pipeline


def run_universal_analysis(raw_text: str, proposal_context: str = "",
                           test_type_hint: str = None,
                           progress_callback=None) -> Dict:
    """
    Legacy wrapper that maps the 3-stage output to the old ``layer1`` / ``layer2`` /
    ``layer3`` key structure expected by earlier front-end code.
    """
    result = run_3stage_pipeline(raw_text, proposal_context, test_type_hint,
                                 progress_callback)

    if not result["success"]:
        return result

    stage1 = result["stage1"]
    stage2 = result["stage2"]
    stage3 = result["stage3"]

    return {
        "success": True,
        "layer1_extraction": {
            "groups_found": stage1["summary"]["groups"],
            "n_groups": stage1["summary"]["n_groups"],
            "samples_per_group": {
                g: len([o for o in stage1["observations"] if o["group"] == g])
                for g in stage1["summary"]["groups"]
            },
        },
        "layer2_statistics": {
            "descriptive": stage2["descriptive"],
            "anova": stage2["anova"],
            "posthoc": stage2["posthoc"],
            "power_analysis": stage2["power_analysis"],
        },
        "layer3_interpretation": {
            "test_type": stage3["test_type"],
            "report": stage3["report"],
        },
    }


# ===========================================================================
# 7. AGENTIC FEATURES
# ===========================================================================

# ---------- Feature A: Messy Data Agent ----------

_CLEANING_SYSTEM_PROMPT = """You are a data scientist assistant. Analyze messy spreadsheet data
and extract structured information.

When given raw data, you must:
1. Identify the groups / categories in the data
2. Identify time points or conditions
3. Extract the numerical values for each group at each time point

OUTPUT FORMAT (JSON only, no other text):
{
  "groups": ["Group1", "Group2"],
  "timepoints": ["Time1", "Time2"],
  "data": {
    "Group1": {"Time1": [val1, val2], "Time2": [val1, val2]},
    "Group2": {"Time1": [val1, val2], "Time2": [val1, val2]}
  }
}

Only output valid JSON."""


def agent_messy_data(df: pd.DataFrame, user_description: str = "") -> Dict:
    """
    Analyse a messy DataFrame end-to-end.

    1. Convert the DataFrame to text.
    2. Run the 3-stage pipeline (AI or fallback).
    3. Return structured results + interpretation.
    """
    # Convert DataFrame to a text dump the pipeline can consume
    raw_text = df.to_string(index=False)

    result = run_3stage_pipeline(raw_text, proposal_context=user_description)

    if not result["success"]:
        return {"success": False, "error": result.get("error", "Analysis failed"),
                "failed_stage": result.get("failed_stage")}

    return {
        "success": True,
        "structured_data": result["stage1"]["observations"],
        "statistics": result["stage2"],
        "interpretation": result["stage3"]["report"],
    }


# ---------- Feature B: Sample-Size Agent ----------

def agent_sample_size(study_text: str) -> Dict:
    """
    Extract Mean / SD values from *study_text* (a pasted abstract, paragraph,
    or table) and compute sample-size recommendations.

    Strategy:
        1. Regex extraction of mean +/- SD patterns.
        2. If AI is available, ask it to extract values as well.
        3. Compute Cohen's d and required N per group.
    """
    # --- Regex extraction ---
    patterns = [
        # "Mean = 5.2, SD = 1.3" or "mean: 5.2  sd: 1.3"
        r"[Mm]ean\s*[:=]\s*([\d.]+)\s*,?\s*(?:SD|sd|S\.D\.|Std\.?\s*Dev\.?)\s*[:=]\s*([\d.]+)",
        # "5.2 +/- 1.3" or "5.2 +- 1.3"
        r"([\d.]+)\s*(?:\+/?-|\+-|\\pm)\s*([\d.]+)",
        # "M = 5.2 (SD = 1.3)"
        r"[Mm]\s*=\s*([\d.]+)\s*\(\s*(?:SD|sd)\s*=\s*([\d.]+)\s*\)",
    ]

    extracted_pairs: List[Dict] = []
    for pat in patterns:
        for match in re.finditer(pat, study_text):
            try:
                mean_val = float(match.group(1))
                sd_val = float(match.group(2))
                if sd_val > 0:
                    extracted_pairs.append({"mean": mean_val, "sd": sd_val})
            except (ValueError, IndexError):
                continue

    # --- AI extraction (if available and regex found nothing) ---
    if not extracted_pairs and is_ollama_available():
        ai_prompt = (
            "Extract all Mean and Standard Deviation pairs from the following text. "
            "Output JSON only:\n"
            '[{"mean": X, "sd": Y}, ...]\n\n'
            f"TEXT:\n{study_text}"
        )
        ai_result = call_agent(ai_prompt, timeout=60)
        if ai_result["success"]:
            try:
                json_match = re.search(r"\[[\s\S]*?\]", ai_result["response"])
                if json_match:
                    pairs = json.loads(json_match.group())
                    for p in pairs:
                        m = float(p.get("mean", 0))
                        s = float(p.get("sd", 0))
                        if s > 0:
                            extracted_pairs.append({"mean": m, "sd": s})
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    # --- Compute sample size ---
    if len(extracted_pairs) >= 2:
        m1, s1 = extracted_pairs[0]["mean"], extracted_pairs[0]["sd"]
        m2, s2 = extracted_pairs[1]["mean"], extracted_pairs[1]["sd"]
        pooled_sd = float(np.sqrt((s1 ** 2 + s2 ** 2) / 2))
        cohens_d = abs(m2 - m1) / pooled_sd if pooled_sd > 0 else 0.0
    elif len(extracted_pairs) == 1:
        # Only one pair found: assume medium effect (d = 0.5) relative to found SD
        cohens_d = 0.5
        m1, s1 = extracted_pairs[0]["mean"], extracted_pairs[0]["sd"]
        m2, s2 = None, None
        pooled_sd = s1
    else:
        # No data at all: use Cohen's medium
        cohens_d = 0.5
        m1, s1, m2, s2, pooled_sd = None, None, None, None, None

    from scipy.stats import norm
    alpha = 0.05
    power = 0.80
    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)

    if cohens_d > 0:
        n_per_group = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (cohens_d ** 2)))
    else:
        n_per_group = 64  # fallback for d=0.5

    if cohens_d < 0.2:
        interp = "negligible"
    elif cohens_d < 0.5:
        interp = "small"
    elif cohens_d < 0.8:
        interp = "medium"
    else:
        interp = "large"

    return {
        "success": True,
        "extracted_pairs": extracted_pairs,
        "effect_size": round(cohens_d, 4),
        "interpretation": interp,
        "n_per_group": n_per_group,
        "total_n": n_per_group * 2,
        "alpha": alpha,
        "power": power,
        "source": "extracted from text" if extracted_pairs else "default (Cohen's medium effect)",
    }


# ---------- Feature C: Literature Review Agent ----------

def agent_literature_review(query: str) -> Dict:
    """
    Search for academic literature on *query* and optionally synthesise
    the results into a review paragraph.

    Uses DuckDuckGo when available; falls back to a stub message.
    If Ollama is available the raw results are synthesised by the AI.
    """
    # Step 1 -- web search
    search_results: List[Dict] = []
    if HAS_DDGS:
        try:
            academic_query = (
                f"{query} site:pubmed.gov OR site:scholar.google.com "
                "OR site:arxiv.org OR site:researchgate.net"
            )
            with DDGS() as ddgs:
                raw = list(ddgs.text(academic_query, max_results=8))
                search_results = [
                    {
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "href": r.get("href", ""),
                        "source": "web_search",
                    }
                    for r in raw
                ]
        except Exception as exc:
            search_results = [{"error": str(exc)}]
    else:
        search_results = [{"error": "duckduckgo-search not installed"}]

    # Remove error entries for downstream processing
    valid_results = [r for r in search_results if "error" not in r]

    if not valid_results:
        return {
            "success": False,
            "error": "No search results found. Install duckduckgo-search for web lookup.",
            "search_results": search_results,
        }

    # Compile references
    references: List[Dict] = []
    search_text = "Literature Search Results:\n\n"
    for i, r in enumerate(valid_results[:10]):
        search_text += f"[{i + 1}] {r.get('title', 'N/A')}\n"
        search_text += f"    Summary: {r.get('body', '')}\n"
        search_text += f"    Source: {r.get('href', '')}\n\n"
        references.append({
            "number": i + 1,
            "title": r.get("title", ""),
            "url": r.get("href", ""),
        })

    # Step 2 -- AI synthesis (if available)
    if is_ollama_available():
        lit_system = (
            "You are an academic researcher. Given search results, synthesise "
            "the information into a coherent literature review with inline "
            "citations like [1], [2]. Be objective and scholarly."
        )
        prompt = (
            f"Write a literature review on: {query}\n\n"
            f"{search_text}\n"
            "Synthesise these sources into a coherent review."
        )
        ai_result = call_agent(prompt, lit_system, timeout=120)
        review = ai_result["response"] if ai_result["success"] else None
    else:
        review = None

    # Fallback: plain summary
    if not review:
        lines = [f"Literature Search: '{query}'", "=" * 50, ""]
        for ref in references:
            lines.append(f"  [{ref['number']}] {ref['title']}")
            body = valid_results[ref["number"] - 1].get("body", "")
            if body:
                lines.append(f"      {body[:200]}")
            lines.append("")
        lines.append("(AI synthesis unavailable -- showing raw search results)")
        review = "\n".join(lines)

    return {
        "success": True,
        "review": review,
        "references": references,
        "sources_searched": len(valid_results),
    }


# ===========================================================================
# BACKWARD-COMPATIBILITY WRAPPERS
# ===========================================================================
# These keep ``app.py`` (and other callers) working without changes.

def search_web(query: str, max_results: int = 5) -> List[Dict]:
    """Search the web using DuckDuckGo."""
    if not HAS_DDGS:
        return [{"error": "duckduckgo-search not installed"}]
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                {"title": r.get("title", ""), "body": r.get("body", ""),
                 "href": r.get("href", "")}
                for r in results
            ]
    except Exception as exc:
        return [{"error": str(exc)}]


def search_academic(query: str, max_results: int = 5) -> List[Dict]:
    """Search for academic papers via DuckDuckGo."""
    if not HAS_DDGS:
        return [{"error": "duckduckgo-search not installed"}]
    try:
        academic_query = (
            f"{query} site:pubmed.gov OR site:scholar.google.com "
            "OR site:arxiv.org OR site:researchgate.net"
        )
        with DDGS() as ddgs:
            results = list(ddgs.text(academic_query, max_results=max_results))
            return [
                {"title": r.get("title", ""), "body": r.get("body", ""),
                 "href": r.get("href", ""), "source": "web_search"}
                for r in results
            ]
    except Exception as exc:
        return [{"error": str(exc)}]


def parse_pdf(file_path: str) -> str:
    """Extract text from a PDF file on disk."""
    if not HAS_PDF:
        return "[Error: PyPDF2 not installed]"
    try:
        text = ""
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except Exception as exc:
        return f"[Error parsing PDF: {exc}]"


def parse_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes (uploaded file)."""
    if not HAS_PDF:
        return "[Error: PyPDF2 not installed]"
    try:
        text = ""
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as exc:
        return f"[Error parsing PDF: {exc}]"


def run_messy_data_analysis(raw_text: str, context: str = "") -> Dict:
    """Legacy entry-point used by ``app.py`` for messy-data analysis."""
    result = run_3stage_pipeline(raw_text, proposal_context=context)
    if result["success"]:
        return {
            "success": True,
            "structured_data": result["stage1"]["observations"],
            "statistics": result["stage2"],
            "interpretation": result["stage3"]["report"],
        }
    return {"error": result.get("error", "Pipeline failed"),
            "step": f"stage{result.get('failed_stage', '?')}"}


def search_for_sample_size_data(topic: str) -> Dict:
    """
    Legacy wrapper: search the web for Mean/SD values on *topic* and
    compute a sample-size recommendation.
    """
    # Try web search first to build study_text
    results = search_academic(topic + " mean standard deviation sample size", max_results=8)
    valid = [r for r in results if "error" not in r]

    if valid:
        study_text = "\n".join(
            f"{r.get('title', '')} -- {r.get('body', '')}" for r in valid
        )
    else:
        study_text = topic

    ss = agent_sample_size(study_text)
    ss["search_results"] = results
    return ss


def calculate_sample_size_manual(effect_size: float, alpha: float = 0.05,
                                  power: float = 0.80,
                                  test_type: str = "t-test") -> Dict:
    """Manual sample-size calculation with user-provided parameters."""
    from scipy.stats import norm

    try:
        z_alpha = norm.ppf(1 - alpha / 2)
        z_beta = norm.ppf(power)

        n_per_group = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (effect_size ** 2)))

        if test_type in ("anova", "ANOVA"):
            total_n = n_per_group * 3  # default 3 groups
        else:
            total_n = n_per_group * 2

        if effect_size < 0.2:
            interp = "negligible"
        elif effect_size < 0.5:
            interp = "small"
        elif effect_size < 0.8:
            interp = "medium"
        else:
            interp = "large"

        return {
            "success": True,
            "effect_size": effect_size,
            "interpretation": interp,
            "n_per_group": n_per_group,
            "total_n": total_n,
            "alpha": alpha,
            "power": power,
            "test_type": test_type,
        }
    except Exception as exc:
        return {"error": str(exc)}


def generate_literature_review(topic: str, context: str = "") -> Dict:
    """Legacy wrapper used by ``app.py``."""
    query = f"{topic} {context}".strip() if context else topic
    return agent_literature_review(query)


def run_agent_task(task_type: str, **kwargs) -> Dict:
    """Central dispatcher -- keeps the old orchestrator interface alive."""
    if task_type == "messy_data":
        return run_messy_data_analysis(kwargs.get("raw_text", ""),
                                       kwargs.get("context", ""))

    if task_type == "sample_size_auto":
        return search_for_sample_size_data(kwargs.get("topic", ""))

    if task_type == "sample_size_manual":
        return calculate_sample_size_manual(
            kwargs.get("effect_size", 0.5),
            kwargs.get("alpha", 0.05),
            kwargs.get("power", 0.80),
            kwargs.get("test_type", "t-test"),
        )

    if task_type == "literature_review":
        return generate_literature_review(kwargs.get("topic", ""),
                                           kwargs.get("context", ""))

    if task_type == "web_search":
        results = search_web(kwargs.get("query", ""), kwargs.get("max_results", 5))
        return {"success": True, "results": results}

    if task_type == "parse_pdf":
        if "file_path" in kwargs:
            text = parse_pdf(kwargs["file_path"])
        elif "pdf_bytes" in kwargs:
            text = parse_pdf_bytes(kwargs["pdf_bytes"])
        else:
            return {"error": "No PDF file provided"}
        return {"success": True, "text": text}

    if task_type == "universal_analyze":
        return run_universal_analysis(
            kwargs.get("raw_text", ""),
            kwargs.get("proposal_context", ""),
            kwargs.get("test_type_hint", None),
        )

    return {"error": f"Unknown task type: {task_type}"}
