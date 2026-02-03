"""
SolarSTATA — Flask Application Server

Routes:
  /                          → main page
  /api/upload                → upload CSV/Excel
  /api/data/preview          → preview loaded data
  /api/data/columns          → list columns & types
  /api/stats/<test>          → run a statistical test
  /api/agent/*               → AI agent endpoints
  /api/health                → health-check
"""

import os, json, traceback
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, render_template

import stats_engine as se

# Lazy-import heavy modules so startup is fast
_ai_brain = None
_agent_core = None

def _brain():
    global _ai_brain
    if _ai_brain is None:
        import ai_brain; _ai_brain = ai_brain
    return _ai_brain

def _agent():
    global _agent_core
    if _agent_core is None:
        import agent_core; _agent_core = agent_core
    return _agent_core

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory data store (single-user)
# ---------------------------------------------------------------------------
_store = {"df": None, "filename": None, "columns": [], "dtypes": {}}


def _set_data(df, filename):
    _store["df"] = df
    _store["filename"] = filename
    _store["columns"] = list(df.columns)
    _store["dtypes"] = {str(c): str(df[c].dtype) for c in df.columns}


def _get_df():
    return _store["df"]


# ---------------------------------------------------------------------------
# JSON safety — converts NaN / Inf / numpy types to JSON-safe values
# ---------------------------------------------------------------------------
def _safe(obj):
    """Recursively sanitise an object for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.ndarray):
        return _safe(obj.tolist())
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.DataFrame):
        return json.loads(obj.to_json(orient="records"))
    if isinstance(obj, pd.Series):
        return json.loads(obj.to_json())
    return obj


def _ok(result):
    """Wrap a result dict in a JSON response with sanitisation."""
    return jsonify({"result": _safe(result)})


def _err(msg, code=400):
    return jsonify({"error": str(msg)}), code


# ---------------------------------------------------------------------------
# Format helpers — produce Stata-style plain-text output strings
# ---------------------------------------------------------------------------

def _fmt_anova(r):
    """Format one-way ANOVA result as Stata-style table."""
    lines = []
    lines.append("                        Analysis of Variance")
    lines.append(f"    Source              SS         df      MS            F     Prob > F")
    lines.append("  " + "-" * 68)
    at = r.get("anova_table", {})
    src = at.get("Source", [])
    ss = at.get("SS", [])
    df_vals = at.get("df", [])
    ms = at.get("MS", [])
    fv = at.get("F", [])
    pv = at.get("Prob", [])
    for i in range(len(src)):
        s = f"    {str(src[i]):<18}"
        s += f" {str(ss[i]):>10}" if ss[i] != "" else " " * 11
        s += f" {str(df_vals[i]):>6}" if df_vals[i] != "" else " " * 7
        s += f" {str(ms[i]):>12}" if ms[i] != "" else " " * 13
        s += f" {str(fv[i]):>10}" if fv[i] != "" else " " * 11
        s += f" {str(pv[i]):>10}" if pv[i] != "" else " " * 11
        lines.append(s)
    lines.append("")
    p = r.get("p")
    if p is not None:
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        lines.append(f"    F({at['df'][0] if at.get('df') else '?'}, "
                     f"{at['df'][1] if at.get('df') and len(at['df'])>1 else '?'}) = "
                     f"{r.get('F', '?')}    Prob > F = {p} {sig}")
    lines.append("")
    for gs in r.get("group_stats", []):
        lines.append(f"    {gs['Group']:<20}  N={gs['N']}  Mean={gs['Mean']}  SD={gs['SD']}")
    lines.append("")
    b = r.get("bartlett", {})
    l = r.get("levene", {})
    if b:
        lines.append(f"    Bartlett's test:  chi2 = {b.get('chi2','?')}  Prob>chi2 = {b.get('p','?')}")
    if l:
        lines.append(f"    Levene's test:   F = {l.get('F','?')}  Prob>F = {l.get('p','?')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ROUTES — main page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# ROUTES — file upload & data
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("No file provided")
    fname = f.filename.lower()
    path = os.path.join(UPLOAD_DIR, f.filename)
    f.save(path)
    try:
        if fname.endswith(".csv"):
            df = pd.read_csv(path)
        elif fname.endswith((".xlsx", ".xls")):
            df = pd.read_excel(path)
        elif fname.endswith(".dta"):
            df = pd.read_stata(path)
        else:
            return _err("Unsupported format. Use CSV, Excel, or Stata (.dta)")
        # Clean data
        try:
            df = _brain().smart_clean(df)
        except Exception:
            df = se.clean_data(df)
        _set_data(df, f.filename)
        # Build data_info for the frontend
        var_types = se.detect_variable_types(df)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = [c for c in df.columns if c not in numeric_cols]
        var_info = json.loads(var_types.to_json(orient="records")) if var_types is not None else []
        group_candidates = [{"column": c, "n_groups": int(df[c].nunique())}
                            for c in cat_cols if 1 < df[c].nunique() <= 20]
        missing = {str(c): int(df[c].isnull().sum()) for c in df.columns}
        data_info = {
            "variable_info": var_info,
            "numeric_columns": numeric_cols,
            "categorical_columns": cat_cols,
            "group_candidates": group_candidates,
            "missing_summary": missing,
        }
        preview = json.loads(df.head(100).to_json(orient="records"))
        return jsonify(_safe({
            "message": f"Loaded {f.filename}: {len(df)} obs, {len(df.columns)} vars",
            "rows": len(df),
            "columns": list(df.columns),
            "dtypes": {str(c): str(df[c].dtype) for c in df.columns},
            "filename": f.filename,
            "shape": [len(df), len(df.columns)],
            "data_info": data_info,
            "preview": preview,
        }))
    except Exception as e:
        return _err(f"Failed to read file: {e}")


@app.route("/api/data/preview")
def data_preview():
    df = _get_df()
    if df is None:
        return _err("No data loaded")
    n = min(int(request.args.get("n", 100)), len(df))
    return jsonify({"columns": list(df.columns),
                    "rows": json.loads(df.head(n).to_json(orient="records")),
                    "total_rows": len(df), "shown": n})


@app.route("/api/data/columns")
def data_columns():
    df = _get_df()
    if df is None:
        return _err("No data loaded")
    info = se.detect_variable_types(df)
    return jsonify({"columns": json.loads(info.to_json(orient="records"))})


# ---------------------------------------------------------------------------
# ROUTES — statistical tests
# ---------------------------------------------------------------------------

@app.route("/api/stats/descriptive", methods=["POST"])
def stat_descriptive():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    variables = d.get("variables") or df.select_dtypes(include=[np.number]).columns.tolist()
    detail = d.get("detail", True)
    r = se.descriptive(df, variables, detail=detail)
    return _ok({"table": json.loads(r.to_json(orient="records")),
                "output": r.to_string(index=False)})


@app.route("/api/stats/tabulate", methods=["POST"])
def stat_tabulate():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    r = se.tabulate(df, d["var1"], d.get("var2"))
    return _ok({"table": json.loads(r.to_json(orient="records")), "output": r.to_string()})


@app.route("/api/stats/normality", methods=["POST"])
def stat_normality():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    r = se.normality(df, d["variable"])
    # Normalize keys for frontend
    r.setdefault("Shapiro_W", r.get("SW_W")); r.setdefault("Shapiro_p", r.get("SW_p"))
    r.setdefault("normal", (r.get("SW_p") or 1) > 0.05)
    return _ok(r)


@app.route("/api/stats/ttest", methods=["POST"])
def stat_ttest():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    tt = d.get("type", "two_sample")
    try:
        if tt == "one_sample":
            r = se.ttest_one(df, d["variable"], mu=float(d.get("mu", 0)))
            r.setdefault("t_stat", r.get("t")); r.setdefault("p", r.get("p_two"))
        elif tt == "paired":
            r = se.ttest_paired(df, d["var1"], d["var2"])
            r.setdefault("t_stat", r.get("t"))
        else:
            r = se.ttest_two(df, d["variable"], d["groupvar"])
            # Add canonical keys from Welch values (preferred)
            r.setdefault("t_stat", r.get("t_welch") or r.get("t_equal"))
            r.setdefault("p", r.get("p_welch") or r.get("p_equal"))
            r.setdefault("df", r.get("df_welch") or r.get("df_equal"))
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/anova", methods=["POST"])
def stat_anova():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        if d.get("type") == "twoway":
            r = se.twoway_anova(df, d["depvar"], d["factor1"], d["factor2"],
                                interaction=d.get("interaction", True))
        else:
            r = se.oneway_anova(df, d["depvar"], d["groupvar"])
            r["output"] = _fmt_anova(r)
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/chi_square", methods=["POST"])
def stat_chi_square():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        if d.get("type") == "gof":
            r = se.chi_square_gof(df, d["variable"])
        else:
            r = se.chi_square(df, d["var1"], d["var2"])
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/fisher", methods=["POST"])
def stat_fisher():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        r = se.fisher_exact(df, d["var1"], d["var2"])
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/regression", methods=["POST"])
def stat_regression():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        rtype = d.get("type", "ols")
        if rtype == "logistic":
            r = se.logistic_regression(df, d["depvar"], d["indepvars"])
        elif rtype == "probit":
            r = se.probit_regression(df, d["depvar"], d["indepvars"])
        else:
            r = se.ols_regression(df, d["depvar"], d["indepvars"],
                                  robust=d.get("robust", False))
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/nonparametric", methods=["POST"])
def stat_nonparametric():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        test = d.get("test", "mann_whitney")
        if test == "mann_whitney":
            r = se.mann_whitney(df, d["variable"], d["groupvar"])
        elif test == "wilcoxon":
            r = se.wilcoxon_signed(df, d["var1"], d["var2"])
        elif test == "kruskal_wallis":
            r = se.kruskal_wallis(df, d["variable"], d["groupvar"])
        else:
            return _err(f"Unknown nonparametric test: {test}")
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/correlation", methods=["POST"])
def stat_correlation():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        r = se.correlation(df, d["variables"], method=d.get("method", "pearson"))
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/posthoc", methods=["POST"])
def stat_posthoc():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        if d.get("method") == "bonferroni":
            r = se.bonferroni(df, d["depvar"], d["groupvar"])
        else:
            r = se.tukey_hsd(df, d["depvar"], d["groupvar"])
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/repeated", methods=["POST"])
def stat_repeated():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        test_type = d.get("test") or d.get("type", "rm_anova")
        within = d.get("within_vars") or d.get("variables", [])
        subj = d.get("subject_var") or None
        if test_type == "friedman":
            r = se.friedman(df, subj, within)
        else:
            r = se.repeated_anova(df, subj, within)
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/survival", methods=["POST"])
def stat_survival():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        stype = d.get("test") or d.get("type", "kaplan_meier")
        if stype == "cox":
            r = se.cox_regression(df, d["time_var"], d["event_var"], d["covariates"])
        else:
            r = se.kaplan_meier(df, d["time_var"], d["event_var"], d.get("group_var"))
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/power", methods=["POST"])
def stat_power():
    d = request.json or {}
    try:
        raw = d.get("test") or d.get("test_type", "ttest")
        test = raw.lower().replace("-", "").replace("_", "").replace("square", "2")
        # Normalise: "t-test" -> "ttest", "chi-square" -> "chi2"
        params = {k: v for k, v in d.items()
                  if k not in ("test", "test_type") and v is not None}
        if "ttest" in test or test == "t":
            r = se.power_ttest(**params)
        elif "anova" in test:
            r = se.power_anova(**params)
        elif "chi" in test:
            r = se.power_chi2(**params)
        else:
            return _err(f"Unknown power test: {raw}")
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/sample_size", methods=["POST"])
def stat_sample_size():
    d = request.json or {}
    try:
        raw = d.get("type") or d.get("test_type", "means")
        if raw == "proportions" or raw == "proportion":
            r = se.sample_size_proportions(float(d["p1"]), float(d["p2"]),
                                            float(d.get("alpha", 0.05)),
                                            float(d.get("power", 0.80)))
        else:
            delta = float(d.get("delta") or d.get("effect_size", 0.5))
            sd = float(d.get("sd", 1.0))
            r = se.sample_size_means(delta, sd,
                                      float(d.get("alpha", 0.05)),
                                      float(d.get("power", 0.80)))
        return _ok(r)
    except Exception as e:
        return _err(str(e))


@app.route("/api/stats/smart", methods=["POST"])
def stat_smart():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        r = se.smart_analysis(df, d.get("columns", list(df.columns)),
                              subject_var=d.get("subject_var"))
        # Normalize keys for frontend
        if "test_name" in r and "selected_test" not in r:
            r["selected_test"] = r.pop("test_name")
        if "test_result" in r and "result" not in r:
            r["result"] = r.pop("test_result")
        if isinstance(r.get("reasoning"), list):
            r["reasoning"] = "; ".join(r["reasoning"])
        return _ok(r)
    except Exception as e:
        return _err(str(e))


# ---------------------------------------------------------------------------
# ROUTES — AI Agent endpoints
# ---------------------------------------------------------------------------

@app.route("/api/agent/models")
def agent_models():
    try:
        ac = _agent()
        return jsonify({"models": ac.get_available_models(),
                        "current": ac.get_model(),
                        "ollama_running": ac.is_ollama_available(),
                        "fallback_mode": not ac.is_ollama_available()})
    except Exception as e:
        return jsonify({"error": str(e), "models": ["llama3.2"],
                        "current": "llama3.2", "ollama_running": False,
                        "fallback_mode": True})


@app.route("/api/agent/models", methods=["POST"])
def agent_set_model():
    d = request.json or {}
    _agent().set_model(d.get("model", "llama3.2"))
    return jsonify({"success": True, "model": d.get("model", "llama3.2")})


@app.route("/api/agent/ollama_status")
def agent_ollama_status():
    ac = _agent()
    ac.reset_ollama_check()
    avail = ac.is_ollama_available()
    return jsonify({"available": avail, "fallback_mode": not avail,
                    "message": "Ollama is running" if avail else
                    "Ollama not available — Python fallbacks active. Statistics unaffected."})


@app.route("/api/agent/universal_analyze", methods=["POST"])
def agent_universal():
    d = request.json or {}
    raw = d.get("raw_text", "")
    ctx = d.get("proposal_context", "")
    hint = d.get("test_type") or None
    if not raw.strip():
        return _err("No data provided")
    try:
        r = _agent().run_universal_analysis(raw, ctx, hint)
        return jsonify({"result": _safe(r)})
    except Exception as e:
        traceback.print_exc()
        return _err(f"Pipeline error: {e}", 500)


@app.route("/api/agent/analyze", methods=["POST"])
def agent_analyze():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        r = _brain().analyze_data(df, d.get("proposal", ""),
                                   d.get("question", ""),
                                   d.get("do_research", True))
        return jsonify({"result": _safe(r)})
    except Exception as e:
        traceback.print_exc()
        return _err(f"AI analysis error: {e}", 500)


@app.route("/api/agent/smart_analyze", methods=["POST"])
def agent_smart():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        cols = d.get("columns") or list(df.columns)
        r = se.smart_analysis(df, cols, subject_var=d.get("subject_var"))
        return jsonify({"result": _safe(r)})
    except Exception as e:
        return _err(str(e))


@app.route("/api/agent/messy_data", methods=["POST"])
def agent_messy():
    df = _get_df()
    if df is None: return _err("No data loaded")
    d = request.json or {}
    try:
        r = _agent().agent_messy_data(df, d.get("description", ""))
        return jsonify({"result": _safe(r)})
    except Exception as e:
        return _err(str(e))


@app.route("/api/agent/sample_size_text", methods=["POST"])
def agent_sample_size_text():
    d = request.json or {}
    text = d.get("text", "")
    if not text.strip(): return _err("No text provided")
    try:
        r = _brain().calculate_sample_size_from_text(text,
                alpha=float(d.get("alpha", 0.05)),
                power=float(d.get("power", 0.80)))
        return jsonify({"result": _safe(r)})
    except Exception as e:
        return _err(str(e))


@app.route("/api/agent/literature", methods=["POST"])
def agent_literature():
    d = request.json or {}
    query = d.get("query", "")
    if not query.strip(): return _err("No query provided")
    try:
        r = _brain().search_literature(query, max_results=int(d.get("max", 5)))
        return jsonify({"result": _safe(r)})
    except Exception as e:
        return _err(str(e))


@app.route("/api/agent/proposal", methods=["POST"])
def agent_proposal():
    d = request.json or {}
    text = d.get("text", "")
    if not text.strip(): return _err("No proposal text")
    try:
        r = _brain().set_proposal_context(text)
        return jsonify({"result": _safe(r)})
    except Exception as e:
        return _err(str(e))


# ---------------------------------------------------------------------------
# ROUTES — Command-line interface
# ---------------------------------------------------------------------------

@app.route("/api/command", methods=["POST"])
def run_command():
    d = request.json or {}
    cmd = d.get("command", "").strip()
    if not cmd:
        return _err("No command")
    try:
        return jsonify({"result": _safe(_exec_command(cmd))})
    except Exception as e:
        return jsonify({"result": {"output": f"Error: {e}", "error": True}})


def _exec_command(cmd):
    """Parse and execute a Stata-style command string."""
    df = _get_df()
    parts = cmd.split()
    verb = parts[0].lower() if parts else ""

    if verb == "help":
        return {"output": _help_text()}

    if verb in ("tests", "list"):
        catalog = se.list_tests()
        lines = ["Available tests:", "-" * 50]
        for k, v in catalog.items():
            lines.append(f"  {k:<25} {v['desc']:<35} [{v['stata']}]")
        return {"output": "\n".join(lines)}

    if verb in ("describe", "desc", "summarize", "sum"):
        if df is None: return {"output": "No data loaded. Use Open to load a file."}
        variables = parts[1:] if len(parts) > 1 else None
        detail = "detail" in cmd.lower() or ",d" in cmd.lower()
        r = se.descriptive(df, variables, detail=detail)
        return {"output": r.to_string(index=False)}

    if verb in ("tabulate", "tab"):
        if df is None: return {"output": "No data loaded."}
        if len(parts) < 2: return {"output": "Usage: tab var1 [var2]"}
        v1 = parts[1]; v2 = parts[2] if len(parts) > 2 else None
        r = se.tabulate(df, v1, v2)
        return {"output": r.to_string()}

    if verb == "ttest":
        if df is None: return {"output": "No data loaded."}
        if "==" in cmd:
            idx = parts.index("==")
            v = parts[1]
            rhs = parts[idx + 1] if idx + 1 < len(parts) else "0"
            try:
                mu = float(rhs)
                r = se.ttest_one(df, v, mu=mu)
            except ValueError:
                r = se.ttest_paired(df, v, rhs)
            return {"output": json.dumps(_safe(r), indent=2)}
        if "by(" in cmd.lower():
            import re as _re
            m = _re.search(r"by\((\w+)\)", cmd, _re.IGNORECASE)
            gv = m.group(1) if m else parts[-1]
            v = parts[1].rstrip(",")
            r = se.ttest_two(df, v, gv)
            return {"output": json.dumps(_safe(r), indent=2)}
        return {"output": "Usage: ttest var == mu | ttest var, by(group) | ttest v1 == v2"}

    if verb == "oneway":
        if df is None: return {"output": "No data loaded."}
        if len(parts) < 3: return {"output": "Usage: oneway depvar groupvar"}
        r = se.oneway_anova(df, parts[1], parts[2])
        return {"output": _fmt_anova(r)}

    if verb in ("regress", "reg"):
        if df is None: return {"output": "No data loaded."}
        if len(parts) < 3: return {"output": "Usage: regress depvar indep1 [indep2 ...]"}
        r = se.ols_regression(df, parts[1], parts[2:])
        return {"output": r.get("summary", json.dumps(_safe(r), indent=2))}

    if verb in ("logit", "logistic"):
        if df is None: return {"output": "No data loaded."}
        if len(parts) < 3: return {"output": "Usage: logit depvar indep1 [indep2 ...]"}
        r = se.logistic_regression(df, parts[1], parts[2:])
        return {"output": r.get("summary", json.dumps(_safe(r), indent=2))}

    if verb in ("pwcorr", "corr", "correlate"):
        if df is None: return {"output": "No data loaded."}
        variables = parts[1:] if len(parts) > 1 else df.select_dtypes(include=[np.number]).columns.tolist()
        r = se.correlation(df, variables[:10])
        return {"output": r.get("correlation_str", "")}

    if verb in ("sktest", "swilk", "normality"):
        if df is None: return {"output": "No data loaded."}
        if len(parts) < 2: return {"output": "Usage: sktest variable"}
        r = se.normality(df, parts[1])
        return {"output": json.dumps(_safe(r), indent=2)}

    if verb == "ranksum":
        if df is None: return {"output": "No data loaded."}
        import re as _re
        m = _re.search(r"by\((\w+)\)", cmd, _re.IGNORECASE)
        if m and len(parts) >= 2:
            r = se.mann_whitney(df, parts[1].rstrip(","), m.group(1))
            return {"output": json.dumps(_safe(r), indent=2)}
        return {"output": "Usage: ranksum var, by(group)"}

    if verb == "kwallis":
        if df is None: return {"output": "No data loaded."}
        import re as _re
        m = _re.search(r"by\((\w+)\)", cmd, _re.IGNORECASE)
        if m and len(parts) >= 2:
            r = se.kruskal_wallis(df, parts[1].rstrip(","), m.group(1))
            return {"output": json.dumps(_safe(r), indent=2)}
        return {"output": "Usage: kwallis var, by(group)"}

    if verb == "use":
        return {"output": "Use the Open button to load data files."}

    if verb == "clear":
        _store["df"] = None; _store["filename"] = None
        _store["columns"] = []; _store["dtypes"] = {}
        return {"output": "Data cleared."}

    return {"output": f"Unrecognised command: {verb}. Type 'help' for a list of commands."}


def _help_text():
    return """SolarSTATA Command Reference
============================
  describe [vars]        Descriptive statistics
  summarize [vars]       Same as describe
  tab var1 [var2]        Frequency / cross-tabulation
  ttest var == mu        One-sample t-test
  ttest var, by(group)   Two-sample t-test
  ttest v1 == v2         Paired t-test
  oneway depvar group    One-way ANOVA
  regress y x1 x2 ...   Linear regression
  logit y x1 x2 ...     Logistic regression
  pwcorr [vars]          Correlation matrix
  sktest var             Normality test
  ranksum var, by(grp)   Mann-Whitney U
  kwallis var, by(grp)   Kruskal-Wallis H
  tests                  List all available tests
  clear                  Clear loaded data
  help                   Show this help"""


# ---------------------------------------------------------------------------
# ROUTES — health
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "2.0.0", "name": "SolarSTATA"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
