/**
 * SolarSTATA v2.0 - Main Application JavaScript
 * Stata 19-inspired statistical analysis interface with AI integration.
 *
 * Matches HTML (templates/index.html) and CSS (static/css/stata.css).
 */

/* ==================================================================
   1. STATE
   ================================================================== */
const S = {
    loaded:       false,
    columns:      [],
    dtypes:       {},
    dataInfo:     null,
    selectedVars: [],
    cmdHistory:   [],
    histIdx:      -1,
    curTab:       "output",
    curTest:      null,         // which stat test modal is being configured
};

/* ==================================================================
   2. BOOTSTRAP
   ================================================================== */
document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initRightTabs();
    initCommandInput();
    initToolbar();
    initTestButtons();
    initAgentButtons();
    initModals();
    initVariableSearch();
    initKeyboard();
    loadModels();
    toast("SolarSTATA ready. Load data to begin.", "success");
});

/* ==================================================================
   3. TAB SYSTEM (center area)
   ================================================================== */
function initTabs() {
    document.querySelectorAll("#tab-bar .tab").forEach(t => {
        t.addEventListener("click", () => switchTab(t.dataset.tab));
    });
}

function switchTab(id) {
    document.querySelectorAll("#tab-bar .tab").forEach(t => t.classList.toggle("active", t.dataset.tab === id));
    document.querySelectorAll("#center-area > .tab-content").forEach(c => c.classList.toggle("active", c.id === `tab-${id}`));
    S.curTab = id;
}

/* ==================================================================
   4. RIGHT PANEL TABS (Tests / AI Agent)
   ================================================================== */
function initRightTabs() {
    document.querySelectorAll("#right-tabs .right-tab").forEach(t => {
        t.addEventListener("click", () => {
            document.querySelectorAll("#right-tabs .right-tab").forEach(x => x.classList.remove("active"));
            document.querySelectorAll("#right-panel .right-content").forEach(x => x.classList.remove("active"));
            t.classList.add("active");
            const panel = document.getElementById(t.dataset.panel);
            if (panel) panel.classList.add("active");
        });
    });
}

/* ==================================================================
   5. TOOLBAR
   ================================================================== */
function initToolbar() {
    const btnOpen = document.getElementById("btn-open");
    const fileInput = document.getElementById("file-input");
    const btnSave = document.getElementById("btn-save-log");
    const btnHelp = document.getElementById("btn-help");
    const banner = document.getElementById("dismiss-banner");

    if (btnOpen) btnOpen.addEventListener("click", () => fileInput.click());
    if (fileInput) fileInput.addEventListener("change", handleFileUpload);
    if (btnSave) btnSave.addEventListener("click", saveLog);
    if (btnHelp) btnHelp.addEventListener("click", showHelp);
    if (banner) banner.addEventListener("click", () => {
        document.getElementById("fallback-banner").style.display = "none";
    });
}

async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setStatus("loading", `Loading ${file.name}...`);
    toast(`Uploading ${file.name}...`);
    try {
        const r = await fetch("/api/upload", { method: "POST", body: fd });
        const d = await r.json();
        if (d.error) { toast(d.error, "error"); setStatus("error", d.error); return; }
        S.loaded = true;
        S.columns = d.columns || [];
        S.dtypes = d.dtypes || {};
        S.dataInfo = d.data_info || null;
        updateVarList();
        renderDataTable(d.preview, d.columns);
        switchTab("data");
        setStatus("ok", `${d.filename}: ${d.shape[0]} obs, ${d.shape[1]} vars`);
        document.getElementById("status-data").textContent = `${d.shape[0]} obs, ${d.shape[1]} vars`;
        appendOutput("use", `use "${d.filename}"`, d.message || "Data loaded.");
        toast(d.message || "Data loaded.", "success");
    } catch (err) {
        toast(`Upload failed: ${err.message}`, "error");
        setStatus("error", "Upload failed");
    }
    e.target.value = "";
}

function saveLog() {
    const area = document.getElementById("output-area");
    if (!area) return;
    const text = area.innerText;
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "solarstata_output.log";
    a.click();
    toast("Output saved", "success");
}

function showHelp() {
    const help = [
        "SolarSTATA v2.0 - Quick Reference",
        "=".repeat(40),
        "",
        "Keyboard Shortcuts:",
        "  Ctrl+O     Open file",
        "  Ctrl+L     Focus command bar",
        "  Ctrl+1/2/3 Switch tabs",
        "",
        "Commands (type in command bar):",
        "  summarize [vars]",
        "  ttest var, by(group)",
        "  oneway dep group",
        "  tabulate var1 var2",
        "  regress dep indep1 indep2",
        "  help",
        "",
        "Right panel: click Tests or AI Agent tab.",
        "Select variables in left panel, then click Smart Analysis.",
    ];
    appendOutput("info", "help", help.join("\n"));
    switchTab("output");
}

/* ==================================================================
   6. VARIABLES PANEL
   ================================================================== */
function updateVarList() {
    const list = document.getElementById("variables-list");
    const count = document.getElementById("var-count");
    if (!list) return;
    const vars = S.dataInfo?.variable_info || [];
    if (count) count.textContent = vars.length;
    S.selectedVars = [];
    list.innerHTML = vars.map(v => {
        const tc = v.Type === "continuous" ? "numeric" : "categorical";
        const badge = v.Type === "continuous" ? "num" : "str";
        return `<div class="var-item" data-var="${esc(v.Variable)}">
            <span class="var-type-icon ${tc}">${badge}</span>
            <span class="var-name">${esc(v.Variable)}</span>
        </div>`;
    }).join("");
    list.querySelectorAll(".var-item").forEach(el => {
        el.addEventListener("click", () => toggleVar(el));
    });
}

function toggleVar(el) {
    const v = el.dataset.var;
    const i = S.selectedVars.indexOf(v);
    if (i >= 0) { S.selectedVars.splice(i, 1); el.classList.remove("selected"); }
    else { S.selectedVars.push(v); el.classList.add("selected"); }
}

function initVariableSearch() {
    const input = document.getElementById("var-search-input");
    if (!input) return;
    input.addEventListener("input", () => {
        const q = input.value.toLowerCase();
        document.querySelectorAll("#variables-list .var-item").forEach(el => {
            el.style.display = el.dataset.var.toLowerCase().includes(q) ? "" : "none";
        });
    });
}

/* ==================================================================
   7. DATA TABLE
   ================================================================== */
function renderDataTable(rows, cols) {
    const viewer = document.getElementById("data-viewer");
    if (!viewer) return;
    if (!rows || rows.length === 0) {
        viewer.innerHTML = '<div class="empty-state"><div class="empty-state-icon">[ ]</div><div class="empty-state-title">No Data</div></div>';
        return;
    }
    let h = '<table class="data-table"><thead><tr><th class="row-num">#</th>';
    cols.forEach(c => h += `<th>${esc(c)}</th>`);
    h += "</tr></thead><tbody>";
    rows.forEach((row, i) => {
        h += `<tr><td class="row-num">${i + 1}</td>`;
        cols.forEach(c => {
            const v = row[c];
            h += `<td>${v === null || v === undefined ? "." : esc(String(v))}</td>`;
        });
        h += "</tr>";
    });
    h += "</tbody></table>";
    viewer.innerHTML = h;
}

/* ==================================================================
   8. COMMAND INPUT (Stata-style CLI)
   ================================================================== */
function initCommandInput() {
    const input = document.getElementById("command-input");
    if (!input) return;
    input.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); runCommand(input.value); input.value = ""; }
        else if (e.key === "ArrowUp") { e.preventDefault(); navHistory(-1, input); }
        else if (e.key === "ArrowDown") { e.preventDefault(); navHistory(1, input); }
    });
}

function navHistory(dir, input) {
    if (!S.cmdHistory.length) return;
    S.histIdx += dir;
    if (S.histIdx < 0) S.histIdx = 0;
    if (S.histIdx >= S.cmdHistory.length) { S.histIdx = S.cmdHistory.length; input.value = ""; return; }
    input.value = S.cmdHistory[S.histIdx];
}

async function runCommand(cmd) {
    cmd = cmd.trim();
    if (!cmd) return;
    S.cmdHistory.push(cmd);
    S.histIdx = S.cmdHistory.length;
    appendOutput("command", cmd, "Running...");
    switchTab("output");
    try {
        const r = await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: cmd }),
        });
        const d = await r.json();
        if (d.error) updateLastOutput(d.error, "error");
        else updateLastOutput(d.result?.output || formatObj(d.result));
    } catch (err) {
        updateLastOutput(`Error: ${err.message}`, "error");
    }
}

/* ==================================================================
   9. OUTPUT AREA
   ================================================================== */
function appendOutput(type, cmd, text) {
    const area = document.getElementById("output-area");
    if (!area) return;
    const block = document.createElement("div");
    block.className = "output-block";
    if (type === "command" || type === "use") {
        block.innerHTML = `<div class="output-command">${esc(cmd)}</div><div class="output-result">${esc(text || "")}</div>`;
    } else {
        block.innerHTML = `<div class="output-result">${esc(text || "")}</div>`;
    }
    area.appendChild(block);
    area.scrollTop = area.scrollHeight;
}

function updateLastOutput(text, cls) {
    const area = document.getElementById("output-area");
    if (!area) return;
    const blocks = area.querySelectorAll(".output-block");
    if (blocks.length === 0) return;
    const last = blocks[blocks.length - 1].querySelector(".output-result");
    if (!last) return;
    last.className = cls === "error" ? "output-error" : "output-result";
    last.textContent = text;
    area.scrollTop = area.scrollHeight;
}

function clearOutput() {
    const area = document.getElementById("output-area");
    if (area) area.innerHTML = "";
}

/* ==================================================================
   10. STAT TEST BUTTONS → GENERIC MODAL
   ================================================================== */

// Maps data-test attribute → { title, buildForm, run }
const TEST_CONFIG = {
    descriptive: {
        title: "Descriptive Statistics",
        build: () => formMultiVar("desc-vars", "numeric") + formCheck("desc-detail", "Detailed output", true),
        run: () => apiRun("/api/stats/descriptive", {
            variables: multiVal("desc-vars"), detail: isChecked("desc-detail")
        }, "summarize"),
    },
    tabulate: {
        title: "Tabulate",
        build: () => formVar("tab-var1", "Variable 1", "any") + formVar("tab-var2", "Variable 2 (optional)", "any"),
        run: () => apiRun("/api/stats/tabulate", {
            var1: val("tab-var1"), var2: val("tab-var2")
        }, "tabulate"),
    },
    normality: {
        title: "Normality Test",
        build: () => formVar("norm-var", "Variable", "numeric"),
        run: () => apiRun("/api/stats/normality", { variable: val("norm-var") }, "swilk"),
    },
    ttest_one: {
        title: "One-Sample T-Test",
        build: () => formVar("t1-var", "Variable", "numeric") + formNum("t1-mu", "Test value (mu)", 0),
        run: () => apiRun("/api/stats/ttest", {
            type: "one_sample", variable: val("t1-var"), mu: numVal("t1-mu")
        }, "ttest"),
    },
    ttest_two: {
        title: "Two-Sample T-Test",
        build: () => formVar("t2-var", "Variable", "numeric") + formVar("t2-group", "Group variable", "categorical"),
        run: () => apiRun("/api/stats/ttest", {
            type: "two_sample", variable: val("t2-var"), groupvar: val("t2-group")
        }, "ttest"),
    },
    ttest_paired: {
        title: "Paired T-Test",
        build: () => formVar("tp-var1", "Variable 1", "numeric") + formVar("tp-var2", "Variable 2", "numeric"),
        run: () => apiRun("/api/stats/ttest", {
            type: "paired", var1: val("tp-var1"), var2: val("tp-var2")
        }, "ttest"),
    },
    anova_oneway: {
        title: "One-Way ANOVA",
        build: () => formVar("a1-dep", "Dependent variable", "numeric") + formVar("a1-group", "Group variable", "categorical"),
        run: () => apiRun("/api/stats/anova", {
            type: "oneway", depvar: val("a1-dep"), groupvar: val("a1-group")
        }, "oneway"),
    },
    anova_twoway: {
        title: "Two-Way ANOVA",
        build: () => formVar("a2-dep", "Dependent variable", "numeric") +
            formVar("a2-f1", "Factor 1", "categorical") +
            formVar("a2-f2", "Factor 2", "categorical") +
            formCheck("a2-int", "Include interaction", true),
        run: () => apiRun("/api/stats/anova", {
            type: "twoway", depvar: val("a2-dep"), factor1: val("a2-f1"),
            factor2: val("a2-f2"), interaction: isChecked("a2-int")
        }, "anova"),
    },
    chi_square: {
        title: "Chi-Square Test",
        build: () => formVar("chi-v1", "Variable 1", "categorical") + formVar("chi-v2", "Variable 2", "categorical"),
        run: () => apiRun("/api/stats/chi_square", {
            var1: val("chi-v1"), var2: val("chi-v2")
        }, "tabulate, chi2"),
    },
    fisher: {
        title: "Fisher's Exact Test",
        build: () => formVar("fish-v1", "Variable 1", "categorical") + formVar("fish-v2", "Variable 2", "categorical"),
        run: () => apiRun("/api/stats/fisher", {
            var1: val("fish-v1"), var2: val("fish-v2")
        }, "tabulate, exact"),
    },
    regression: {
        title: "OLS Regression",
        build: () => formVar("reg-dep", "Dependent variable", "numeric") +
            formMultiVar("reg-ind", "numeric") + formCheck("reg-robust", "Robust SE", false),
        run: () => apiRun("/api/stats/regression", {
            type: "ols", depvar: val("reg-dep"), indepvars: multiVal("reg-ind"), robust: isChecked("reg-robust")
        }, "regress"),
    },
    logistic: {
        title: "Logistic Regression",
        build: () => formVar("logit-dep", "Dependent (binary)", "categorical") + formMultiVar("logit-ind", "numeric"),
        run: () => apiRun("/api/stats/regression", {
            type: "logistic", depvar: val("logit-dep"), indepvars: multiVal("logit-ind")
        }, "logistic"),
    },
    probit: {
        title: "Probit Regression",
        build: () => formVar("probit-dep", "Dependent (binary)", "categorical") + formMultiVar("probit-ind", "numeric"),
        run: () => apiRun("/api/stats/regression", {
            type: "probit", depvar: val("probit-dep"), indepvars: multiVal("probit-ind")
        }, "probit"),
    },
    mann_whitney: {
        title: "Mann-Whitney U Test",
        build: () => formVar("mw-var", "Variable", "numeric") + formVar("mw-group", "Group variable", "categorical"),
        run: () => apiRun("/api/stats/nonparametric", {
            test: "mann_whitney", variable: val("mw-var"), groupvar: val("mw-group")
        }, "ranksum"),
    },
    wilcoxon: {
        title: "Wilcoxon Signed-Rank Test",
        build: () => formVar("wil-v1", "Variable 1", "numeric") + formVar("wil-v2", "Variable 2", "numeric"),
        run: () => apiRun("/api/stats/nonparametric", {
            test: "wilcoxon", var1: val("wil-v1"), var2: val("wil-v2")
        }, "signrank"),
    },
    kruskal_wallis: {
        title: "Kruskal-Wallis Test",
        build: () => formVar("kw-var", "Variable", "numeric") + formVar("kw-group", "Group variable", "categorical"),
        run: () => apiRun("/api/stats/nonparametric", {
            test: "kruskal_wallis", variable: val("kw-var"), groupvar: val("kw-group")
        }, "kwallis"),
    },
    correlation: {
        title: "Correlation",
        build: () => formMultiVar("corr-vars", "numeric") +
            `<div class="form-group"><label>Method</label><select class="form-control" id="corr-method">
                <option value="pearson">Pearson</option><option value="spearman">Spearman</option>
                <option value="kendall">Kendall</option></select></div>`,
        run: () => apiRun("/api/stats/correlation", {
            variables: multiVal("corr-vars"), method: val("corr-method")
        }, "correlate"),
    },
    tukey: {
        title: "Tukey HSD Post-Hoc",
        build: () => formVar("tukey-dep", "Dependent variable", "numeric") + formVar("tukey-group", "Group variable", "categorical"),
        run: () => apiRun("/api/stats/posthoc", {
            method: "tukey", depvar: val("tukey-dep"), groupvar: val("tukey-group")
        }, "tukey"),
    },
    bonferroni: {
        title: "Bonferroni Post-Hoc",
        build: () => formVar("bon-dep", "Dependent variable", "numeric") + formVar("bon-group", "Group variable", "categorical"),
        run: () => apiRun("/api/stats/posthoc", {
            method: "bonferroni", depvar: val("bon-dep"), groupvar: val("bon-group")
        }, "bonferroni"),
    },
    rm_anova: {
        title: "Repeated Measures ANOVA",
        build: () => formMultiVar("rm-vars", "numeric") +
            formVar("rm-subj", "Subject variable (optional)", "any"),
        run: () => apiRun("/api/stats/repeated", {
            type: "rm_anova", variables: multiVal("rm-vars"), subject_var: val("rm-subj") || null
        }, "rm anova"),
    },
    friedman: {
        title: "Friedman Test",
        build: () => formMultiVar("fried-vars", "numeric") +
            formVar("fried-subj", "Subject variable (optional)", "any"),
        run: () => apiRun("/api/stats/repeated", {
            type: "friedman", variables: multiVal("fried-vars"), subject_var: val("fried-subj") || null
        }, "friedman"),
    },
    kaplan_meier: {
        title: "Kaplan-Meier Survival",
        build: () => formVar("km-time", "Time variable", "numeric") +
            formVar("km-event", "Event variable", "any") +
            formVar("km-group", "Group variable (optional)", "categorical"),
        run: () => apiRun("/api/stats/survival", {
            type: "kaplan_meier", time_var: val("km-time"),
            event_var: val("km-event"), group_var: val("km-group") || null
        }, "sts graph"),
    },
    cox: {
        title: "Cox Proportional Hazards",
        build: () => formVar("cox-time", "Time variable", "numeric") +
            formVar("cox-event", "Event variable", "any") +
            formMultiVar("cox-cov", "numeric"),
        run: () => apiRun("/api/stats/survival", {
            type: "cox", time_var: val("cox-time"),
            event_var: val("cox-event"), covariates: multiVal("cox-cov")
        }, "stcox"),
    },
    power: {
        title: "Power Analysis",
        build: () =>
            `<div class="form-group"><label>Test type</label><select class="form-control" id="pow-test">
                <option value="t-test">T-Test</option><option value="anova">ANOVA</option>
                <option value="chi-square">Chi-Square</option></select></div>` +
            formNum("pow-n", "Sample size per group", 30) +
            formNum("pow-alpha", "Alpha", 0.05) +
            formNum("pow-delta", "Effect size (delta or f)", 0.5) +
            formNum("pow-sd", "Standard deviation", 1),
        run: () => apiRun("/api/stats/power", {
            test_type: val("pow-test"),
            n: numVal("pow-n"), alpha: numVal("pow-alpha"),
            delta: numVal("pow-delta"), sd: numVal("pow-sd")
        }, "power"),
    },
    sample_size: {
        title: "Sample Size Calculator",
        build: () =>
            `<div class="form-group"><label>Test type</label><select class="form-control" id="ss-test">
                <option value="t-test">T-Test</option><option value="anova">ANOVA</option>
                <option value="chi-square">Chi-Square</option><option value="proportion">Proportion</option></select></div>` +
            formNum("ss-effect", "Effect size", 0.5) +
            formNum("ss-sd2", "SD (if applicable)", 1) +
            formNum("ss-alpha2", "Alpha", 0.05) +
            formNum("ss-power2", "Desired power", 0.80) +
            formNum("ss-groups", "Number of groups", 2),
        run: () => apiRun("/api/stats/sample_size", {
            test_type: val("ss-test"),
            effect_size: numVal("ss-effect"), sd: numVal("ss-sd2"),
            alpha: numVal("ss-alpha2"), power: numVal("ss-power2"),
            k_groups: numVal("ss-groups")
        }, "power sampsi"),
    },
};

function initTestButtons() {
    document.querySelectorAll("[data-test]").forEach(btn => {
        btn.addEventListener("click", () => openStatModal(btn.dataset.test));
    });
    document.getElementById("btn-smart")?.addEventListener("click", runSmartAnalysis);
}

function openStatModal(testKey) {
    const cfg = TEST_CONFIG[testKey];
    if (!cfg) { toast(`Unknown test: ${testKey}`, "error"); return; }
    if (!S.loaded && !["power", "sample_size"].includes(testKey)) {
        toast("Load data first", "error"); return;
    }
    S.curTest = testKey;
    document.getElementById("stat-modal-title").textContent = cfg.title;
    document.getElementById("stat-modal-body").innerHTML = cfg.build();
    populateSelectors();
    openModal("stat-modal");
}

/* ==================================================================
   11. AGENT BUTTONS
   ================================================================== */
function initAgentButtons() {
    document.getElementById("btn-universal")?.addEventListener("click", () => openModal("universal-modal"));
    document.getElementById("btn-ai-analyze")?.addEventListener("click", () => {
        if (!S.loaded) { toast("Load data first", "error"); return; }
        openModal("ai-modal");
    });
    document.getElementById("btn-messy-data")?.addEventListener("click", () => {
        if (!S.loaded) { toast("Load data first", "error"); return; }
        openModal("messy-modal");
    });
    document.getElementById("btn-sample-size-text")?.addEventListener("click", () => openModal("sample-size-modal"));
    document.getElementById("btn-lit-review")?.addEventListener("click", () => openModal("lit-modal"));

    // Run buttons in agent modals
    document.getElementById("universal-run-btn")?.addEventListener("click", runUniversalAnalysis);
    document.getElementById("universal-file-btn")?.addEventListener("click", () => {
        document.getElementById("universal-file-input")?.click();
    });
    document.getElementById("universal-file-input")?.addEventListener("change", handleUniversalFile);
    document.getElementById("ai-run-btn")?.addEventListener("click", runAIAnalysis);
    document.getElementById("ss-run-btn")?.addEventListener("click", runSampleSizeText);
    document.getElementById("messy-run-btn")?.addEventListener("click", runMessyData);
    document.getElementById("lit-run-btn")?.addEventListener("click", runLitReview);
}

/* ==================================================================
   12. MODAL SYSTEM
   ================================================================== */
function initModals() {
    // Close on backdrop click
    document.querySelectorAll(".modal-overlay").forEach(overlay => {
        overlay.addEventListener("click", e => {
            if (e.target === overlay) overlay.classList.remove("active");
        });
    });
    // Close on X button
    document.querySelectorAll("[data-dismiss]").forEach(btn => {
        btn.addEventListener("click", () => closeModal(btn.dataset.dismiss));
    });
    // Stat modal run button
    document.getElementById("stat-modal-run")?.addEventListener("click", () => {
        if (S.curTest && TEST_CONFIG[S.curTest]) {
            closeModal("stat-modal");
            TEST_CONFIG[S.curTest].run();
        }
    });
}

function openModal(id) {
    document.getElementById(id)?.classList.add("active");
}

function closeModal(id) {
    document.getElementById(id)?.classList.remove("active");
}

/* ==================================================================
   13. FORM BUILDERS (for generic stat modal)
   ================================================================== */
function formVar(id, label, type) {
    return `<div class="form-group"><label>${label}</label>
        <select class="form-control var-selector" id="${id}" data-type="${type}">
        <option value="">-- Select --</option></select></div>`;
}

function formMultiVar(id, type) {
    return `<div class="form-group"><label>Variables</label>
        <select class="form-control var-multi-selector" id="${id}" data-type="${type}" multiple size="5">
        </select><div class="form-hint">Hold Ctrl/Cmd to select multiple</div></div>`;
}

function formNum(id, label, defaultVal) {
    return `<div class="form-group"><label>${label}</label>
        <input class="form-control" type="number" id="${id}" value="${defaultVal}" step="any"></div>`;
}

function formCheck(id, label, checked) {
    return `<div class="form-check"><input type="checkbox" id="${id}" ${checked ? "checked" : ""}>
        <label for="${id}">${label}</label></div>`;
}

function populateSelectors() {
    document.querySelectorAll(".var-selector").forEach(sel => {
        const type = sel.dataset.type;
        let vars = S.columns;
        if (type === "numeric" && S.dataInfo) vars = S.dataInfo.numeric_columns || S.columns;
        else if (type === "categorical" && S.dataInfo) vars = S.dataInfo.categorical_columns || S.columns;
        const cur = sel.value;
        sel.innerHTML = '<option value="">-- Select --</option>';
        vars.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v; opt.textContent = v;
            if (v === cur) opt.selected = true;
            sel.appendChild(opt);
        });
    });
    document.querySelectorAll(".var-multi-selector").forEach(sel => {
        const type = sel.dataset.type;
        let vars = S.columns;
        if (type === "numeric" && S.dataInfo) vars = S.dataInfo.numeric_columns || S.columns;
        sel.innerHTML = "";
        vars.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v; opt.textContent = v;
            sel.appendChild(opt);
        });
    });
}

function val(id) { return document.getElementById(id)?.value || ""; }
function numVal(id) { return parseFloat(document.getElementById(id)?.value) || 0; }
function isChecked(id) { return document.getElementById(id)?.checked || false; }
function multiVal(id) {
    const sel = document.getElementById(id);
    if (!sel) return [];
    return Array.from(sel.selectedOptions).map(o => o.value);
}

/* ==================================================================
   14. API HELPER
   ================================================================== */
async function apiRun(url, payload, label) {
    switchTab("output");
    appendOutput("command", label, "Computing...");
    try {
        const r = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const d = await r.json();
        if (d.error) {
            updateLastOutput(d.error, "error");
            toast(d.error, "error");
        } else {
            updateLastOutput(formatResult(d.result));
        }
    } catch (err) {
        updateLastOutput(`Error: ${err.message}`, "error");
    }
}

/* ==================================================================
   15. RESULT FORMATTING
   ================================================================== */
function formatResult(obj) {
    if (obj == null) return "No result";
    if (typeof obj === "string") return obj;
    if (obj.output) return obj.output;
    if (obj.result_str) return obj.result_str;
    if (obj.summary) return obj.summary;
    if (obj.stdout) return obj.stdout;
    if (Array.isArray(obj)) return formatTable(obj);
    return formatStatResult(obj);
}

function formatStatResult(obj) {
    const L = [];
    // Test header
    if (obj.test) { L.push(`  Test: ${obj.test}`); L.push("  " + "=".repeat(50)); }
    if (obj.error) { L.push(`  Error: ${obj.error}`); return L.join("\n"); }

    // T-test
    if (obj.t_stat !== undefined || obj.t !== undefined) {
        const t = obj.t_stat ?? obj.t;
        L.push("");
        if (obj.Variable) L.push(`  Variable: ${obj.Variable}`);
        if (obj.Obs) L.push(`  Obs: ${obj.Obs}`);
        if (obj.Mean !== undefined) L.push(`  Mean: ${obj.Mean}`);
        if (obj["Std. Err."] !== undefined) L.push(`  Std. Err.: ${obj["Std. Err."]}`);
        if (obj["95% CI"]) L.push(`  95% CI: [${obj["95% CI"].join(", ")}]`);
        L.push(""); L.push(`  t = ${n4(t)}`);
        if (obj.df !== undefined) L.push(`  df = ${obj.df}`);
        if (obj.p !== undefined) L.push(`  p = ${n6(obj.p)}`);
        if (obj["p (two-tail)"] !== undefined) L.push(`  p (two-tail) = ${obj["p (two-tail)"]}`);
        if (obj.Group_1) L.push(`\n  Group 1: ${obj.Group_1} (n=${obj.n1}, mean=${obj.mean1})`);
        if (obj.Group_2) L.push(`  Group 2: ${obj.Group_2} (n=${obj.n2}, mean=${obj.mean2})`);
        if (obj.mean_diff !== undefined) L.push(`  Mean Difference: ${obj.mean_diff}`);
        return L.join("\n");
    }

    // Chi-square
    if (obj.chi2 !== undefined && obj.Pr !== undefined) {
        L.push(""); L.push(`  Pearson chi2(${obj.df ?? "?"}) = ${obj.chi2}`);
        L.push(`  Pr = ${obj.Pr}`);
        if (obj.cramers_v !== undefined) L.push(`  Cramer's V = ${obj.cramers_v}`);
        if (obj.observed_str) L.push(`\n  Observed:\n${obj.observed_str}`);
        if (obj.expected_str) L.push(`\n  Expected:\n${obj.expected_str}`);
        return L.join("\n");
    }

    // Fisher
    if (obj.odds_ratio !== undefined && obj.p !== undefined && obj.t_stat === undefined) {
        L.push(""); L.push(`  Odds Ratio: ${obj.odds_ratio}`);
        L.push(`  p-value: ${obj.p}`);
        if (obj["95% CI"]) L.push(`  95% CI: [${obj["95% CI"].join(", ")}]`);
        return L.join("\n");
    }

    // Normality
    if (obj.Shapiro_W !== undefined) {
        L.push("");
        if (obj.Variable) L.push(`  Variable: ${obj.Variable}`);
        L.push(`  Shapiro-Wilk W = ${obj.Shapiro_W}`);
        if (obj.Shapiro_p !== undefined) L.push(`  Shapiro-Wilk p = ${obj.Shapiro_p}`);
        if (obj.normal !== undefined) L.push(`\n  Normal: ${obj.normal ? "Yes" : "No"}`);
        return L.join("\n");
    }

    // Mann-Whitney
    if (obj.U !== undefined) {
        L.push(`\n  U = ${obj.U}`); L.push(`  p = ${obj.p}`);
        if (obj.Group_1) L.push(`  ${obj.Group_1}: n=${obj.n1}, median=${obj.median1 ?? "N/A"}`);
        if (obj.Group_2) L.push(`  ${obj.Group_2}: n=${obj.n2}, median=${obj.median2 ?? "N/A"}`);
        return L.join("\n");
    }

    // Kruskal-Wallis
    if (obj.H !== undefined) {
        L.push(`\n  H = ${obj.H}`); L.push(`  df = ${obj.df}`); L.push(`  p = ${obj.p}`);
        if (obj.groups) obj.groups.forEach(g => L.push(`  ${g.Group}: n=${g.N}, median=${g.Median ?? "N/A"}`));
        return L.join("\n");
    }

    // Wilcoxon
    if (obj.T !== undefined && obj.p !== undefined && obj.t_stat === undefined) {
        L.push(`\n  T = ${obj.T}`); L.push(`  p = ${obj.p}`);
        return L.join("\n");
    }

    // Correlation
    if (obj.correlation_str) {
        L.push(""); L.push(obj.correlation_str);
        if (obj.p_values_str) { L.push("\n  P-values:"); L.push(obj.p_values_str); }
        return L.join("\n");
    }

    // Post-hoc comparisons
    if (obj.comparisons && Array.isArray(obj.comparisons)) {
        L.push(`  ${"Comparison".padEnd(30)} ${"Diff".padStart(10)} ${"p-value".padStart(12)} Sig`);
        L.push("  " + "-".repeat(58));
        obj.comparisons.forEach(c => {
            const comp = `${c.group1 || c.Group1} vs ${c.group2 || c.Group2}`;
            const diff = c.mean_diff ?? c.meandiff ?? c.diff ?? "";
            const p = c.p_adj ?? c.p ?? "";
            const sig = (c.significant || c.reject) ? " ***" : "";
            L.push(`  ${comp.padEnd(30)} ${n4s(diff).padStart(10)} ${n6s(p).padStart(12)}${sig}`);
        });
        return L.join("\n");
    }

    // Power / Sample size
    if (obj.power !== undefined && obj.n !== undefined) {
        L.push(""); L.push(`  Power: ${obj.power}`); L.push(`  N per group: ${obj.n}`);
        if (obj.effect_size !== undefined) L.push(`  Effect size: ${obj.effect_size}`);
        if (obj.alpha !== undefined) L.push(`  Alpha: ${obj.alpha}`);
        return L.join("\n");
    }

    // Repeated measures
    if (obj.F !== undefined && obj.p_value !== undefined) {
        L.push(""); L.push(`  F = ${obj.F}`); L.push(`  p = ${obj.p_value}`);
        if (obj.condition_stats) obj.condition_stats.forEach(cs => {
            L.push(`  ${cs.Condition || cs.condition}: N=${cs.N}, Mean=${n4s(cs.Mean)}, SD=${n4s(cs.SD)}`);
        });
        return L.join("\n");
    }

    // Friedman
    if (obj.chi2 !== undefined && obj.p_value !== undefined) {
        L.push(""); L.push(`  Chi2 = ${obj.chi2}`); L.push(`  df = ${obj.df}`); L.push(`  p = ${obj.p_value}`);
        if (obj.kendall_w !== undefined) L.push(`  Kendall's W = ${obj.kendall_w}`);
        return L.join("\n");
    }

    // Fallback
    return formatObj(obj);
}

function formatTable(arr) {
    if (!arr.length) return "[]";
    const keys = Object.keys(arr[0]);
    const widths = keys.map(k => Math.max(k.length, ...arr.map(r => String(r[k] ?? "").length)));
    let h = "  " + keys.map((k, i) => k.padEnd(widths[i])).join("  ") + "\n";
    h += "  " + widths.map(w => "-".repeat(w)).join("  ") + "\n";
    arr.forEach(row => {
        h += "  " + keys.map((k, i) => String(row[k] ?? "").padEnd(widths[i])).join("  ") + "\n";
    });
    return h;
}

function formatObj(obj) {
    if (obj == null) return "No result";
    try { return JSON.stringify(obj, null, 2); } catch { return String(obj); }
}

function n4(v) { return typeof v === "number" ? v.toFixed(4) : v; }
function n6(v) { return typeof v === "number" ? v.toFixed(6) : v; }
function n4s(v) { return typeof v === "number" ? v.toFixed(4) : String(v ?? ""); }
function n6s(v) { return typeof v === "number" ? v.toFixed(6) : String(v ?? ""); }

/* ==================================================================
   16. SMART ANALYSIS
   ================================================================== */
async function runSmartAnalysis() {
    if (!S.loaded) { toast("Load data first", "error"); return; }
    if (S.selectedVars.length === 0) { toast("Select at least one variable", "error"); return; }
    switchTab("output");
    const label = `smart analyze ${S.selectedVars.join(" ")}`;
    appendOutput("command", label, "Analyzing data structure and selecting test...");
    try {
        const r = await fetch("/api/stats/smart", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ columns: S.selectedVars }),
        });
        const d = await r.json();
        if (d.error) { updateLastOutput(d.error, "error"); return; }
        const res = d.result;
        let out = "=".repeat(60) + "\n  SMART STATISTICAL ROUTER\n" + "=".repeat(60) + "\n\n";
        if (res.selected_test) out += `  Selected Test: ${res.selected_test}\n`;
        if (res.reasoning) out += `  Reasoning: ${res.reasoning}\n\n`;
        if (res.variable_types) {
            out += "  Variable Classification:\n";
            Object.entries(res.variable_types).forEach(([v, t]) => out += `    ${v}: ${t}\n`);
            out += "\n";
        }
        if (res.result) {
            out += "  --- Results ---\n";
            out += (res.result.output || formatResult(res.result)) + "\n\n";
        }
        if (res.posthoc) {
            out += "  --- Post-Hoc ---\n";
            if (res.posthoc_note) out += `  ${res.posthoc_note}\n`;
            if (res.posthoc.comparisons) {
                res.posthoc.comparisons.forEach(c => {
                    out += `    ${c.Group1} vs ${c.Group2}: diff=${c.Mean_Diff}, p=${c.p_adj || c.p_bonferroni}`;
                    out += (c.Significant || c.Reject_H0 === "True") ? " *\n" : "\n";
                });
            }
        }
        out += "=".repeat(60);
        updateLastOutput(out);
        toast(`Analysis complete: ${res.selected_test}`, "success");
    } catch (err) {
        updateLastOutput(`Error: ${err.message}`, "error");
    }
}

/* ==================================================================
   17. UNIVERSAL ANALYSIS (3-Stage Pipeline)
   ================================================================== */
let universalFile = null;

function handleUniversalFile(e) {
    const f = e.target.files[0];
    if (!f) return;
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (ext === ".csv") {
        const reader = new FileReader();
        reader.onload = ev => {
            document.getElementById("universal-data-text").value = ev.target.result;
            universalFile = null;
        };
        reader.readAsText(f);
    } else {
        universalFile = f;
        document.getElementById("universal-data-text").value = "";
        document.getElementById("universal-data-text").placeholder = `File loaded: ${f.name}`;
    }
    document.getElementById("universal-file-name").textContent = f.name;
}

function setStepper(stage, state, text) {
    const el = document.getElementById(`stage-${stage}`);
    const icon = document.getElementById(`stage-${stage}-icon`);
    const status = document.getElementById(`stage-${stage}-status`);
    if (el) el.className = `progress-stage ${state}`;
    if (icon) icon.textContent = state === "complete" ? "OK" : state === "error" ? "X" : state === "active" ? "*" : stage;
    if (status && text) status.textContent = text;
}

async function runUniversalAnalysis() {
    const raw = document.getElementById("universal-data-text")?.value || "";
    const ctx = document.getElementById("universal-context")?.value || "";
    const tt = document.getElementById("universal-test-type")?.value || "";
    if (!raw.trim() && !universalFile) { toast("Paste data or upload file", "error"); return; }

    // Show stepper
    const stepper = document.getElementById("universal-stepper");
    if (stepper) stepper.style.display = "";
    setStepper(1, "active", "Organizing...");
    setStepper(2, "waiting", "Waiting");
    setStepper(3, "waiting", "Waiting");

    const btn = document.getElementById("universal-run-btn");
    if (btn) btn.disabled = true;
    switchTab("output");
    appendOutput("command", "agent universal_analyze",
        "Running 3-Stage Pipeline...\n  Stage 1: Data Organizer\n  Stage 2: Calculator\n  Stage 3: Reporter");
    setStatus("loading", "Stage 1: Organizing data...");

    const ac = new AbortController();
    const tid = setTimeout(() => ac.abort(), 300000);

    try {
        let resp;
        if (universalFile) {
            const fd = new FormData();
            fd.append("file", universalFile);
            fd.append("proposal_context", ctx);
            if (tt) fd.append("test_type", tt);
            resp = await fetch("/api/agent/universal_analyze_file", { method: "POST", body: fd, signal: ac.signal });
        } else {
            resp = await fetch("/api/agent/universal_analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ raw_text: raw, proposal_context: ctx, test_type: tt || null }),
                signal: ac.signal,
            });
        }
        clearTimeout(tid);
        const d = await resp.json();

        if (d.error || d.result?.error) {
            const fs = d.result?.failed_stage || 1;
            for (let i = 1; i < fs; i++) setStepper(i, "complete", "Done");
            setStepper(fs, "error", "Failed");
            updateLastOutput(d.error || d.result.error, "error");
            setStatus("error", "Analysis failed");
            delayCleanup(btn, stepper);
            return;
        }

        setStepper(1, "complete", "Done");
        setStepper(2, "complete", "Done");
        setStepper(3, "complete", "Done");

        const res = d.result;
        let out = "=".repeat(60) + "\n  UNIVERSAL STATISTICAL ANALYSIS\n" + "=".repeat(60) + "\n\n";

        // Stage 1
        if (res.layer1_extraction) {
            out += ">>> STAGE 1: DATA ORGANIZER\n" + "-".repeat(40) + "\n";
            out += `  Groups: ${res.layer1_extraction.groups_found?.join(", ") || "N/A"}\n`;
            if (res.layer1_extraction.samples_per_group) {
                Object.entries(res.layer1_extraction.samples_per_group).forEach(([g, n]) =>
                    out += `    ${g}: n=${n}\n`);
            }
            out += "\n";
        }

        // Stage 2
        if (res.layer2_statistics) {
            const st = res.layer2_statistics;
            out += ">>> STAGE 2: PYTHON CALCULATOR\n" + "-".repeat(40) + "\n\n";

            if (st.descriptive) {
                out += "  DESCRIPTIVE STATISTICS\n  " + "-".repeat(56) + "\n";
                out += "  " + "Group".padEnd(18) + "N".padStart(6) + "Mean".padStart(10) + "SD".padStart(10) + "   95% CI\n";
                out += "  " + "-".repeat(56) + "\n";
                Object.entries(st.descriptive).forEach(([g, d]) => {
                    let ci = "N/A";
                    if (Array.isArray(d.ci_95) && d.ci_95.length === 2) ci = `[${d.ci_95[0].toFixed(2)}, ${d.ci_95[1].toFixed(2)}]`;
                    else if (d.ci_95_lower != null) ci = `[${d.ci_95_lower.toFixed(2)}, ${d.ci_95_upper.toFixed(2)}]`;
                    out += `  ${g.padEnd(18)} ${String(d.n).padStart(6)} ${d.mean.toFixed(3).padStart(10)} ${d.std.toFixed(3).padStart(10)}   ${ci}\n`;
                });
                out += "\n";
            }

            if (st.anova) {
                out += "  ONE-WAY ANOVA\n  " + "-".repeat(35) + "\n";
                out += `  F = ${st.anova.F_statistic}\n  p = ${st.anova.p_value}`;
                out += st.anova.significant ? " ***\n" : "\n";
                if (st.anova.conclusion) out += `  ${st.anova.conclusion}\n`;
                out += "\n";
            }

            if (st.posthoc?.comparisons) {
                out += "  TUKEY HSD\n  " + "-".repeat(55) + "\n";
                out += "  " + "Comparison".padEnd(28) + "Diff".padStart(10) + "p-adj".padStart(12) + " Sig\n";
                out += "  " + "-".repeat(55) + "\n";
                st.posthoc.comparisons.forEach(c => {
                    const sig = c.significant ? " ***" : "";
                    out += `  ${(c.group1 + " vs " + c.group2).padEnd(28)} ${c.mean_diff.toFixed(3).padStart(10)} ${c.p_adj.toFixed(6).padStart(12)}${sig}\n`;
                });
                out += "\n";
            }

            if (st.power_analysis && !st.power_analysis.error) {
                const pa = st.power_analysis;
                out += "  POWER ANALYSIS\n  " + "-".repeat(40) + "\n";
                out += `  Effect size (f): ${pa.effect_size_f}\n`;
                out += `  Observed power: ${pa.observed_power}\n`;
                out += `  Current N/group: ${pa.current_n_per_group}\n`;
                if (!pa.adequate_power) out += `  Recommended N: ${pa.recommended_n_per_group}\n`;
                out += "\n";
            }
        }

        // Stage 3
        if (res.layer3_interpretation) {
            const interp = res.layer3_interpretation;
            out += ">>> STAGE 3: REPORTER\n" + "-".repeat(40) + "\n\n";
            if (interp.report) {
                out += "  ACADEMIC RESULTS:\n  " + "=".repeat(45) + "\n\n";
                wordWrap(interp.report, 70).forEach(line => out += `  ${line}\n`);
            }
        }

        out += "\n" + "=".repeat(60) + "\n  PIPELINE COMPLETE\n" + "=".repeat(60);
        updateLastOutput(out);
        setStatus("ok", "Pipeline complete");
        toast("Universal analysis complete", "success");
        universalFile = null;
        delayCleanup(btn, stepper, true);

    } catch (err) {
        clearTimeout(tid);
        setStepper(1, "error", "Failed");
        updateLastOutput(err.name === "AbortError" ? "Timed out" : `Error: ${err.message}`, "error");
        setStatus("error", "Analysis failed");
        delayCleanup(btn, stepper);
    }
}

function delayCleanup(btn, stepper, closeM) {
    setTimeout(() => {
        if (stepper) stepper.style.display = "none";
        if (btn) btn.disabled = false;
        if (closeM) closeModal("universal-modal");
    }, 1500);
}

/* ==================================================================
   18. AI ANALYSIS
   ================================================================== */
async function runAIAnalysis() {
    const proposal = document.getElementById("ai-proposal-text")?.value || "";
    const question = document.getElementById("ai-question")?.value || "";
    const research = isChecked("ai-lit-search");
    closeModal("ai-modal");
    switchTab("output");
    appendOutput("command", "ai analyze", "Running AI analysis...");
    setStatus("loading", "AI analyzing...");
    try {
        const r = await fetch("/api/agent/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ proposal, question, do_research: research }),
        });
        const d = await r.json();
        if (d.error) { updateLastOutput(d.error, "error"); setStatus("error", "Failed"); return; }
        const res = d.result;
        let out = "";
        if (res?.stdout) out = res.stdout;
        else if (res?.output) out = res.output;
        else out = formatObj(res);
        updateLastOutput(out);
        setStatus("ok", "AI analysis complete");
    } catch (err) {
        updateLastOutput(`Error: ${err.message}`, "error");
        setStatus("error", "AI failed");
    }
}

/* ==================================================================
   19. SAMPLE SIZE FROM TEXT
   ================================================================== */
async function runSampleSizeText() {
    const text = document.getElementById("ss-description")?.value || "";
    const alpha = parseFloat(document.getElementById("ss-alpha")?.value) || 0.05;
    const power = parseFloat(document.getElementById("ss-power")?.value) || 0.80;
    if (!text.trim()) { toast("Paste text with Mean/SD values", "error"); return; }
    closeModal("sample-size-modal");
    switchTab("output");
    appendOutput("command", "sample size from text", "Parsing Mean/SD values...");
    try {
        const r = await fetch("/api/agent/sample_size_text", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, alpha, power }),
        });
        const d = await r.json();
        if (d.error || d.result?.error) { updateLastOutput(d.error || d.result.error, "error"); return; }
        const res = d.result;
        let out = "=".repeat(60) + "\n  SAMPLE SIZE (from text)\n" + "=".repeat(60) + "\n\n";
        if (res.group1 && res.group2) {
            out += `  Group 1 (${res.group1.name}): Mean=${res.group1.mean}, SD=${res.group1.sd}\n`;
            out += `  Group 2 (${res.group2.name}): Mean=${res.group2.mean}, SD=${res.group2.sd}\n\n`;
        }
        if (res.effect_size) {
            out += `  Cohen's d = ${res.effect_size.cohens_d} (${res.effect_size.interpretation})\n\n`;
        }
        if (res.calculation) {
            const c = res.calculation;
            out += `  Required N per group: ${c.n_per_group}\n`;
            out += `  Total N: ${c.total_n}\n`;
            out += `  Alpha=${c.alpha}, Power=${c.power}\n`;
        }
        out += "\n" + "=".repeat(60);
        updateLastOutput(out);
        toast("Sample size calculated", "success");
    } catch (err) {
        updateLastOutput(`Error: ${err.message}`, "error");
    }
}

/* ==================================================================
   20. MESSY DATA
   ================================================================== */
async function runMessyData() {
    const desc = document.getElementById("messy-description")?.value || "";
    closeModal("messy-modal");
    switchTab("output");
    appendOutput("command", "agent messy_data", "Analyzing loaded data...");
    setStatus("loading", "Agent analyzing...");
    try {
        const r = await fetch("/api/agent/messy_data", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description: desc }),
        });
        const d = await r.json();
        if (d.error || d.result?.error) {
            updateLastOutput(d.error || d.result.error, "error");
            setStatus("error", "Failed"); return;
        }
        const res = d.result;
        let out = "=".repeat(60) + "\n  MESSY DATA ANALYSIS\n" + "=".repeat(60) + "\n\n";
        if (res.statistics) {
            const st = res.statistics;
            if (st.anova_results) {
                out += "  ANOVA Results:\n";
                Object.entries(st.anova_results).forEach(([tp, r]) => {
                    out += `    [${tp}] F=${r.F_statistic}, p=${r.p_value}${r.significant ? " ***" : ""}\n`;
                });
                out += "\n";
            }
            if (st.descriptive_stats) {
                out += "  Descriptive Stats:\n";
                Object.entries(st.descriptive_stats).forEach(([tp, groups]) => {
                    out += `    [${tp}]\n`;
                    Object.entries(groups).forEach(([g, d]) => {
                        out += `      ${g}: Mean=${d.mean}, SD=${d.std}, N=${d.n}\n`;
                    });
                });
                out += "\n";
            }
        }
        if (res.interpretation) out += `  Interpretation:\n  ${res.interpretation}\n`;
        out += "\n" + "=".repeat(60);
        updateLastOutput(out);
        setStatus("ok", "Analysis complete");
        toast("Messy data analysis complete", "success");
    } catch (err) {
        updateLastOutput(`Error: ${err.message}`, "error");
        setStatus("error", "Failed");
    }
}

/* ==================================================================
   21. LITERATURE REVIEW
   ================================================================== */
async function runLitReview() {
    const query = document.getElementById("lit-query")?.value || "";
    const max = parseInt(document.getElementById("lit-max")?.value) || 5;
    if (!query.trim()) { toast("Enter a topic", "error"); return; }
    closeModal("lit-modal");
    switchTab("output");
    appendOutput("command", `literature "${query.substring(0, 40)}"`, "Searching...");
    setStatus("loading", "Searching literature...");
    try {
        const r = await fetch("/api/agent/literature", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, max_results: max }),
        });
        const d = await r.json();
        if (d.error || d.result?.error) {
            updateLastOutput(d.error || d.result.error, "error");
            setStatus("error", "Failed"); return;
        }
        const res = d.result;
        let out = "=".repeat(60) + "\n  LITERATURE REVIEW\n" + "=".repeat(60) + "\n\n";
        out += `  Topic: ${query}\n  Sources: ${res.sources_searched || 0}\n\n`;
        if (res.review) out += res.review + "\n\n";
        if (res.references?.length) {
            out += "  References:\n";
            res.references.forEach(r => out += `    [${r.number}] ${r.title}\n        ${r.url}\n`);
        }
        out += "\n" + "=".repeat(60);
        updateLastOutput(out);
        setStatus("ok", "Review complete");
        toast("Literature review generated", "success");
    } catch (err) {
        updateLastOutput(`Error: ${err.message}`, "error");
        setStatus("error", "Failed");
    }
}

/* ==================================================================
   22. MODEL MANAGEMENT / OLLAMA STATUS
   ================================================================== */
async function loadModels() {
    try {
        const r = await fetch("/api/agent/models");
        const d = await r.json();
        const sel = document.getElementById("model-select");
        const dot = document.getElementById("ollama-status");
        if (sel && d.models) {
            sel.innerHTML = "";
            d.models.forEach(m => {
                const opt = document.createElement("option");
                opt.value = m; opt.textContent = m;
                if (m === d.current) opt.selected = true;
                sel.appendChild(opt);
            });
            sel.addEventListener("change", () => changeModel(sel.value));
        }
        if (dot) {
            dot.classList.remove("connecting");
            if (d.ollama_running) {
                dot.classList.add("connected");
                dot.title = "Ollama running";
            } else {
                dot.classList.add("warning");
                dot.title = "Ollama not available";
            }
        }
        const banner = document.getElementById("fallback-banner");
        if (banner) banner.style.display = d.fallback_mode ? "" : "none";
    } catch {
        const dot = document.getElementById("ollama-status");
        if (dot) { dot.classList.remove("connecting"); dot.classList.add("warning"); dot.title = "Cannot reach server"; }
    }
}

async function changeModel(name) {
    try {
        await fetch("/api/agent/models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: name }),
        });
        toast(`Model set to ${name}`, "success");
    } catch (err) {
        toast(`Failed: ${err.message}`, "error");
    }
}

/* ==================================================================
   23. STATUS BAR
   ================================================================== */
function setStatus(type, text) {
    const dot = document.getElementById("status-dot");
    const msg = document.getElementById("status-message");
    if (dot) {
        dot.className = "status-dot";
        if (type === "error") dot.classList.add("error");
        else if (type === "loading") dot.classList.add("warning");
        else if (type === "ok") dot.classList.add("connected");
    }
    if (msg) msg.textContent = text;
}

/* ==================================================================
   24. TOAST NOTIFICATIONS
   ================================================================== */
function toast(message, type) {
    type = type || "info";
    const container = document.getElementById("toast-container");
    if (!container) return;
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.textContent = message;
    container.appendChild(t);
    requestAnimationFrame(() => t.classList.add("show"));
    setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 300); }, 3500);
}

/* ==================================================================
   25. KEYBOARD SHORTCUTS
   ================================================================== */
function initKeyboard() {
    document.addEventListener("keydown", e => {
        if (e.ctrlKey && e.key === "o") { e.preventDefault(); document.getElementById("file-input")?.click(); }
        if (e.ctrlKey && e.key === "l") { e.preventDefault(); document.getElementById("command-input")?.focus(); }
        if (e.ctrlKey && e.key >= "1" && e.key <= "3") {
            e.preventDefault();
            const tabs = ["output", "data", "graph"];
            switchTab(tabs[parseInt(e.key) - 1]);
        }
        if (e.key === "Escape") {
            document.querySelectorAll(".modal-overlay.active").forEach(m => m.classList.remove("active"));
        }
    });
}

/* ==================================================================
   26. UTILITIES
   ================================================================== */
function esc(str) {
    if (!str) return "";
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}

function wordWrap(text, maxLen) {
    const words = text.split(" ");
    const lines = [];
    let cur = "";
    words.forEach(w => {
        if (cur.length + w.length + 1 > maxLen) { lines.push(cur); cur = w; }
        else cur = cur ? cur + " " + w : w;
    });
    if (cur) lines.push(cur);
    return lines;
}
