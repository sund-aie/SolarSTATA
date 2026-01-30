"""
SolarSTATA Agent Core
Agentic workflow orchestrator using Ollama for reasoning and Python for computation.
Implements the separation: Math=Python, Search=Python, Logic/Text=Ollama
"""

import ollama
import subprocess
import json
import re
import pandas as pd
import numpy as np
from scipy import stats as sp_stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import threading
import queue
from typing import Optional, Dict, List, Any

# Try to import web search tools
try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False
    print("[Agent] duckduckgo-search not installed. Run: pip install duckduckgo-search")

try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    print("[Agent] PyPDF2 not installed. Run: pip install PyPDF2")


# ---------------------------------------------------------------------------
# OLLAMA MODEL MANAGEMENT
# ---------------------------------------------------------------------------

def get_available_models() -> List[str]:
    """Get list of locally available Ollama models."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return ["llama3.2"]

        lines = result.stdout.strip().split("\n")
        models = []
        for line in lines[1:]:  # Skip header
            if line.strip():
                # Format: NAME  ID  SIZE  MODIFIED
                parts = line.split()
                if parts:
                    model_name = parts[0]
                    # Remove :latest suffix for cleaner display
                    if ":latest" in model_name:
                        model_name = model_name.replace(":latest", "")
                    models.append(model_name)

        return models if models else ["llama3.2"]
    except Exception as e:
        print(f"[Agent] Error listing models: {e}")
        return ["llama3.2"]


def check_ollama_running() -> bool:
    """Check if Ollama service is running."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# Current model selection
_current_model = "llama3.2"


def set_model(model_name: str):
    """Set the current Ollama model to use."""
    global _current_model
    _current_model = model_name


def get_model() -> str:
    """Get the currently selected model."""
    return _current_model


# ---------------------------------------------------------------------------
# WEB SEARCH TOOLS (Python-based)
# ---------------------------------------------------------------------------

def search_web(query: str, max_results: int = 5) -> List[Dict]:
    """Search the web using DuckDuckGo."""
    if not HAS_DDGS:
        return [{"error": "duckduckgo-search not installed"}]

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "href": r.get("href", ""),
                }
                for r in results
            ]
    except Exception as e:
        return [{"error": str(e)}]


def search_academic(query: str, max_results: int = 5) -> List[Dict]:
    """Search for academic papers."""
    if not HAS_DDGS:
        return [{"error": "duckduckgo-search not installed"}]

    try:
        # Add academic keywords to improve results
        academic_query = f"{query} site:pubmed.gov OR site:scholar.google.com OR site:arxiv.org OR site:researchgate.net"
        with DDGS() as ddgs:
            results = list(ddgs.text(academic_query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "href": r.get("href", ""),
                    "source": "web_search"
                }
                for r in results
            ]
    except Exception as e:
        return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# PDF PARSING
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    if not HAS_PDF:
        return "[Error: PyPDF2 not installed]"

    try:
        text = ""
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"[Error parsing PDF: {e}]"


def parse_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes."""
    if not HAS_PDF:
        return "[Error: PyPDF2 not installed]"

    try:
        import io
        text = ""
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"[Error parsing PDF: {e}]"


# ---------------------------------------------------------------------------
# AGENT: CALL OLLAMA WITH TIMEOUT
# ---------------------------------------------------------------------------

def call_agent(prompt: str, system_prompt: str = None, timeout: int = 120) -> Dict:
    """
    Call the Ollama agent with a timeout.
    Returns: {"success": bool, "response": str, "error": str}
    """
    result_queue = queue.Queue()

    def _call():
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            resp = ollama.chat(
                model=_current_model,
                messages=messages,
            )
            result_queue.put({"success": True, "response": resp["message"]["content"]})
        except Exception as e:
            result_queue.put({"success": False, "error": str(e)})

    thread = threading.Thread(target=_call)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        return {"success": False, "error": f"Timeout after {timeout} seconds"}

    try:
        return result_queue.get_nowait()
    except:
        return {"success": False, "error": "No response received"}


# ---------------------------------------------------------------------------
# FEATURE A: MESSY DATA ANALYSIS AGENT
# ---------------------------------------------------------------------------

CLEANING_SYSTEM_PROMPT = """You are a data scientist assistant. Your task is to analyze messy spreadsheet data and extract structured information.

When given raw data, you must:
1. Identify the groups/categories in the data
2. Identify time points or conditions
3. Extract the numerical values for each group at each time point

OUTPUT FORMAT (JSON only, no other text):
{
  "groups": ["Group1 Name", "Group2 Name", ...],
  "timepoints": ["Time1", "Time2", ...],
  "data": {
    "Group1 Name": {
      "Time1": [val1, val2, val3, ...],
      "Time2": [val1, val2, val3, ...]
    },
    "Group2 Name": {
      "Time1": [val1, val2, val3, ...],
      "Time2": [val1, val2, val3, ...]
    }
  }
}

Only output valid JSON. No explanations before or after."""


def agent_clean_messy_data(raw_data_text: str) -> Dict:
    """
    Step 1: Use AI to understand and structure messy data.
    Returns structured JSON that Python can process.
    """
    prompt = f"""Analyze this spreadsheet data and extract the structure:

{raw_data_text}

Identify all groups, time points, and numerical values. Output as JSON only."""

    result = call_agent(prompt, CLEANING_SYSTEM_PROMPT, timeout=60)

    if not result["success"]:
        return {"error": result.get("error", "AI call failed")}

    # Parse JSON from response
    response = result["response"]
    try:
        # Try to extract JSON from the response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            structured = json.loads(json_match.group())
            return {"success": True, "structured_data": structured}
        else:
            return {"error": "Could not parse JSON from AI response", "raw": response}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parsing error: {e}", "raw": response}


def python_run_anova(structured_data: Dict) -> Dict:
    """
    Step 2: Python-based ANOVA and Post-hoc Tukey tests.
    This is the MATH part - never let AI guess numbers.
    """
    try:
        groups = structured_data.get("groups", [])
        timepoints = structured_data.get("timepoints", [])
        data = structured_data.get("data", {})

        results = {
            "anova_results": {},
            "posthoc_results": {},
            "descriptive_stats": {}
        }

        # For each timepoint, run ANOVA across groups
        for tp in timepoints:
            group_data = []
            group_labels = []

            for group in groups:
                values = data.get(group, {}).get(tp, [])
                if values:
                    # Convert to float
                    float_values = [float(v) for v in values if v is not None]
                    if float_values:
                        group_data.append(float_values)
                        group_labels.extend([group] * len(float_values))

            if len(group_data) >= 2:
                # Run One-Way ANOVA
                f_stat, p_val = sp_stats.f_oneway(*group_data)

                results["anova_results"][tp] = {
                    "F_statistic": round(f_stat, 4) if not np.isnan(f_stat) else None,
                    "p_value": round(p_val, 4) if not np.isnan(p_val) else None,
                    "significant": p_val < 0.05 if not np.isnan(p_val) else False,
                    "n_groups": len(group_data),
                }

                # Descriptive stats per group
                results["descriptive_stats"][tp] = {}
                for i, group in enumerate(groups):
                    if i < len(group_data):
                        arr = np.array(group_data[i])
                        results["descriptive_stats"][tp][group] = {
                            "n": len(arr),
                            "mean": round(arr.mean(), 4),
                            "std": round(arr.std(ddof=1), 4) if len(arr) > 1 else 0,
                            "sem": round(sp_stats.sem(arr), 4) if len(arr) > 1 else 0,
                        }

                # Post-hoc Tukey if significant and >2 groups
                if p_val < 0.05 and len(group_data) > 2:
                    all_values = []
                    all_labels = []
                    for i, group in enumerate(groups):
                        if i < len(group_data):
                            all_values.extend(group_data[i])
                            all_labels.extend([group] * len(group_data[i]))

                    try:
                        tukey = pairwise_tukeyhsd(all_values, all_labels, alpha=0.05)
                        comparisons = []
                        for row in tukey.summary().data[1:]:
                            comparisons.append({
                                "group1": str(row[0]),
                                "group2": str(row[1]),
                                "mean_diff": round(float(row[2]), 4),
                                "p_adj": round(float(row[3]), 4),
                                "significant": row[6] == True or str(row[6]) == "True"
                            })
                        results["posthoc_results"][tp] = comparisons
                    except Exception as e:
                        results["posthoc_results"][tp] = {"error": str(e)}

        return {"success": True, "results": results}

    except Exception as e:
        return {"error": str(e)}


INTERPRETATION_SYSTEM_PROMPT = """You are a statistical consultant. Given ANOVA results, write a clear interpretation.

Be specific about:
- Whether there are significant differences between groups
- Which specific groups differ (from post-hoc tests)
- What these findings mean practically

Keep it concise and professional. Use the exact p-values and statistics provided."""


def agent_interpret_results(stats_results: Dict, context: str = "") -> str:
    """
    Step 3: AI interprets the calculated statistics.
    """
    prompt = f"""Interpret these statistical results:

{json.dumps(stats_results, indent=2)}

Context: {context if context else "Data analysis comparing groups across time points."}

Write a clear statistical interpretation."""

    result = call_agent(prompt, INTERPRETATION_SYSTEM_PROMPT, timeout=60)

    if result["success"]:
        return result["response"]
    else:
        return f"[Interpretation unavailable: {result.get('error', 'Unknown error')}]"


def run_messy_data_analysis(raw_text: str, context: str = "") -> Dict:
    """
    Full pipeline for messy data analysis.
    """
    # Step 1: AI cleans/structures the data
    cleaned = agent_clean_messy_data(raw_text)
    if "error" in cleaned:
        return {"error": f"Data cleaning failed: {cleaned['error']}", "step": "cleaning"}

    # Step 2: Python runs the statistics
    stats = python_run_anova(cleaned["structured_data"])
    if "error" in stats:
        return {"error": f"Statistical analysis failed: {stats['error']}", "step": "statistics"}

    # Step 3: AI interprets the results
    interpretation = agent_interpret_results(stats["results"], context)

    return {
        "success": True,
        "structured_data": cleaned["structured_data"],
        "statistics": stats["results"],
        "interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# FEATURE B: DUAL-MODE SAMPLE SIZE CALCULATOR
# ---------------------------------------------------------------------------

SAMPLE_SIZE_SEARCH_PROMPT = """You are a research assistant. Given search results about a research topic, extract Mean and Standard Deviation values reported in the studies.

Look for patterns like:
- "Mean = X, SD = Y"
- "M = X (SD = Y)"
- "X +/- Y"
- Tables with means and standard deviations

OUTPUT FORMAT (JSON only):
{
  "studies_found": [
    {
      "title": "Study title or source",
      "control_mean": 5.2,
      "control_sd": 1.3,
      "treatment_mean": 7.8,
      "treatment_sd": 1.5,
      "sample_size": 30
    }
  ],
  "pooled_effect_size": 0.5,
  "recommended_effect_size": "medium",
  "notes": "Any relevant observations"
}

Only output JSON. If no values found, return empty studies_found array."""


def search_for_sample_size_data(topic: str) -> Dict:
    """
    AI-powered sample size estimation through web search.
    """
    # Step 1: Search for relevant studies
    search_query = f"{topic} mean standard deviation sample size clinical study"
    search_results = search_academic(search_query, max_results=8)

    if not search_results or (len(search_results) == 1 and "error" in search_results[0]):
        return {"error": "Web search failed or unavailable"}

    # Compile search results into text
    search_text = "Search Results:\n\n"
    for i, r in enumerate(search_results):
        if "error" not in r:
            search_text += f"[{i+1}] {r.get('title', 'N/A')}\n"
            search_text += f"    {r.get('body', '')}\n"
            search_text += f"    URL: {r.get('href', '')}\n\n"

    # Step 2: AI extracts Mean/SD values
    prompt = f"""Topic: {topic}

{search_text}

Extract any Mean and Standard Deviation values from these search results to estimate effect size for sample size calculation."""

    result = call_agent(prompt, SAMPLE_SIZE_SEARCH_PROMPT, timeout=90)

    if not result["success"]:
        return {"error": result.get("error", "AI extraction failed")}

    # Parse the response
    try:
        json_match = re.search(r'\{[\s\S]*\}', result["response"])
        if json_match:
            extracted = json.loads(json_match.group())
        else:
            extracted = {"studies_found": [], "notes": result["response"]}
    except json.JSONDecodeError:
        extracted = {"studies_found": [], "notes": result["response"]}

    # Step 3: Calculate sample size if we have effect size
    sample_size_result = None

    if extracted.get("studies_found"):
        # Calculate effect size from first complete study
        for study in extracted["studies_found"]:
            if all(k in study for k in ["control_mean", "control_sd", "treatment_mean", "treatment_sd"]):
                try:
                    m1 = float(study["control_mean"])
                    s1 = float(study["control_sd"])
                    m2 = float(study["treatment_mean"])
                    s2 = float(study["treatment_sd"])

                    # Cohen's d
                    pooled_sd = np.sqrt((s1**2 + s2**2) / 2)
                    cohens_d = abs(m2 - m1) / pooled_sd

                    # Sample size calculation
                    from scipy.stats import norm
                    alpha = 0.05
                    power = 0.80
                    z_alpha = norm.ppf(1 - alpha/2)
                    z_beta = norm.ppf(power)

                    n_per_group = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (cohens_d ** 2)))

                    sample_size_result = {
                        "effect_size": round(cohens_d, 4),
                        "interpretation": "small" if cohens_d < 0.5 else "medium" if cohens_d < 0.8 else "large",
                        "n_per_group": n_per_group,
                        "total_n": n_per_group * 2,
                        "alpha": alpha,
                        "power": power,
                        "source_study": study.get("title", "Extracted from search"),
                    }
                    break
                except (ValueError, ZeroDivisionError):
                    continue

    # If no effect size found, use default
    if not sample_size_result:
        # Default to medium effect size
        cohens_d = 0.5
        from scipy.stats import norm
        z_alpha = norm.ppf(0.975)
        z_beta = norm.ppf(0.80)
        n_per_group = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (cohens_d ** 2)))

        sample_size_result = {
            "effect_size": cohens_d,
            "interpretation": "medium (default - no specific data found)",
            "n_per_group": n_per_group,
            "total_n": n_per_group * 2,
            "alpha": 0.05,
            "power": 0.80,
            "source_study": "Default (Cohen's medium effect)",
        }

    return {
        "success": True,
        "search_results": search_results,
        "extracted_data": extracted,
        "sample_size": sample_size_result,
    }


def calculate_sample_size_manual(effect_size: float, alpha: float = 0.05,
                                  power: float = 0.80, test_type: str = "t-test") -> Dict:
    """
    Manual sample size calculation with user-provided parameters.
    """
    from scipy.stats import norm

    try:
        z_alpha = norm.ppf(1 - alpha / 2)
        z_beta = norm.ppf(power)

        if test_type in ["t-test", "ttest", "two-sample"]:
            # Two-sample t-test
            n_per_group = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (effect_size ** 2)))
            total_n = n_per_group * 2
        elif test_type in ["anova", "ANOVA"]:
            # Simplified ANOVA (using f to d conversion approximation)
            n_per_group = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (effect_size ** 2)))
            total_n = n_per_group * 3  # Assume 3 groups
        else:
            n_per_group = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (effect_size ** 2)))
            total_n = n_per_group * 2

        interpretation = "small" if effect_size < 0.5 else "medium" if effect_size < 0.8 else "large"

        return {
            "success": True,
            "effect_size": effect_size,
            "interpretation": interpretation,
            "n_per_group": n_per_group,
            "total_n": total_n,
            "alpha": alpha,
            "power": power,
            "test_type": test_type,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# FEATURE C: LITERATURE REVIEW AGENT
# ---------------------------------------------------------------------------

LIT_REVIEW_SYSTEM_PROMPT = """You are an academic researcher writing a literature review. Given search results, synthesize the information into a coherent review with proper citations.

Requirements:
1. Organize information thematically
2. Include inline citations like (Author, Year) or [1], [2]
3. Highlight key findings and gaps in the literature
4. Be objective and scholarly in tone

Format the output as a proper literature review section."""


def generate_literature_review(topic: str, context: str = "") -> Dict:
    """
    Full literature review agent workflow.
    """
    # Step 1: Generate search queries
    queries = [
        topic,
        f"{topic} systematic review",
        f"{topic} meta-analysis",
        f"{topic} clinical trial",
    ]

    all_results = []
    for query in queries[:2]:  # Limit to avoid too many searches
        results = search_academic(query, max_results=5)
        if results and "error" not in results[0]:
            all_results.extend(results)

    if not all_results:
        return {"error": "No search results found"}

    # Remove duplicates by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url = r.get("href", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)

    # Step 2: Compile results for AI
    search_text = "Literature Search Results:\n\n"
    references = []
    for i, r in enumerate(unique_results[:10]):  # Top 10
        search_text += f"[{i+1}] {r.get('title', 'N/A')}\n"
        search_text += f"    Summary: {r.get('body', '')}\n"
        search_text += f"    Source: {r.get('href', '')}\n\n"
        references.append({
            "number": i + 1,
            "title": r.get("title", ""),
            "url": r.get("href", ""),
        })

    # Step 3: AI synthesizes review
    prompt = f"""Write a literature review on: {topic}

{f"Additional context: {context}" if context else ""}

{search_text}

Synthesize these sources into a coherent literature review. Use [1], [2], etc. to cite sources."""

    result = call_agent(prompt, LIT_REVIEW_SYSTEM_PROMPT, timeout=120)

    if not result["success"]:
        return {"error": result.get("error", "AI generation failed")}

    return {
        "success": True,
        "review": result["response"],
        "references": references,
        "sources_searched": len(unique_results),
    }


# ---------------------------------------------------------------------------
# AGENT ORCHESTRATOR
# ---------------------------------------------------------------------------

def run_agent_task(task_type: str, **kwargs) -> Dict:
    """
    Main orchestrator for all agent tasks.
    """
    if task_type == "messy_data":
        return run_messy_data_analysis(
            kwargs.get("raw_text", ""),
            kwargs.get("context", "")
        )

    elif task_type == "sample_size_auto":
        return search_for_sample_size_data(
            kwargs.get("topic", "")
        )

    elif task_type == "sample_size_manual":
        return calculate_sample_size_manual(
            kwargs.get("effect_size", 0.5),
            kwargs.get("alpha", 0.05),
            kwargs.get("power", 0.80),
            kwargs.get("test_type", "t-test")
        )

    elif task_type == "literature_review":
        return generate_literature_review(
            kwargs.get("topic", ""),
            kwargs.get("context", "")
        )

    elif task_type == "web_search":
        results = search_web(kwargs.get("query", ""), kwargs.get("max_results", 5))
        return {"success": True, "results": results}

    elif task_type == "parse_pdf":
        if "file_path" in kwargs:
            text = parse_pdf(kwargs["file_path"])
        elif "pdf_bytes" in kwargs:
            text = parse_pdf_bytes(kwargs["pdf_bytes"])
        else:
            return {"error": "No PDF file provided"}
        return {"success": True, "text": text}

    elif task_type == "universal_analyze":
        return run_universal_analysis(
            kwargs.get("raw_text", ""),
            kwargs.get("proposal_context", ""),
            kwargs.get("test_type_hint", None)
        )

    else:
        return {"error": f"Unknown task type: {task_type}"}


# ---------------------------------------------------------------------------
# 3-STAGE PIPELINE: ORGANIZER -> CALCULATOR -> REPORTER
# ---------------------------------------------------------------------------
# Stage 1: AI organizes raw data into clean JSON
# Stage 2: Python calculates statistics (ANOVA, Tukey, Power)
# Stage 3: AI generates professional report
# ---------------------------------------------------------------------------

# Test type categorization for context-aware interpretation
TEST_TYPE_CATEGORIES = {
    # Higher = Better (strength, hardness, efficacy)
    "higher_better": [
        "microhardness", "hardness", "vickers", "knoop", "shear bond",
        "bond strength", "tensile", "compressive", "flexural", "mpa",
        "adhesion", "retention", "survival", "success rate", "efficacy"
    ],
    # Lower = Better (bacterial, roughness, wear, leakage)
    "lower_better": [
        "crystal violet", "absorbance", "biofilm", "bacterial", "cfu",
        "roughness", "ra", "surface roughness", "wear", "abrasion",
        "microleakage", "leakage", "gap", "marginal", "porosity",
        "cytotoxicity", "inflammation", "pain"
    ]
}

# Summary row keywords to filter out (Python safety net)
SUMMARY_ROW_KEYWORDS = [
    'mean', 'average', 'avg', 'm=',
    'sd', 'std', 'stdev', 'standard deviation', 's.d.',
    'sem', 'se', 'standard error',
    'n=', 'count', 'total', 'sum',
    'min', 'max', 'range', 'median'
]


# ===========================================================================
# STAGE 1: AI DATA ORGANIZER
# ===========================================================================

STAGE1_ORGANIZER_PROMPT = """You are a data extraction specialist. Your job is to convert messy spreadsheet data into a clean, standardized JSON format.

CRITICAL INSTRUCTIONS:
1. Find ALL raw observation data (individual measurements)
2. Identify the GROUP each value belongs to (e.g., "Control", "Cow Milk", "Soy Milk", "Treatment A")
3. If there are TIME POINTS or CONDITIONS, identify those too (e.g., "Baseline", "Day 7", "Day 14")
4. Extract each individual numerical value

ABSOLUTELY IGNORE (these are summary statistics, NOT raw data):
- Rows labeled "Mean", "Average", "Avg"
- Rows labeled "SD", "Std Dev", "StDev", "Standard Deviation"
- Rows labeled "SEM", "SE", "Standard Error"
- Rows labeled "N=", "n=", "Count", "Total", "Sum"
- Rows labeled "Min", "Max", "Range", "Median"
- Any calculated/aggregated values at the bottom of columns

OUTPUT FORMAT - Array of observation objects (JSON only, no other text):
[
    {"group": "Control", "time_point": "Baseline", "value": 466.4},
    {"group": "Control", "time_point": "Baseline", "value": 472.1},
    {"group": "Cow Milk", "time_point": "Day 7", "value": 389.2},
    ...
]

If there are NO time points, use "All" as the time_point value.

Output ONLY valid JSON array. No explanations, no markdown, just the JSON."""


def stage1_ai_organizer(raw_text: str, progress_callback=None) -> Dict:
    """
    STAGE 1: AI DATA ORGANIZER

    Takes raw spreadsheet text dump and uses AI to extract clean JSON.
    Output format: [{"group": "X", "time_point": "Y", "value": Z}, ...]
    """
    if progress_callback:
        progress_callback("stage1", "AI Organizing Data...")

    # Pre-filter obvious summary rows
    filtered_text = _filter_summary_rows(raw_text)

    prompt = f"""Analyze this raw spreadsheet data and extract all individual observations.

RAW DATA:
{filtered_text}

Extract every raw numerical value with its group and time point.
Output as JSON array: [{{"group": "X", "time_point": "Y", "value": Z}}, ...]
If no time points exist, use "All" as the time_point."""

    result = call_agent(prompt, STAGE1_ORGANIZER_PROMPT, timeout=180)

    if not result["success"]:
        error_msg = result.get("error", "Unknown error")
        if "Timeout" in error_msg:
            error_msg = f"AI Organizer timed out. Ensure Ollama is running ('ollama serve') and a model is loaded."
        return {"error": error_msg, "stage": 1}

    # Parse JSON from response
    response = result["response"]
    try:
        # Extract JSON array from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            observations = json.loads(json_match.group())

            # Validate structure
            if not isinstance(observations, list):
                return {"error": "AI returned invalid format (expected array)", "stage": 1}

            if len(observations) == 0:
                return {"error": "AI found no data. Check if your file has raw observations.", "stage": 1}

            # Clean and validate each observation
            clean_observations = []
            for obs in observations:
                if not isinstance(obs, dict):
                    continue

                group = str(obs.get("group", "")).strip()
                time_point = str(obs.get("time_point", "All")).strip()
                value = obs.get("value")

                # Skip if group looks like a summary keyword
                if _is_summary_keyword(group):
                    continue

                # Skip if no valid value
                if value is None:
                    continue

                try:
                    value = float(value)
                    if not np.isnan(value) and not np.isinf(value):
                        clean_observations.append({
                            "group": group if group else "Unknown",
                            "time_point": time_point if time_point else "All",
                            "value": value
                        })
                except (ValueError, TypeError):
                    continue

            if len(clean_observations) < 3:
                return {
                    "error": "Error: No raw data found. Only found {} values. Please check your Excel sheet has actual observations, not just summary statistics.".format(len(clean_observations)),
                    "stage": 1
                }

            # Summary of what was found
            groups_found = list(set(o["group"] for o in clean_observations))
            timepoints_found = list(set(o["time_point"] for o in clean_observations))

            return {
                "success": True,
                "observations": clean_observations,
                "summary": {
                    "total_observations": len(clean_observations),
                    "groups": groups_found,
                    "time_points": timepoints_found,
                    "n_groups": len(groups_found),
                    "n_timepoints": len(timepoints_found)
                }
            }
        else:
            return {"error": "AI could not parse data structure", "stage": 1, "raw_response": response}

    except json.JSONDecodeError as e:
        return {"error": f"JSON parsing failed: {e}", "stage": 1, "raw_response": response}


def _filter_summary_rows(raw_text: str) -> str:
    """Pre-filter lines that contain summary statistics keywords."""
    lines = raw_text.split('\n')
    filtered_lines = []

    for line in lines:
        line_lower = line.lower().strip()
        if not line_lower:
            filtered_lines.append(line)
            continue

        is_summary = False
        for keyword in SUMMARY_ROW_KEYWORDS:
            if line_lower.startswith(keyword) or f'\t{keyword}' in line_lower or f' {keyword}' in line_lower:
                is_summary = True
                break

        if not is_summary:
            filtered_lines.append(line)

    return '\n'.join(filtered_lines)


def _is_summary_keyword(text: str) -> bool:
    """Check if text matches a summary keyword."""
    text_lower = text.lower().strip()
    for keyword in SUMMARY_ROW_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


# ===========================================================================
# STAGE 2: PYTHON CALCULATION ENGINE (THE AUTOMATIC SYSTEM)
# ===========================================================================

def stage2_calculator(observations: List[Dict], alpha: float = 0.05,
                      progress_callback=None) -> Dict:
    """
    STAGE 2: PYTHON CALCULATION ENGINE

    Pure Python statistics - NO AI guessing allowed.
    - Validation: N >= 3 per group
    - One-Way ANOVA
    - Tukey HSD (if significant)
    - Power Analysis
    - Descriptive Statistics
    """
    if progress_callback:
        progress_callback("stage2", "Running Statistical Engine...")

    # Convert observations to DataFrame
    df = pd.DataFrame(observations)

    # Get unique groups and time points
    groups = df["group"].unique().tolist()
    time_points = df["time_point"].unique().tolist()

    # =========== VALIDATION ===========
    validation_errors = []

    # Check N per group (must be >= 3)
    group_counts = df.groupby("group").size()
    for group, count in group_counts.items():
        if count < 3:
            validation_errors.append(
                f"'{group}': N={count} (minimum 3 required)"
            )

    if validation_errors:
        return {
            "error": "Error: No raw data found. Please check your Excel sheet.",
            "details": validation_errors,
            "hint": "Found only {} observations per group. Ensure summary rows (Mean/SD) are excluded.".format(
                ", ".join([f"{g}={c}" for g, c in group_counts.items()])
            ),
            "stage": 2
        }

    if len(groups) < 2:
        return {
            "error": f"Need at least 2 groups for comparison, found only: {groups}",
            "stage": 2
        }

    # =========== DESCRIPTIVE STATISTICS ===========
    descriptive = {}
    for group in groups:
        group_data = df[df["group"] == group]["value"]
        n = len(group_data)
        mean = float(group_data.mean())
        std = float(group_data.std(ddof=1))
        sem = std / np.sqrt(n)

        # 95% Confidence Interval
        from scipy.stats import t as t_dist
        t_crit = t_dist.ppf(1 - alpha/2, df=n-1)
        ci_lower = mean - t_crit * sem
        ci_upper = mean + t_crit * sem

        descriptive[group] = {
            "n": n,
            "mean": round(mean, 4),
            "std": round(std, 4),
            "sem": round(sem, 4),
            "ci_95": [round(ci_lower, 4), round(ci_upper, 4)],
            "min": round(float(group_data.min()), 4),
            "max": round(float(group_data.max()), 4)
        }

    # =========== ONE-WAY ANOVA ===========
    group_arrays = [df[df["group"] == g]["value"].values for g in groups]
    f_stat, p_value = sp_stats.f_oneway(*group_arrays)

    # Handle NaN
    if np.isnan(f_stat):
        f_stat = None
    else:
        f_stat = round(float(f_stat), 4)

    if np.isnan(p_value):
        p_value = None
        significant = False
    else:
        p_value = round(float(p_value), 6)
        significant = p_value < alpha

    anova_result = {
        "test": "One-Way ANOVA",
        "F_statistic": f_stat,
        "p_value": p_value,
        "alpha": alpha,
        "significant": significant,
        "conclusion": "Significant difference between groups" if significant else "No significant difference between groups"
    }

    # =========== POST-HOC TUKEY HSD ===========
    posthoc_result = None
    if significant and len(groups) >= 2:
        try:
            all_values = df["value"].tolist()
            all_labels = df["group"].tolist()

            tukey = pairwise_tukeyhsd(all_values, all_labels, alpha=alpha)
            comparisons = []

            for row in tukey.summary().data[1:]:
                comparisons.append({
                    "group1": str(row[0]),
                    "group2": str(row[1]),
                    "mean_diff": round(float(row[2]), 4),
                    "p_adj": round(float(row[3]), 6),
                    "ci_lower": round(float(row[4]), 4),
                    "ci_upper": round(float(row[5]), 4),
                    "significant": bool(row[6]) if isinstance(row[6], bool) else str(row[6]) == "True"
                })

            posthoc_result = {
                "test": "Tukey HSD",
                "comparisons": comparisons
            }
        except Exception as e:
            posthoc_result = {"error": f"Tukey HSD failed: {str(e)}"}

    # =========== POWER ANALYSIS ===========
    power_result = None
    try:
        # Calculate effect size (Cohen's f)
        grand_mean = df["value"].mean()
        between_var = sum(
            descriptive[g]["n"] * (descriptive[g]["mean"] - grand_mean) ** 2
            for g in groups
        ) / (len(groups) - 1)

        within_var = df.groupby("group")["value"].var(ddof=1).mean()

        if within_var > 0:
            cohens_f = np.sqrt(between_var / within_var)
            cohens_f = round(float(cohens_f), 4)

            # Interpret effect size
            if cohens_f < 0.1:
                effect_interpretation = "negligible"
            elif cohens_f < 0.25:
                effect_interpretation = "small"
            elif cohens_f < 0.4:
                effect_interpretation = "medium"
            else:
                effect_interpretation = "large"

            # Calculate observed power (simplified)
            avg_n = int(df.groupby("group").size().mean())
            total_n = len(df)

            # Power calculation using noncentrality parameter
            from scipy.stats import f as f_dist
            df_between = len(groups) - 1
            df_within = total_n - len(groups)
            ncp = cohens_f ** 2 * total_n  # Noncentrality parameter

            f_crit = f_dist.ppf(1 - alpha, df_between, df_within)
            observed_power = 1 - f_dist.cdf(f_crit, df_between, df_within, ncp)
            observed_power = round(float(observed_power), 4)

            # Recommend sample size for 80% power
            target_power = 0.80
            if observed_power < target_power and cohens_f > 0:
                # Approximate required N per group
                from scipy.stats import norm
                z_alpha = norm.ppf(1 - alpha/2)
                z_beta = norm.ppf(target_power)
                recommended_n = int(np.ceil(2 * ((z_alpha + z_beta) ** 2) / (cohens_f ** 2)))
            else:
                recommended_n = avg_n

            power_result = {
                "effect_size_f": cohens_f,
                "effect_interpretation": effect_interpretation,
                "observed_power": observed_power,
                "current_n_per_group": avg_n,
                "recommended_n_per_group": recommended_n,
                "adequate_power": observed_power >= 0.80,
                "power_note": "Power >= 0.80 is generally considered adequate" if observed_power >= 0.80
                             else f"Consider increasing to N={recommended_n} per group for 80% power"
            }
    except Exception as e:
        power_result = {"error": f"Power analysis failed: {str(e)}"}

    # =========== BUILD RESULT ===========
    return {
        "success": True,
        "summary": {
            "total_observations": len(df),
            "n_groups": len(groups),
            "groups": groups,
            "time_points": time_points
        },
        "descriptive": descriptive,
        "anova": anova_result,
        "posthoc": posthoc_result,
        "power_analysis": power_result
    }


# ===========================================================================
# STAGE 3: AI REPORTER
# ===========================================================================

STAGE3_REPORTER_PROMPT = """You are a dental research statistician writing results for an academic paper.

STRICT RULES:
1. Use ONLY the exact statistics provided - NEVER invent or modify numbers
2. Report p-values, F-statistics, means, and SDs exactly as given
3. Clearly state which comparisons are significant (p < 0.05)
4. Apply the correct interpretation based on the test type

{test_type_instruction}

Write a professional academic paragraph suitable for the Results section.
Be specific: state exact p-values, mean differences, and group comparisons.
Do NOT include methodology - only results interpretation."""


def stage3_ai_reporter(stats_results: Dict, proposal_context: str = "",
                       test_type_hint: str = None, progress_callback=None) -> str:
    """
    STAGE 3: AI REPORTER

    Takes proven statistics and generates professional report.
    Uses context to determine correct interpretation (higher/lower = better).
    """
    if progress_callback:
        progress_callback("stage3", "Generating Report...")

    # Detect test type for interpretation
    test_type_info = _detect_test_type(proposal_context, test_type_hint)
    category = test_type_info.get("category", "unknown")
    detected = test_type_info.get("detected_type", "unknown test")

    if category == "higher_better":
        test_instruction = f"""TEST TYPE: {detected} (HIGHER values = BETTER)
- The group with HIGHEST mean has the best performance
- Significant increases indicate improvement
- Example: "Group A showed significantly higher microhardness (p<0.05), indicating superior mechanical properties" """
    elif category == "lower_better":
        test_instruction = f"""TEST TYPE: {detected} (LOWER values = BETTER)
- The group with LOWEST mean has the best performance
- Significant decreases indicate improvement
- Example: "Group A showed significantly lower absorbance (p<0.05), indicating superior anti-biofilm activity" """
    else:
        test_instruction = """TEST TYPE: Unknown - Interpret neutrally
- Report significant differences without implying which is "better"
- Example: "Group A showed significantly different values compared to Control (p<0.05)" """

    system_prompt = STAGE3_REPORTER_PROMPT.format(test_type_instruction=test_instruction)

    # Build statistics summary for AI
    stats_text = f"""
STATISTICAL RESULTS (use these exact numbers):

ANOVA: F = {stats_results['anova']['F_statistic']}, p = {stats_results['anova']['p_value']}
Result: {'SIGNIFICANT' if stats_results['anova']['significant'] else 'Not significant'}

DESCRIPTIVE STATISTICS:
"""
    for group, stats in stats_results['descriptive'].items():
        stats_text += f"  {group}: Mean = {stats['mean']}, SD = {stats['std']}, N = {stats['n']}\n"

    if stats_results.get('posthoc') and stats_results['posthoc'].get('comparisons'):
        stats_text += "\nPOST-HOC COMPARISONS (Tukey HSD):\n"
        for comp in stats_results['posthoc']['comparisons']:
            sig = "***" if comp['significant'] else ""
            stats_text += f"  {comp['group1']} vs {comp['group2']}: diff = {comp['mean_diff']}, p = {comp['p_adj']} {sig}\n"

    if stats_results.get('power_analysis') and not stats_results['power_analysis'].get('error'):
        pa = stats_results['power_analysis']
        stats_text += f"\nPOWER ANALYSIS: Observed power = {pa['observed_power']} ({pa['effect_interpretation']} effect)\n"

    prompt = f"""Write a professional academic results paragraph.

{stats_text}

RESEARCH CONTEXT:
{proposal_context if proposal_context else "Dental materials research study comparing groups."}

Generate a clear, professional interpretation using the exact statistics above."""

    result = call_agent(prompt, system_prompt, timeout=180)

    if result["success"]:
        return result["response"]
    else:
        return f"[Report generation failed: {result.get('error', 'Unknown error')}]"


def _detect_test_type(context: str, hint: str = None) -> Dict:
    """Detect test type from context for correct interpretation."""
    if hint:
        if hint.lower() in ["higher", "higher_better", "strength", "hardness"]:
            return {"category": "higher_better", "detected_type": hint}
        elif hint.lower() in ["lower", "lower_better", "biofilm", "roughness"]:
            return {"category": "lower_better", "detected_type": hint}

    context_lower = context.lower()

    for keyword in TEST_TYPE_CATEGORIES["higher_better"]:
        if keyword in context_lower:
            return {"category": "higher_better", "detected_type": keyword}

    for keyword in TEST_TYPE_CATEGORIES["lower_better"]:
        if keyword in context_lower:
            return {"category": "lower_better", "detected_type": keyword}

    return {"category": "unknown", "detected_type": None}


# ===========================================================================
# MAIN PIPELINE: RUN ALL 3 STAGES
# ===========================================================================

def run_3stage_pipeline(raw_text: str, proposal_context: str = "",
                        test_type_hint: str = None, alpha: float = 0.05,
                        progress_callback=None) -> Dict:
    """
    COMPLETE 3-STAGE PIPELINE

    Stage 1: AI organizes raw data into clean JSON
    Stage 2: Python calculates statistics (no AI guessing)
    Stage 3: AI generates professional report

    Returns detailed results from each stage.
    """
    pipeline_result = {
        "stage1": None,
        "stage2": None,
        "stage3": None,
        "success": False
    }

    # ===== STAGE 1: AI DATA ORGANIZER =====
    stage1_result = stage1_ai_organizer(raw_text, progress_callback)
    pipeline_result["stage1"] = stage1_result

    if "error" in stage1_result:
        pipeline_result["error"] = stage1_result["error"]
        pipeline_result["failed_stage"] = 1
        return pipeline_result

    # ===== STAGE 2: PYTHON CALCULATOR =====
    stage2_result = stage2_calculator(
        stage1_result["observations"],
        alpha=alpha,
        progress_callback=progress_callback
    )
    pipeline_result["stage2"] = stage2_result

    if "error" in stage2_result:
        pipeline_result["error"] = stage2_result["error"]
        pipeline_result["failed_stage"] = 2
        return pipeline_result

    # ===== STAGE 3: AI REPORTER =====
    report = stage3_ai_reporter(
        stage2_result,
        proposal_context=proposal_context,
        test_type_hint=test_type_hint,
        progress_callback=progress_callback
    )
    pipeline_result["stage3"] = {
        "report": report,
        "test_type": _detect_test_type(proposal_context, test_type_hint)
    }

    if progress_callback:
        progress_callback("complete", "Analysis Complete")

    pipeline_result["success"] = True
    return pipeline_result


# ===========================================================================
# LEGACY COMPATIBILITY: Keep old function names working
# ===========================================================================

def run_universal_analysis(raw_text: str, proposal_context: str = "",
                           test_type_hint: str = None) -> Dict:
    """Legacy wrapper - redirects to 3-stage pipeline."""
    result = run_3stage_pipeline(raw_text, proposal_context, test_type_hint)

    # Convert to old format for compatibility
    if result["success"]:
        return {
            "success": True,
            "layer1_extraction": {
                "groups_found": result["stage1"]["summary"]["groups"],
                "n_groups": result["stage1"]["summary"]["n_groups"],
                "samples_per_group": {
                    g: len([o for o in result["stage1"]["observations"] if o["group"] == g])
                    for g in result["stage1"]["summary"]["groups"]
                }
            },
            "layer2_statistics": {
                "descriptive": result["stage2"]["descriptive"],
                "anova": result["stage2"]["anova"],
                "posthoc": result["stage2"]["posthoc"],
                "power_analysis": result["stage2"]["power_analysis"]
            },
            "layer3_interpretation": {
                "test_type": result["stage3"]["test_type"],
                "report": result["stage3"]["report"]
            }
        }
    else:
        return result
