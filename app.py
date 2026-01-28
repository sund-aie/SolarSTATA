"""
SolarSTATA - AI-Powered Statistical Analysis Application
Flask web server providing a Stata 19-like interface with integrated AI.
"""

import os
import json
import traceback
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename

import stats_engine as se
import ai_brain

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# In-memory dataset storage (per-session simulation)
datasets = {}
command_history = []
results_log = []

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "dta", "tsv", "txt"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_df():
    """Get the currently loaded dataframe."""
    return datasets.get("current")


def set_current_df(df, name="current"):
    """Store a dataframe."""
    datasets[name] = df


def log_command(cmd, result_summary=""):
    """Log a command to history (Stata-style)."""
    command_history.append({"command": cmd, "result": result_summary})


def numpy_safe(obj):
    """Convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.DataFrame):
        return json.loads(obj.to_json(orient="records"))
    if isinstance(obj, pd.Series):
        return json.loads(obj.to_json())
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        result = numpy_safe(obj)
        if result is not obj:
            return result
        return super().default(obj)


app.json_encoder = NumpyEncoder


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Upload and parse a data file."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    try:
        ext = filename.rsplit(".", 1)[1].lower()
        if ext == "csv":
            df = pd.read_csv(filepath)
        elif ext == "tsv" or ext == "txt":
            df = pd.read_csv(filepath, sep="\t")
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(filepath, header=None)
            # Flatten: read without header so merged cells don't create MultiIndex
        elif ext == "dta":
            df = pd.read_stata(filepath)
        else:
            return jsonify({"error": "Unsupported format"}), 400

        # Smart clean
        try:
            df = ai_brain.smart_clean(df)
        except Exception:
            # Fallback: basic cleaning if smart_clean fails
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [str(c) for c in df.columns]
            df.columns = [str(c) for c in df.columns]

        # Ensure all column names are strings and unique
        cols = list(df.columns)
        seen = {}
        new_cols = []
        for c in cols:
            c = str(c)
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        df.columns = new_cols

        set_current_df(df, "current")
        set_current_df(df, filename)

        # Analyze structure
        try:
            data_info = ai_brain.analyze_data_structure(df)
        except Exception:
            data_info = {"n_observations": df.shape[0], "n_variables": df.shape[1]}

        log_command(f'use "{filename}"', f"({df.shape[0]} observations, {df.shape[1]} variables)")

        return jsonify({
            "success": True,
            "filename": filename,
            "shape": list(df.shape),
            "columns": df.columns.tolist(),
            "dtypes": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
            "preview": json.loads(df.head(20).to_json(orient="records")),
            "data_info": json.loads(json.dumps(data_info, default=numpy_safe)),
            "message": f"Successfully loaded {filename}: {df.shape[0]} observations, {df.shape[1]} variables",
        })
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 400
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/api/data/preview")
def data_preview():
    """Get current dataset preview."""
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded. Use File > Open to load data."}), 400

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    start = (page - 1) * per_page
    end = start + per_page

    return jsonify({
        "data": json.loads(df.iloc[start:end].to_json(orient="records")),
        "total_rows": len(df),
        "total_cols": len(df.columns),
        "columns": df.columns.tolist(),
        "page": page,
        "per_page": per_page,
        "total_pages": (len(df) + per_page - 1) // per_page,
    })


@app.route("/api/data/info")
def data_info():
    """Get detailed data information (Stata: describe)."""
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400

    info = ai_brain.analyze_data_structure(df)
    return jsonify(json.loads(json.dumps(info, default=numpy_safe)))


@app.route("/api/data/variables")
def data_variables():
    """List all variables and types."""
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    var_info = se.detect_variable_types(df)
    return jsonify(var_info.to_dict("records"))


# ---------------------------------------------------------------------------
# STATISTICAL TESTS API
# ---------------------------------------------------------------------------

@app.route("/api/stats/descriptive", methods=["POST"])
def run_descriptive():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json or {}
    variables = data.get("variables")
    detail = data.get("detail", True)
    result = se.descriptive_stats(df, variables, detail)
    log_command(f"summarize {' '.join(variables or df.select_dtypes(include=[np.number]).columns.tolist())}")
    return jsonify({"result": result.to_dict("records"), "result_str": result.to_string()})


@app.route("/api/stats/tabulate", methods=["POST"])
def run_tabulate():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    var1 = data.get("var1")
    var2 = data.get("var2")
    result = se.tabulate(df, var1, var2)
    log_command(f"tabulate {var1}" + (f" {var2}" if var2 else ""))
    return jsonify({"result": result.to_dict(), "result_str": result.to_string()})


@app.route("/api/stats/normality", methods=["POST"])
def run_normality():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    variable = data.get("variable")
    result = se.normality_test(df, variable)
    log_command(f"sktest {variable}")
    return jsonify({"result": result})


@app.route("/api/stats/ttest", methods=["POST"])
def run_ttest():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    test_type = data.get("type", "two_sample")

    if test_type == "one_sample":
        result = se.ttest_one_sample(df, data["variable"], data.get("mu", 0))
        log_command(f"ttest {data['variable']} == {data.get('mu', 0)}")
    elif test_type == "paired":
        result = se.ttest_paired(df, data["var1"], data["var2"])
        log_command(f"ttest {data['var1']} == {data['var2']}")
    else:
        equal_var = data.get("equal_var", True)
        result = se.ttest_two_sample(df, data["variable"], data["groupvar"], equal_var)
        log_command(f"ttest {data['variable']}, by({data['groupvar']})")

    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/anova", methods=["POST"])
def run_anova():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    anova_type = data.get("type", "oneway")

    if anova_type == "twoway":
        result = se.twoway_anova(df, data["depvar"], data["factor1"], data["factor2"],
                                 data.get("interaction", True))
        log_command(f"anova {data['depvar']} {data['factor1']} {data['factor2']}")
    else:
        result = se.oneway_anova(df, data["depvar"], data["groupvar"])
        log_command(f"oneway {data['depvar']} {data['groupvar']}")

    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/chi_square", methods=["POST"])
def run_chi_square():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    result = se.chi_square_test(df, data["var1"], data["var2"])
    log_command(f"tabulate {data['var1']} {data['var2']}, chi2")
    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/regression", methods=["POST"])
def run_regression():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    reg_type = data.get("type", "ols")

    if reg_type == "logistic":
        result = se.logistic_regression(df, data["depvar"], data["indepvars"])
        log_command(f"logit {data['depvar']} {' '.join(data['indepvars'])}")
    elif reg_type == "probit":
        result = se.probit_regression(df, data["depvar"], data["indepvars"])
        log_command(f"probit {data['depvar']} {' '.join(data['indepvars'])}")
    else:
        robust = data.get("robust", False)
        result = se.linear_regression(df, data["depvar"], data["indepvars"], robust)
        cmd = f"regress {data['depvar']} {' '.join(data['indepvars'])}"
        if robust:
            cmd += ", vce(robust)"
        log_command(cmd)

    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/nonparametric", methods=["POST"])
def run_nonparametric():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    test_type = data.get("test", "mann_whitney")

    if test_type == "mann_whitney":
        result = se.mann_whitney_u(df, data["variable"], data["groupvar"])
        log_command(f"ranksum {data['variable']}, by({data['groupvar']})")
    elif test_type == "wilcoxon":
        result = se.wilcoxon_signed_rank(df, data["var1"], data["var2"])
        log_command(f"signrank {data['var1']} = {data['var2']}")
    elif test_type == "kruskal_wallis":
        result = se.kruskal_wallis(df, data["variable"], data["groupvar"])
        log_command(f"kwallis {data['variable']}, by({data['groupvar']})")
    else:
        return jsonify({"error": f"Unknown test: {test_type}"}), 400

    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/correlation", methods=["POST"])
def run_correlation():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    method = data.get("method", "pearson")
    variables = data.get("variables")
    if not variables:
        variables = df.select_dtypes(include=[np.number]).columns.tolist()
    result = se.correlation_matrix(df, variables, method)
    log_command(f"{'pwcorr' if method == 'pearson' else 'spearman'} {' '.join(variables)}")
    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/survival", methods=["POST"])
def run_survival():
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400
    data = request.json
    analysis_type = data.get("type", "kaplan_meier")

    if analysis_type == "cox":
        result = se.cox_regression(df, data["time_var"], data["event_var"], data["covariates"])
        log_command(f"stcox {' '.join(data['covariates'])}")
    else:
        result = se.kaplan_meier(df, data["time_var"], data["event_var"],
                                 data.get("group_var"))
        log_command(f"sts test {data.get('group_var', '')}")

    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/power", methods=["POST"])
def run_power():
    df = get_current_df()
    data = request.json
    test_type = data.get("test_type", "ttest")

    if test_type == "ttest":
        result = se.power_ttest(**{k: v for k, v in data.items() if k != "test_type" and v is not None})
    elif test_type == "anova":
        result = se.power_anova(**{k: v for k, v in data.items() if k != "test_type" and v is not None})
    elif test_type == "chi2":
        result = se.power_chi2(**{k: v for k, v in data.items() if k != "test_type" and v is not None})
    else:
        return jsonify({"error": f"Unknown power test: {test_type}"}), 400

    log_command(f"power {test_type}")
    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


@app.route("/api/stats/sample_size", methods=["POST"])
def run_sample_size():
    data = request.json
    result = ai_brain.calculate_sample_size(data)
    log_command("power (sample size calculation)")
    return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})


# ---------------------------------------------------------------------------
# AI ANALYSIS API
# ---------------------------------------------------------------------------

@app.route("/api/ai/analyze", methods=["POST"])
def ai_analyze():
    """Full AI-powered analysis."""
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded. Please upload data first."}), 400

    data = request.json or {}
    proposal = data.get("proposal", "")
    question = data.get("question", "")
    do_research = data.get("research", True)

    try:
        result = ai_brain.analyze_data(df, proposal, question, do_research)
        log_command(f"ai analyze" + (f' "{question[:50]}"' if question else ""))
        return jsonify({
            "result": json.loads(json.dumps(result, default=numpy_safe)),
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/api/ai/suggest", methods=["POST"])
def ai_suggest():
    """Get AI test suggestions without running analysis."""
    df = get_current_df()
    if df is None:
        return jsonify({"error": "No dataset loaded"}), 400

    data = request.json or {}
    proposal = data.get("proposal", "")

    data_info = ai_brain.analyze_data_structure(df)
    suggestions = ai_brain.suggest_tests(data_info, proposal)

    return jsonify({
        "suggestions": suggestions,
        "data_info": json.loads(json.dumps(data_info, default=numpy_safe)),
    })


@app.route("/api/ai/research", methods=["POST"])
def ai_research():
    """Search academic literature."""
    data = request.json or {}
    query = data.get("query", "")
    if not query:
        return jsonify({"error": "No search query provided"}), 400

    results = ai_brain.search_literature(query)
    return jsonify({"results": results, "query": query})


# ---------------------------------------------------------------------------
# COMMAND LINE INTERFACE (Stata-style command execution)
# ---------------------------------------------------------------------------

@app.route("/api/command", methods=["POST"])
def execute_command():
    """Execute a Stata-style command string."""
    df = get_current_df()
    data = request.json or {}
    cmd = data.get("command", "").strip()

    if not cmd:
        return jsonify({"error": "No command provided"}), 400

    log_command(cmd)

    try:
        result = parse_and_execute(cmd, df)
        return jsonify({"result": json.loads(json.dumps(result, default=numpy_safe))})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def parse_and_execute(cmd, df):
    """Parse a Stata-style command and execute it."""
    parts = cmd.strip().split()
    if not parts:
        return {"error": "Empty command"}

    command = parts[0].lower()

    # --- DESCRIBE ---
    if command in ("describe", "desc", "d"):
        if df is None:
            return {"output": "No dataset in memory"}
        info = se.detect_variable_types(df)
        output = f"Contains {len(df)} observations and {len(df.columns)} variables\n\n"
        output += info.to_string(index=False)
        return {"output": output}

    # --- SUMMARIZE ---
    if command in ("summarize", "sum", "su"):
        if df is None:
            return {"output": "No dataset in memory"}
        variables = parts[1:] if len(parts) > 1 else None
        # Check for detail option
        detail = False
        if variables and "detail" in [v.lower().strip(",") for v in variables]:
            detail = True
            variables = [v for v in variables if v.lower().strip(",") != "detail"]
            if not variables:
                variables = None
        result = se.descriptive_stats(df, variables, detail)
        return {"output": result.to_string(index=False)}

    # --- TABULATE ---
    if command in ("tabulate", "tab"):
        if df is None:
            return {"output": "No dataset in memory"}
        if len(parts) < 2:
            return {"error": "Syntax: tabulate var1 [var2] [, chi2]"}
        chi2 = "chi2" in cmd.lower()
        var1 = parts[1]
        var2 = parts[2] if len(parts) > 2 and not parts[2].startswith(",") else None
        result = se.tabulate(df, var1, var2)
        output = result.to_string()
        if chi2 and var2:
            chi_res = se.chi_square_test(df, var1, var2)
            output += f"\n\nPearson chi2({chi_res['df']}) = {chi_res['chi2']:.4f}   Pr = {chi_res['Pr']:.4f}"
            output += f"\nCramer's V = {chi_res['cramers_v']:.4f}"
        return {"output": output}

    # --- TTEST ---
    if command == "ttest":
        if df is None:
            return {"output": "No dataset in memory"}
        # Parse: ttest var, by(group) or ttest var == value or ttest var1 == var2
        cmd_body = " ".join(parts[1:])
        if "by(" in cmd_body:
            var = cmd_body.split(",")[0].strip()
            group = cmd_body.split("by(")[1].split(")")[0].strip()
            result = se.ttest_two_sample(df, var, group)
        elif "==" in cmd_body:
            left, right = cmd_body.split("==")
            left = left.strip()
            right = right.strip()
            try:
                mu = float(right)
                result = se.ttest_one_sample(df, left, mu)
            except ValueError:
                result = se.ttest_paired(df, left, right)
        else:
            return {"error": "Syntax: ttest var, by(group) | ttest var == # | ttest var1 == var2"}
        return {"output": json.dumps(result, indent=2, default=str)}

    # --- ONEWAY ---
    if command == "oneway":
        if df is None or len(parts) < 3:
            return {"error": "Syntax: oneway depvar groupvar"}
        result = se.oneway_anova(df, parts[1], parts[2])
        output = f"One-way ANOVA: {parts[1]} by {parts[2]}\n"
        output += f"\nF({result['anova_table']['df'][0]}, {result['anova_table']['df'][1]}) = {result['F']}"
        output += f"\nProb > F = {result['Prob > F']}\n"
        for gs in result["group_stats"]:
            output += f"\n  {gs['Group']}: Mean={gs['Mean']}, SD={gs['Std. Dev.']}, N={gs['N']}"
        output += f"\n\nBartlett's chi2 = {result['bartlett']['chi2']}, p = {result['bartlett']['p']}"
        return {"output": output}

    # --- ANOVA ---
    if command == "anova":
        if df is None or len(parts) < 4:
            return {"error": "Syntax: anova depvar factor1 factor2"}
        result = se.twoway_anova(df, parts[1], parts[2], parts[3])
        return {"output": result.get("anova_table_str", str(result))}

    # --- REGRESS ---
    if command in ("regress", "reg"):
        if df is None or len(parts) < 3:
            return {"error": "Syntax: regress depvar indep1 [indep2 ...]"}
        robust = "robust" in cmd.lower() or "vce(robust)" in cmd.lower()
        indeps = [p for p in parts[2:] if p.lower() not in (",", "robust", "vce(robust)")]
        result = se.linear_regression(df, parts[1], indeps, robust)
        return {"output": result.get("summary", str(result))}

    # --- LOGIT ---
    if command in ("logit", "logistic"):
        if df is None or len(parts) < 3:
            return {"error": "Syntax: logit depvar indep1 [indep2 ...]"}
        result = se.logistic_regression(df, parts[1], parts[2:])
        return {"output": result.get("summary", str(result))}

    # --- PROBIT ---
    if command == "probit":
        if df is None or len(parts) < 3:
            return {"error": "Syntax: probit depvar indep1 [indep2 ...]"}
        result = se.probit_regression(df, parts[1], parts[2:])
        return {"output": result.get("summary", str(result))}

    # --- CORRELATE ---
    if command in ("correlate", "corr", "pwcorr"):
        if df is None:
            return {"output": "No dataset in memory"}
        variables = parts[1:] if len(parts) > 1 else df.select_dtypes(include=[np.number]).columns.tolist()
        result = se.correlation_matrix(df, variables)
        return {"output": result["correlation_str"]}

    # --- SPEARMAN ---
    if command == "spearman":
        if df is None:
            return {"output": "No dataset in memory"}
        variables = parts[1:] if len(parts) > 1 else df.select_dtypes(include=[np.number]).columns.tolist()
        result = se.correlation_matrix(df, variables, method="spearman")
        return {"output": result["correlation_str"]}

    # --- RANKSUM ---
    if command == "ranksum":
        if df is None:
            return {"error": "No dataset in memory"}
        cmd_body = " ".join(parts[1:])
        var = cmd_body.split(",")[0].strip()
        group = cmd_body.split("by(")[1].split(")")[0].strip() if "by(" in cmd_body else parts[2]
        result = se.mann_whitney_u(df, var, group)
        return {"output": json.dumps(result, indent=2, default=str)}

    # --- KWALLIS ---
    if command == "kwallis":
        if df is None:
            return {"error": "No dataset in memory"}
        cmd_body = " ".join(parts[1:])
        var = cmd_body.split(",")[0].strip()
        group = cmd_body.split("by(")[1].split(")")[0].strip() if "by(" in cmd_body else parts[2]
        result = se.kruskal_wallis(df, var, group)
        return {"output": json.dumps(result, indent=2, default=str)}

    # --- SIGNRANK ---
    if command == "signrank":
        if df is None:
            return {"error": "No dataset in memory"}
        cmd_body = " ".join(parts[1:])
        var1, var2 = [v.strip() for v in cmd_body.split("=")]
        result = se.wilcoxon_signed_rank(df, var1, var2)
        return {"output": json.dumps(result, indent=2, default=str)}

    # --- SKTEST ---
    if command == "sktest":
        if df is None or len(parts) < 2:
            return {"error": "Syntax: sktest variable"}
        result = se.normality_test(df, parts[1])
        return {"output": json.dumps(result, indent=2, default=str)}

    # --- POWER ---
    if command == "power":
        return {"output": "Use the Power Analysis panel in the GUI or /api/stats/power endpoint"}

    # --- LIST ---
    if command in ("list", "li", "l"):
        if df is None:
            return {"output": "No dataset in memory"}
        n = min(20, len(df))
        return {"output": df.head(n).to_string()}

    # --- COUNT ---
    if command == "count":
        if df is None:
            return {"output": "No dataset in memory"}
        return {"output": f"  {len(df)}"}

    # --- CLEAR ---
    if command == "clear":
        datasets.clear()
        return {"output": "Dataset cleared from memory"}

    # --- HELP ---
    if command == "help":
        tests = se.list_available_tests()
        output = "SolarSTATA Available Commands:\n"
        output += "=" * 50 + "\n"
        for key, val in tests.items():
            output += f"  {val['stata_cmd']:30s} | {val['description']}\n"
        output += "\nData Commands: describe, list, count, clear\n"
        output += "AI Commands: ai analyze, ai suggest, ai research\n"
        return {"output": output}

    # --- AI COMMANDS ---
    if command == "ai":
        if len(parts) < 2:
            return {"error": "Syntax: ai analyze/suggest/research [query]"}
        sub = parts[1].lower()
        query = " ".join(parts[2:]) if len(parts) > 2 else ""

        if sub == "analyze":
            if df is None:
                return {"error": "No dataset loaded"}
            result = ai_brain.analyze_data(df, proposal_text=query, user_question=query)
            return {"output": result.get("stdout", ""), "code": result.get("generated_code", "")}
        elif sub == "suggest":
            if df is None:
                return {"error": "No dataset loaded"}
            data_info = ai_brain.analyze_data_structure(df)
            suggestions = ai_brain.suggest_tests(data_info, query)
            output = "Suggested Statistical Tests:\n"
            for s in suggestions:
                output += f"  [{s['priority']}] {s['test']}: {s['reason']}\n"
            return {"output": output}
        elif sub == "research":
            results = ai_brain.search_literature(query)
            output = f"Literature Search: '{query}'\n"
            for r in results:
                if "error" not in r:
                    output += f"\n  [{r.get('source')}] {r.get('title', 'N/A')}"
                    output += f"\n    {r.get('authors', 'N/A')} ({r.get('year', 'N/A')})"
                    output += f"\n    {r.get('journal', 'N/A')}\n"
            return {"output": output}

    return {"error": f"Unrecognized command: {command}. Type 'help' for available commands."}


# ---------------------------------------------------------------------------
# UTILITY ROUTES
# ---------------------------------------------------------------------------

@app.route("/api/history")
def get_history():
    return jsonify({"history": command_history[-100:]})


@app.route("/api/tests")
def list_tests():
    return jsonify(se.list_available_tests())


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0", "name": "SolarSTATA"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
