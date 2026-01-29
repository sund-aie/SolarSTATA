/**
 * SolarSTATA - Main Application JavaScript
 * Stata 19-like interface with AI integration
 */

// ============================================================
// STATE
// ============================================================
const State = {
    dataLoaded: false,
    columns: [],
    dtypes: {},
    dataInfo: null,
    selectedVars: [],
    commandHistory: [],
    historyIndex: -1,
    currentTab: "welcome",
    aiMessages: [],
};

// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initCommandInput();
    initAIChat();
    initFileUpload();
    initRightPanel();
    initKeyboardShortcuts();
    loadAvailableModels();
    showToast("SolarSTATA ready. Load data to begin.", "success");
});

// ============================================================
// TAB MANAGEMENT
// ============================================================
function initTabs() {
    document.querySelectorAll(".tab").forEach(tab => {
        tab.addEventListener("click", () => {
            switchTab(tab.dataset.tab);
        });
    });
}

function switchTab(tabId) {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

    const tab = document.querySelector(`.tab[data-tab="${tabId}"]`);
    const content = document.getElementById(`tab-${tabId}`);
    if (tab) tab.classList.add("active");
    if (content) content.classList.add("active");
    State.currentTab = tabId;
}

// ============================================================
// FILE UPLOAD
// ============================================================
function initFileUpload() {
    // Hidden file input
    const fileInput = document.getElementById("file-input");
    if (fileInput) {
        fileInput.addEventListener("change", handleFileUpload);
    }
}

function openFile() {
    document.getElementById("file-input").click();
}

async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setStatus("loading", `Loading ${file.name}...`);
    showToast(`Uploading ${file.name}...`);

    try {
        const resp = await fetch("/api/upload", { method: "POST", body: formData });
        const data = await resp.json();

        if (data.error) {
            showToast(data.error, "error");
            setStatus("error", data.error);
            return;
        }

        State.dataLoaded = true;
        State.columns = data.columns;
        State.dtypes = data.dtypes;
        State.dataInfo = data.data_info;

        updateVariablesList(data.data_info);
        renderDataTable(data.preview, data.columns);
        updateProperties(data);
        switchTab("data");
        setStatus("ok", `${data.filename}: ${data.shape[0]} obs, ${data.shape[1]} vars`);
        appendOutput("use", `"${data.filename}"`, data.message);
        showToast(data.message, "success");
    } catch (err) {
        showToast(`Upload failed: ${err.message}`, "error");
        setStatus("error", "Upload failed");
    }

    e.target.value = "";
}

// ============================================================
// VARIABLES PANEL
// ============================================================
function updateVariablesList(dataInfo) {
    const list = document.getElementById("variables-list");
    const count = document.getElementById("var-count");
    if (!dataInfo) return;

    const vars = dataInfo.variable_info || [];
    if (count) count.textContent = vars.length;

    list.innerHTML = vars.map((v, i) => {
        const typeClass = v.Type === "continuous" ? "numeric" : "categorical";
        const badge = v.Type === "continuous" ? "num" : "str";
        return `<div class="var-item" data-var="${v.Variable}" onclick="selectVariable('${v.Variable}', this)">
            <span class="var-type-badge ${typeClass}">${badge}</span>
            <span class="var-name">${v.Variable}</span>
        </div>`;
    }).join("");
}

function selectVariable(varName, el) {
    const idx = State.selectedVars.indexOf(varName);
    if (idx >= 0) {
        State.selectedVars.splice(idx, 1);
        el.classList.remove("selected");
    } else {
        State.selectedVars.push(varName);
        el.classList.add("selected");
    }
    updateSelectedVarsDisplay();
}

function updateSelectedVarsDisplay() {
    const disp = document.getElementById("selected-vars-display");
    if (disp) {
        disp.textContent = State.selectedVars.length > 0
            ? State.selectedVars.join(", ")
            : "None";
    }
}

// ============================================================
// DATA TABLE
// ============================================================
function renderDataTable(rows, columns) {
    const container = document.getElementById("data-editor");
    if (!rows || rows.length === 0) {
        container.innerHTML = '<div style="padding:20px;color:var(--text-muted);">No data loaded</div>';
        return;
    }

    let html = '<table class="data-table"><thead><tr><th class="row-num">#</th>';
    columns.forEach(col => {
        html += `<th>${col}</th>`;
    });
    html += '</tr></thead><tbody>';

    rows.forEach((row, i) => {
        html += `<tr><td class="row-num">${i + 1}</td>`;
        columns.forEach(col => {
            const val = row[col];
            const display = val === null || val === undefined ? "." : val;
            html += `<td>${display}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

async function loadMoreData(page) {
    try {
        const resp = await fetch(`/api/data/preview?page=${page}&per_page=100`);
        const data = await resp.json();
        if (data.data) {
            renderDataTable(data.data, data.columns);
        }
    } catch (err) {
        showToast("Failed to load data", "error");
    }
}

// ============================================================
// COMMAND INPUT (Stata-style)
// ============================================================
function initCommandInput() {
    const input = document.getElementById("command-input");
    if (!input) return;

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            executeCommand(input.value);
            input.value = "";
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            navigateHistory(-1, input);
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            navigateHistory(1, input);
        }
    });
}

function navigateHistory(direction, input) {
    if (State.commandHistory.length === 0) return;
    State.historyIndex += direction;
    if (State.historyIndex < 0) State.historyIndex = 0;
    if (State.historyIndex >= State.commandHistory.length) {
        State.historyIndex = State.commandHistory.length;
        input.value = "";
        return;
    }
    input.value = State.commandHistory[State.historyIndex];
}

async function executeCommand(cmd) {
    cmd = cmd.trim();
    if (!cmd) return;

    State.commandHistory.push(cmd);
    State.historyIndex = State.commandHistory.length;

    appendOutput("command", cmd, "Running...");
    switchTab("output");

    try {
        const resp = await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: cmd }),
        });
        const data = await resp.json();

        if (data.error) {
            updateLastOutput(cmd, data.error, "error");
        } else {
            updateLastOutput(cmd, data.result?.output || JSON.stringify(data.result, null, 2));
        }
    } catch (err) {
        updateLastOutput(cmd, `Error: ${err.message}`, "error");
    }
}

// ============================================================
// OUTPUT PANEL
// ============================================================
function appendOutput(type, cmd, text) {
    const area = document.getElementById("output-area");
    const block = document.createElement("div");
    block.className = "output-block";
    block.id = `output-${Date.now()}`;

    if (type === "command" || type === "use") {
        block.innerHTML = `<div class="output-command">${escapeHtml(cmd)}</div>
            <div class="output-result" id="result-${block.id}">${escapeHtml(text || "")}</div>`;
    } else {
        block.innerHTML = `<div class="output-result">${escapeHtml(text || "")}</div>`;
    }

    area.appendChild(block);
    area.scrollTop = area.scrollHeight;
    return block.id;
}

function updateLastOutput(cmd, text, type = "result") {
    const area = document.getElementById("output-area");
    const blocks = area.querySelectorAll(".output-block");
    if (blocks.length === 0) return;

    const last = blocks[blocks.length - 1];
    const resultDiv = last.querySelector(".output-result");
    if (resultDiv) {
        resultDiv.className = `output-${type === "error" ? "error" : "result"}`;
        resultDiv.textContent = text;
    }
    area.scrollTop = area.scrollHeight;
}

function clearOutput() {
    document.getElementById("output-area").innerHTML = "";
}

// ============================================================
// STATISTICAL TEST DIALOGS
// ============================================================
function openModal(id) {
    document.getElementById(id).classList.add("active");
    populateVarSelectors();
}

function closeModal(id) {
    document.getElementById(id).classList.remove("active");
}

function populateVarSelectors() {
    document.querySelectorAll(".var-selector").forEach(select => {
        const current = select.value;
        const type = select.dataset.type; // "numeric", "categorical", "any"
        let vars = State.columns;

        if (type === "numeric" && State.dataInfo) {
            vars = State.dataInfo.numeric_columns || State.columns;
        } else if (type === "categorical" && State.dataInfo) {
            vars = State.dataInfo.categorical_columns || State.columns;
        }

        select.innerHTML = '<option value="">-- Select Variable --</option>';
        vars.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            if (v === current) opt.selected = true;
            select.appendChild(opt);
        });
    });

    // Multi-selects
    document.querySelectorAll(".var-multi-selector").forEach(select => {
        const type = select.dataset.type;
        let vars = State.columns;
        if (type === "numeric" && State.dataInfo) {
            vars = State.dataInfo.numeric_columns || State.columns;
        }
        select.innerHTML = "";
        vars.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            select.appendChild(opt);
        });
    });
}

// ---- Run Tests ----

async function runDescriptive() {
    const vars = getMultiSelectValues("desc-vars");
    const detail = document.getElementById("desc-detail")?.checked || true;
    closeModal("modal-descriptive");

    await apiPost("/api/stats/descriptive", { variables: vars.length ? vars : null, detail },
        `summarize ${vars.join(" ")}`);
}

async function runTTest() {
    const testType = document.getElementById("ttest-type").value;
    let payload = { type: testType };

    if (testType === "two_sample") {
        payload.variable = document.getElementById("ttest-var").value;
        payload.groupvar = document.getElementById("ttest-group").value;
    } else if (testType === "one_sample") {
        payload.variable = document.getElementById("ttest-var").value;
        payload.mu = parseFloat(document.getElementById("ttest-mu").value) || 0;
    } else if (testType === "paired") {
        payload.var1 = document.getElementById("ttest-var1").value;
        payload.var2 = document.getElementById("ttest-var2").value;
    }

    closeModal("modal-ttest");
    await apiPost("/api/stats/ttest", payload, `ttest`);
}

async function runANOVA() {
    const anovaType = document.getElementById("anova-type").value;
    let payload = { type: anovaType };

    if (anovaType === "oneway") {
        payload.depvar = document.getElementById("anova-depvar").value;
        payload.groupvar = document.getElementById("anova-groupvar").value;
    } else {
        payload.depvar = document.getElementById("anova-depvar").value;
        payload.factor1 = document.getElementById("anova-factor1").value;
        payload.factor2 = document.getElementById("anova-factor2").value;
        payload.interaction = document.getElementById("anova-interaction")?.checked ?? true;
    }

    closeModal("modal-anova");
    await apiPost("/api/stats/anova", payload, `oneway/anova`);
}

async function runChiSquare() {
    const var1 = document.getElementById("chi-var1").value;
    const var2 = document.getElementById("chi-var2").value;
    closeModal("modal-chi");
    await apiPost("/api/stats/chi_square", { var1, var2 }, `tabulate ${var1} ${var2}, chi2`);
}

async function runRegression() {
    const regType = document.getElementById("reg-type").value;
    const depvar = document.getElementById("reg-depvar").value;
    const indepvars = getMultiSelectValues("reg-indepvars");
    const robust = document.getElementById("reg-robust")?.checked || false;

    closeModal("modal-regression");
    await apiPost("/api/stats/regression",
        { type: regType, depvar, indepvars, robust },
        `${regType === "ols" ? "regress" : regType} ${depvar} ${indepvars.join(" ")}`);
}

async function runCorrelation() {
    const variables = getMultiSelectValues("corr-vars");
    const method = document.getElementById("corr-method").value;
    closeModal("modal-correlation");
    await apiPost("/api/stats/correlation", { variables, method }, `correlate ${variables.join(" ")}`);
}

async function runNonParametric() {
    const test = document.getElementById("np-test").value;
    let payload = { test };

    if (test === "mann_whitney" || test === "kruskal_wallis") {
        payload.variable = document.getElementById("np-var").value;
        payload.groupvar = document.getElementById("np-group").value;
    } else if (test === "wilcoxon") {
        payload.var1 = document.getElementById("np-var1").value;
        payload.var2 = document.getElementById("np-var2").value;
    }

    closeModal("modal-nonparametric");
    await apiPost("/api/stats/nonparametric", payload, `${test}`);
}

async function runSurvival() {
    const sType = document.getElementById("surv-type").value;
    let payload = {
        type: sType,
        time_var: document.getElementById("surv-time").value,
        event_var: document.getElementById("surv-event").value,
    };

    if (sType === "cox") {
        payload.covariates = getMultiSelectValues("surv-covariates");
    } else {
        const gv = document.getElementById("surv-group").value;
        if (gv) payload.group_var = gv;
    }

    closeModal("modal-survival");
    await apiPost("/api/stats/survival", payload, `sts/stcox`);
}

async function runPower() {
    const testType = document.getElementById("power-test").value;
    let payload = { test_type: testType };

    const fields = ["n", "delta", "sd", "alpha", "power", "k", "f_effect", "w", "df"];
    fields.forEach(f => {
        const el = document.getElementById(`power-${f}`);
        if (el && el.value) payload[f] = parseFloat(el.value);
    });

    closeModal("modal-power");
    await apiPost("/api/stats/power", payload, `power ${testType}`);
}

async function runSampleSize() {
    const payload = {
        test_type: document.getElementById("ss-test").value,
        study_type: document.getElementById("ss-study").value,
        effect_size: parseFloat(document.getElementById("ss-effect").value) || null,
        sd: parseFloat(document.getElementById("ss-sd").value) || null,
        alpha: parseFloat(document.getElementById("ss-alpha").value) || 0.05,
        power: parseFloat(document.getElementById("ss-power").value) || 0.80,
        p1: parseFloat(document.getElementById("ss-p1").value) || null,
        p2: parseFloat(document.getElementById("ss-p2").value) || null,
        k_groups: parseInt(document.getElementById("ss-groups").value) || 2,
    };

    closeModal("modal-samplesize");
    await apiPost("/api/stats/sample_size", payload, `power sample_size`);
}

// ---- API helper ----
async function apiPost(url, payload, cmdLabel) {
    switchTab("output");
    appendOutput("command", cmdLabel, "Computing...");

    try {
        const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (data.error) {
            updateLastOutput(cmdLabel, data.error, "error");
            showToast(data.error, "error");
        } else {
            const result = data.result;
            let output = "";
            if (typeof result === "string") {
                output = result;
            } else if (result?.output) {
                output = result.output;
            } else if (result?.result_str) {
                output = result.result_str;
            } else if (result?.summary) {
                output = result.summary;
            } else if (result?.stdout) {
                output = result.stdout;
            } else {
                output = formatResult(result);
            }
            updateLastOutput(cmdLabel, output);
        }
    } catch (err) {
        updateLastOutput(cmdLabel, `Error: ${err.message}`, "error");
    }
}

function formatResult(obj) {
    if (obj === null || obj === undefined) return "No result";
    if (typeof obj === "string") return obj;
    try {
        return JSON.stringify(obj, null, 2);
    } catch {
        return String(obj);
    }
}

function getMultiSelectValues(id) {
    const select = document.getElementById(id);
    if (!select) return [];
    return Array.from(select.selectedOptions).map(o => o.value);
}

// ============================================================
// AI CHAT
// ============================================================
function initAIChat() {
    const input = document.getElementById("ai-input");
    if (!input) return;

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendAIMessage();
        }
    });
}

async function sendAIMessage() {
    const input = document.getElementById("ai-input");
    const msg = input.value.trim();
    if (!msg) return;

    input.value = "";
    addAIMessage("user", msg);

    const sendBtn = document.getElementById("ai-send-btn");
    sendBtn.disabled = true;
    addAIMessage("system", "Analyzing...");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000);  // 5 minutes

    try {
        const resp = await fetch("/api/ai/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: msg, research: true }),
            signal: controller.signal,
        });
        clearTimeout(timeoutId);
        const data = await resp.json();

        // Remove "Analyzing..." message
        removeLastAIMessage();

        if (data.error) {
            addAIMessage("assistant", `Error: ${data.error}`);
        } else {
            const result = data.result;
            let response = "";

            if (result?.stdout) {
                response = result.stdout;
                // Also show in output tab
                appendOutput("command", `ai analyze "${msg.substring(0, 50)}"`, result.stdout);
            }

            if (result?.suggestions) {
                response += "\n\nSuggested Tests:\n";
                result.suggestions.forEach(s => {
                    response += `  - ${s.test}: ${s.reason}\n`;
                });
            }

            if (result?.research && result.research.length > 0) {
                response += "\n\nRelevant Literature:\n";
                result.research.forEach(r => {
                    if (!r.error) {
                        response += `  - ${r.title || "N/A"} (${r.year || "N/A"})\n`;
                    }
                });
            }

            addAIMessage("assistant", response || "Analysis complete. Check the Output tab for results.");
        }
    } catch (err) {
        clearTimeout(timeoutId);
        removeLastAIMessage();
        if (err.name === "AbortError") {
            addAIMessage("assistant", "Request timed out. Make sure Ollama is installed and running (ollama serve). You can still use the statistical test buttons directly without AI.");
        } else {
            addAIMessage("assistant", `Error: ${err.message}. Make sure Ollama is running.`);
        }
    }

    sendBtn.disabled = false;
}

function addAIMessage(role, text) {
    const chat = document.getElementById("ai-chat-area");
    const msg = document.createElement("div");
    msg.className = `ai-message ${role}`;
    msg.textContent = text;
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
}

function removeLastAIMessage() {
    const chat = document.getElementById("ai-chat-area");
    const msgs = chat.querySelectorAll(".ai-message");
    if (msgs.length > 0) {
        msgs[msgs.length - 1].remove();
    }
}

async function runAIAnalysis() {
    const proposal = document.getElementById("ai-proposal")?.value || "";
    if (!State.dataLoaded) {
        showToast("Please load data first", "error");
        return;
    }

    switchTab("output");
    appendOutput("command", "ai analyze", "Running full AI analysis (this may take up to 5 minutes)...");
    setStatus("loading", "AI analysis running...");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000);  // 5 minutes

    try {
        const resp = await fetch("/api/ai/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ proposal, research: true }),
            signal: controller.signal,
        });
        clearTimeout(timeoutId);
        const data = await resp.json();

        if (data.error) {
            updateLastOutput("ai analyze", data.error, "error");
            setStatus("error", "AI analysis failed");
        } else {
            updateLastOutput("ai analyze", data.result?.stdout || "Complete. See results.");
            setStatus("ok", "AI analysis complete");
        }
    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === "AbortError") {
            updateLastOutput("ai analyze", "Error: AI analysis timed out. The Ollama model may not be running.\n\nTo fix this:\n  1. Install Ollama: https://ollama.com\n  2. Run: ollama pull llama3.2\n  3. Make sure Ollama is running, then try again.\n\nAlternatively, use the individual statistical test buttons (Describe, T-Test, ANOVA, etc.) which work without AI.", "error");
        } else {
            updateLastOutput("ai analyze", `Error: ${err.message}\n\nMake sure Ollama is installed and running (ollama serve).\nThe AI features require a local Ollama instance with llama3.2.`, "error");
        }
        setStatus("error", "AI analysis failed");
    }
}

// ============================================================
// RIGHT PANEL
// ============================================================
function initRightPanel() {
    document.querySelectorAll(".right-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".right-tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".right-content").forEach(c => c.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById(tab.dataset.panel).classList.add("active");
        });
    });
}

function updateProperties(data) {
    const panel = document.getElementById("properties-content");
    if (!panel || !data) return;

    let html = '<div class="prop-section">';
    html += '<div class="prop-section-title">Dataset Info</div>';
    html += `<div class="prop-row"><span class="prop-label">File</span><span class="prop-value">${data.filename || "N/A"}</span></div>`;
    html += `<div class="prop-row"><span class="prop-label">Observations</span><span class="prop-value">${data.shape?.[0] || 0}</span></div>`;
    html += `<div class="prop-row"><span class="prop-label">Variables</span><span class="prop-value">${data.shape?.[1] || 0}</span></div>`;
    html += '</div>';

    if (data.data_info) {
        const di = data.data_info;
        html += '<div class="prop-section">';
        html += '<div class="prop-section-title">Variable Types</div>';
        html += `<div class="prop-row"><span class="prop-label">Numeric</span><span class="prop-value">${di.numeric_columns?.length || 0}</span></div>`;
        html += `<div class="prop-row"><span class="prop-label">Categorical</span><span class="prop-value">${di.categorical_columns?.length || 0}</span></div>`;
        html += `<div class="prop-row"><span class="prop-label">Group vars</span><span class="prop-value">${di.group_candidates?.length || 0}</span></div>`;
        html += '</div>';

        if (di.group_candidates?.length > 0) {
            html += '<div class="prop-section">';
            html += '<div class="prop-section-title">Group Variables</div>';
            di.group_candidates.forEach(gc => {
                html += `<div class="prop-row"><span class="prop-label">${gc.column}</span><span class="prop-value">${gc.n_groups} groups</span></div>`;
            });
            html += '</div>';
        }

        // Missing data
        const missing = di.missing_summary || {};
        const totalMissing = Object.values(missing).reduce((a, b) => a + b, 0);
        if (totalMissing > 0) {
            html += '<div class="prop-section">';
            html += '<div class="prop-section-title">Missing Data</div>';
            Object.entries(missing).forEach(([col, n]) => {
                if (n > 0) {
                    html += `<div class="prop-row"><span class="prop-label">${col}</span><span class="prop-value" style="color:var(--accent-yellow)">${n}</span></div>`;
                }
            });
            html += '</div>';
        }
    }

    panel.innerHTML = html;
}

// ============================================================
// STATUS BAR
// ============================================================
function setStatus(type, text) {
    const dot = document.getElementById("status-dot");
    const msg = document.getElementById("status-message");
    if (dot) {
        dot.className = "status-dot";
        if (type === "error") dot.classList.add("error");
        else if (type === "loading" || type === "warning") dot.classList.add("warning");
    }
    if (msg) msg.textContent = text;
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
function showToast(message, type = "info") {
    const existing = document.querySelectorAll(".toast");
    existing.forEach(t => t.remove());

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 4000);
}

// ============================================================
// KEYBOARD SHORTCUTS
// ============================================================
function initKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
        // Ctrl+O: Open file
        if (e.ctrlKey && e.key === "o") {
            e.preventDefault();
            openFile();
        }
        // Ctrl+1-5: Switch tabs
        if (e.ctrlKey && e.key >= "1" && e.key <= "5") {
            e.preventDefault();
            const tabs = ["welcome", "data", "output", "analysis"];
            const idx = parseInt(e.key) - 1;
            if (tabs[idx]) switchTab(tabs[idx]);
        }
        // F5: Run AI analysis
        if (e.key === "F5") {
            e.preventDefault();
            runAIAnalysis();
        }
        // Ctrl+L: Focus command input
        if (e.ctrlKey && e.key === "l") {
            e.preventDefault();
            document.getElementById("command-input")?.focus();
        }
    });
}

// ============================================================
// UTILITIES
// ============================================================
function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// Close modals on outside click
document.addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-overlay")) {
        e.target.classList.remove("active");
    }
});

// ============================================================
// SMART STATISTICAL ROUTER
// ============================================================
async function runSmartAnalyze() {
    const vars = getMultiSelectValues("smart-vars");
    const subjectVar = document.getElementById("smart-subject")?.value || null;
    const alpha = parseFloat(document.getElementById("smart-alpha")?.value) || 0.05;

    if (vars.length === 0) {
        showToast("Select at least one variable", "error");
        return;
    }

    closeModal("modal-smart-analyze");
    switchTab("output");
    appendOutput("command", `smart analyze ${vars.join(" ")}`, ">>> Analyzing data structure and selecting test...");

    try {
        const resp = await fetch("/api/stats/smart_analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                columns: vars,
                subject_var: subjectVar,
                alpha: alpha
            }),
        });
        const data = await resp.json();

        if (data.error) {
            updateLastOutput(`smart analyze`, data.error, "error");
            return;
        }

        const result = data.result;
        let output = "=" .repeat(60) + "\n";
        output += "  SMART STATISTICAL ROUTER RESULTS\n";
        output += "=" .repeat(60) + "\n\n";

        // Selected test
        output += `>>> Selected Test: ${result.selected_test || "Unknown"}\n\n`;

        // Reasoning
        if (result.reasoning) {
            output += "--- Decision Reasoning ---\n";
            output += result.reasoning + "\n\n";
        }

        // Variable types
        if (result.variable_types) {
            output += "--- Variable Classification ---\n";
            Object.entries(result.variable_types).forEach(([v, t]) => {
                output += `  ${v}: ${t}\n`;
            });
            output += "\n";
        }

        // Test result
        if (result.result) {
            output += "--- Test Results ---\n";
            if (typeof result.result === "string") {
                output += result.result;
            } else if (result.result.output) {
                output += result.result.output;
            } else {
                output += JSON.stringify(result.result, null, 2);
            }
            output += "\n\n";
        }

        // Post-hoc (if any)
        if (result.posthoc) {
            output += "--- Post-Hoc Analysis (auto-triggered) ---\n";
            output += result.posthoc_note + "\n";
            if (result.posthoc.comparisons) {
                result.posthoc.comparisons.forEach(c => {
                    output += `  ${c.Group1} vs ${c.Group2}: `;
                    output += `diff=${c.Mean_Diff}, p=${c.p_adj || c.p_bonferroni}`;
                    output += c.Significant === true || c.Reject_H0 === "True" ? " *\n" : "\n";
                });
            }
            output += "\n";
        }

        // Normality (if any)
        if (result.normality) {
            output += "--- Normality Test ---\n";
            output += `  Normal: ${result.normality.is_normal ? "Yes" : "No"}\n`;
            output += `  Shapiro-Wilk p: ${result.normality.p_value}\n\n`;
        }

        output += "=" .repeat(60) + "\n";
        output += "  END OF SMART ANALYSIS\n";
        output += "=" .repeat(60);

        updateLastOutput(`smart analyze ${vars.join(" ")}`, output);
        showToast(`Analysis complete: ${result.selected_test}`, "success");

    } catch (err) {
        updateLastOutput(`smart analyze`, `Error: ${err.message}`, "error");
    }
}

// ============================================================
// SAMPLE SIZE FROM TEXT
// ============================================================
async function runSampleSizeFromText() {
    const text = document.getElementById("ss-text")?.value || "";
    const alpha = parseFloat(document.getElementById("ss-text-alpha")?.value) || 0.05;
    const power = parseFloat(document.getElementById("ss-text-power")?.value) || 0.80;

    if (!text.trim()) {
        showToast("Paste text with Mean/SD values", "error");
        return;
    }

    closeModal("modal-samplesize-text");
    switchTab("output");
    appendOutput("command", "sample size from text", ">>> Parsing Mean/SD values from text...");

    try {
        const resp = await fetch("/api/ai/sample_size_from_text", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, alpha, power }),
        });
        const data = await resp.json();

        if (data.error || data.result?.error) {
            updateLastOutput("sample size from text", data.error || data.result.error, "error");
            return;
        }

        const result = data.result;
        let output = "=" .repeat(60) + "\n";
        output += "  SAMPLE SIZE CALCULATION (from text)\n";
        output += "=" .repeat(60) + "\n\n";

        // Extracted values
        if (result.group1 && result.group2) {
            output += "--- Extracted Values ---\n";
            output += `  Group 1 (${result.group1.name}):\n`;
            output += `    Mean = ${result.group1.mean}, SD = ${result.group1.sd}\n`;
            output += `    Source: "${result.group1.source}"\n\n`;
            output += `  Group 2 (${result.group2.name}):\n`;
            output += `    Mean = ${result.group2.mean}, SD = ${result.group2.sd}\n`;
            output += `    Source: "${result.group2.source}"\n\n`;
        }

        // Effect size
        if (result.effect_size) {
            output += "--- Effect Size ---\n";
            output += `  Cohen's d = ${result.effect_size.cohens_d}\n`;
            output += `  Interpretation: ${result.effect_size.interpretation}\n\n`;
        }

        // Calculation
        if (result.calculation) {
            const calc = result.calculation;
            output += "--- Sample Size Calculation ---\n";
            output += `  Mean difference (delta) = ${calc.mean_difference}\n`;
            output += `  Pooled SD = ${calc.pooled_sd}\n`;
            output += `  Alpha = ${calc.alpha}, Power = ${calc.power}\n`;
            output += `  Z_alpha/2 = ${calc.z_alpha}, Z_beta = ${calc.z_beta}\n\n`;
            output += `  >>> Required N per group = ${calc.n_per_group}\n`;
            output += `  >>> Total N = ${calc.total_n}\n\n`;
            output += `  Formula: ${calc.formula}\n`;
        }

        // All extracted values
        if (result.all_extracted && result.all_extracted.length > 2) {
            output += "\n--- All Extracted Values ---\n";
            result.all_extracted.forEach((v, i) => {
                output += `  [${i+1}] ${v.group}: Mean=${v.mean}, SD=${v.sd}\n`;
            });
        }

        output += "\n" + "=" .repeat(60);

        updateLastOutput("sample size from text", output);
        showToast("Sample size calculated", "success");

    } catch (err) {
        updateLastOutput("sample size from text", `Error: ${err.message}`, "error");
    }
}

// ============================================================
// PROPOSAL UPLOAD (RAG CONTEXT)
// ============================================================
async function uploadProposal() {
    const text = document.getElementById("proposal-text")?.value || "";

    if (!text.trim()) {
        showToast("Paste your research proposal text", "error");
        return;
    }

    closeModal("modal-proposal-upload");
    showToast("Storing proposal context...");

    try {
        const resp = await fetch("/api/ai/proposal", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        const data = await resp.json();

        if (data.error) {
            showToast(data.error, "error");
            return;
        }

        const result = data.result;
        let msg = `Proposal stored (${result.text_length} chars)`;
        if (result.variables_detected?.length > 0) {
            msg += `, ${result.variables_detected.length} variables detected`;
        }
        if (result.citations_found > 0) {
            msg += `, ${result.citations_found} citations found`;
        }

        showToast(msg, "success");

        // Also show in output
        switchTab("output");
        let output = ">>> Research Proposal Context Stored\n";
        output += `  Text length: ${result.text_length} characters\n`;
        output += `  Variables detected: ${result.variables_detected?.join(", ") || "None"}\n`;
        output += `  Citations found: ${result.citations_found}\n`;
        output += `  Methodology extracted: ${result.methodology_extracted ? "Yes" : "No"}\n`;
        output += "\n>>> The AI will use this context for future analyses.";
        appendOutput("command", "ai proposal upload", output);

    } catch (err) {
        showToast(`Error: ${err.message}`, "error");
    }
}

async function checkProposalReferences() {
    const text = document.getElementById("proposal-text")?.value || "";

    if (!text.trim()) {
        showToast("Paste your proposal text first", "error");
        return;
    }

    showToast("Analyzing references...");

    try {
        const resp = await fetch("/api/ai/check_references", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        const data = await resp.json();

        if (data.error) {
            showToast(data.error, "error");
            return;
        }

        const result = data.result;
        closeModal("modal-proposal-upload");
        switchTab("output");

        let output = "=" .repeat(60) + "\n";
        output += "  REFERENCE ANALYSIS\n";
        output += "=" .repeat(60) + "\n\n";
        output += `Total citations found: ${result.total_citations}\n\n`;

        if (result.citations_list?.length > 0) {
            output += "--- Citations Found ---\n";
            result.citations_list.forEach((c, i) => {
                output += `  [${i+1}] ${c}\n`;
            });
            output += "\n";
        }

        if (result.quality_indicators) {
            const qi = result.quality_indicators;
            output += "--- Quality Indicators ---\n";
            output += `  Average publication year: ${qi.average_year}\n`;
            output += `  Oldest reference: ${qi.oldest_reference}\n`;
            output += `  Newest reference: ${qi.newest_reference}\n`;
            output += `  Years span: ${qi.years_span}\n\n`;
        }

        if (result.suggestions?.length > 0) {
            output += "--- Suggestions ---\n";
            result.suggestions.forEach(s => {
                output += `  >>> ${s}\n`;
            });
        }

        output += "\n" + "=" .repeat(60);
        appendOutput("command", "check references", output);
        showToast("Reference analysis complete", "success");

    } catch (err) {
        showToast(`Error: ${err.message}`, "error");
    }
}

// ============================================================
// AGENT CORE: MODEL MANAGEMENT
// ============================================================
async function loadAvailableModels() {
    try {
        const resp = await fetch("/api/agent/models");
        const data = await resp.json();

        const select = document.getElementById("model-select");
        const status = document.getElementById("ollama-status");

        if (select && data.models) {
            select.innerHTML = "";
            data.models.forEach(model => {
                const opt = document.createElement("option");
                opt.value = model;
                opt.textContent = model;
                if (model === data.current) opt.selected = true;
                select.appendChild(opt);
            });
        }

        if (status) {
            if (data.ollama_running) {
                status.style.background = "var(--accent-green)";
                status.title = "Ollama running";
            } else {
                status.style.background = "var(--accent-red)";
                status.title = "Ollama not running";
            }
        }
    } catch (err) {
        const status = document.getElementById("ollama-status");
        if (status) {
            status.style.background = "var(--accent-red)";
            status.title = "Cannot connect to Ollama";
        }
    }
}

async function changeModel(modelName) {
    try {
        await fetch("/api/agent/models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: modelName }),
        });
        showToast(`Model changed to ${modelName}`, "success");
    } catch (err) {
        showToast(`Failed to change model: ${err.message}`, "error");
    }
}

// ============================================================
// AGENT: MESSY DATA ANALYSIS
// ============================================================
async function runMessyDataAnalysis() {
    const rawText = document.getElementById("messy-data-text")?.value || "";
    const context = document.getElementById("messy-data-context")?.value || "";

    if (!rawText.trim()) {
        showToast("Paste your messy data first", "error");
        return;
    }

    closeModal("modal-messy-data");
    switchTab("output");
    appendOutput("command", "agent messy_data", ">>> Analyzing messy data (AI cleaning + Python ANOVA)...");
    setStatus("loading", "Agent analyzing data...");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000); // 3 minutes

    try {
        const resp = await fetch("/api/agent/messy_data", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ raw_text: rawText, context }),
            signal: controller.signal,
        });
        clearTimeout(timeoutId);
        const data = await resp.json();

        if (data.error || data.result?.error) {
            updateLastOutput("agent messy_data", data.error || data.result.error, "error");
            setStatus("error", "Analysis failed");
            return;
        }

        const result = data.result;
        let output = "=" .repeat(60) + "\n";
        output += "  MESSY DATA ANALYSIS RESULTS\n";
        output += "=" .repeat(60) + "\n\n";

        // Structured Data
        if (result.structured_data) {
            output += "--- Extracted Structure ---\n";
            output += `  Groups: ${result.structured_data.groups?.join(", ") || "N/A"}\n`;
            output += `  Time Points: ${result.structured_data.timepoints?.join(", ") || "N/A"}\n\n`;
        }

        // Statistics
        if (result.statistics) {
            output += "--- ANOVA Results (Python scipy) ---\n";
            const stats = result.statistics;

            if (stats.anova_results) {
                Object.entries(stats.anova_results).forEach(([tp, res]) => {
                    output += `\n  [${tp}]\n`;
                    output += `    F-statistic: ${res.F_statistic}\n`;
                    output += `    p-value: ${res.p_value}`;
                    output += res.significant ? " ***\n" : "\n";
                });
            }

            if (stats.descriptive_stats) {
                output += "\n--- Descriptive Statistics ---\n";
                Object.entries(stats.descriptive_stats).forEach(([tp, groups]) => {
                    output += `\n  [${tp}]\n`;
                    Object.entries(groups).forEach(([group, ds]) => {
                        output += `    ${group}: Mean=${ds.mean}, SD=${ds.std}, N=${ds.n}\n`;
                    });
                });
            }

            if (stats.posthoc_results && Object.keys(stats.posthoc_results).length > 0) {
                output += "\n--- Post-Hoc Tukey HSD ---\n";
                Object.entries(stats.posthoc_results).forEach(([tp, comparisons]) => {
                    output += `\n  [${tp}]\n`;
                    if (Array.isArray(comparisons)) {
                        comparisons.forEach(c => {
                            output += `    ${c.group1} vs ${c.group2}: diff=${c.mean_diff}, p=${c.p_adj}`;
                            output += c.significant ? " *\n" : "\n";
                        });
                    }
                });
            }
        }

        // Interpretation
        if (result.interpretation) {
            output += "\n--- AI Interpretation ---\n";
            output += result.interpretation + "\n";
        }

        output += "\n" + "=" .repeat(60);
        updateLastOutput("agent messy_data", output);
        setStatus("ok", "Analysis complete");
        showToast("Messy data analysis complete", "success");

    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === "AbortError") {
            updateLastOutput("agent messy_data", "Error: Analysis timed out. Make sure Ollama is running.", "error");
        } else {
            updateLastOutput("agent messy_data", `Error: ${err.message}`, "error");
        }
        setStatus("error", "Analysis failed");
    }
}

// ============================================================
// AGENT: DUAL-MODE SAMPLE SIZE CALCULATOR
// ============================================================
let sampleSizeMode = "ai";

function switchSampleSizeMode(mode) {
    sampleSizeMode = mode;
    const aiBtn = document.getElementById("ss-dual-ai-btn");
    const manualBtn = document.getElementById("ss-dual-manual-btn");
    const aiMode = document.getElementById("ss-dual-ai-mode");
    const manualMode = document.getElementById("ss-dual-manual-mode");

    if (mode === "ai") {
        aiBtn.className = "btn btn-primary";
        manualBtn.className = "btn btn-secondary";
        aiMode.style.display = "";
        manualMode.style.display = "none";
    } else {
        aiBtn.className = "btn btn-secondary";
        manualBtn.className = "btn btn-primary";
        aiMode.style.display = "none";
        manualMode.style.display = "";
    }
}

async function runDualSampleSize() {
    closeModal("modal-sample-size-dual");
    switchTab("output");

    if (sampleSizeMode === "ai") {
        const topic = document.getElementById("ss-dual-topic")?.value || "";
        if (!topic.trim()) {
            showToast("Enter a research topic", "error");
            return;
        }

        appendOutput("command", `agent sample_size_auto "${topic.substring(0, 40)}..."`, ">>> Searching for similar studies and extracting effect size...");
        setStatus("loading", "Agent searching literature...");

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 180000);

        try {
            const resp = await fetch("/api/agent/sample_size_auto", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic }),
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            const data = await resp.json();

            if (data.error || data.result?.error) {
                updateLastOutput("agent sample_size_auto", data.error || data.result.error, "error");
                setStatus("error", "Search failed");
                return;
            }

            const result = data.result;
            let output = "=" .repeat(60) + "\n";
            output += "  AI-POWERED SAMPLE SIZE CALCULATION\n";
            output += "=" .repeat(60) + "\n\n";
            output += `Topic: ${topic}\n\n`;

            // Search results
            if (result.search_results?.length > 0) {
                output += "--- Literature Search Results ---\n";
                result.search_results.slice(0, 5).forEach((r, i) => {
                    if (!r.error) {
                        output += `  [${i+1}] ${r.title || "N/A"}\n`;
                        output += `      ${r.body?.substring(0, 100) || ""}...\n`;
                    }
                });
                output += "\n";
            }

            // Extracted data
            if (result.extracted_data?.studies_found?.length > 0) {
                output += "--- Extracted Mean/SD Data ---\n";
                result.extracted_data.studies_found.forEach((s, i) => {
                    output += `  Study ${i+1}: ${s.title || "N/A"}\n`;
                    if (s.control_mean !== undefined) {
                        output += `    Control: Mean=${s.control_mean}, SD=${s.control_sd}\n`;
                    }
                    if (s.treatment_mean !== undefined) {
                        output += `    Treatment: Mean=${s.treatment_mean}, SD=${s.treatment_sd}\n`;
                    }
                });
                output += "\n";
            }

            // Sample size calculation
            if (result.sample_size) {
                const ss = result.sample_size;
                output += "--- Sample Size Calculation ---\n";
                output += `  Effect Size (Cohen's d): ${ss.effect_size} (${ss.interpretation})\n`;
                output += `  Alpha: ${ss.alpha}, Power: ${ss.power}\n`;
                output += `  Source: ${ss.source_study}\n\n`;
                output += `  >>> REQUIRED N PER GROUP: ${ss.n_per_group}\n`;
                output += `  >>> TOTAL N: ${ss.total_n}\n`;
            }

            output += "\n" + "=" .repeat(60);
            updateLastOutput("agent sample_size_auto", output);
            setStatus("ok", "Calculation complete");
            showToast("Sample size calculated", "success");

        } catch (err) {
            clearTimeout(timeoutId);
            if (err.name === "AbortError") {
                updateLastOutput("agent sample_size_auto", "Error: Search timed out.", "error");
            } else {
                updateLastOutput("agent sample_size_auto", `Error: ${err.message}`, "error");
            }
            setStatus("error", "Calculation failed");
        }

    } else {
        // Manual mode
        const effectSize = parseFloat(document.getElementById("ss-dual-effect")?.value) || 0.5;
        const alpha = parseFloat(document.getElementById("ss-dual-alpha")?.value) || 0.05;
        const power = parseFloat(document.getElementById("ss-dual-power")?.value) || 0.80;
        const testType = document.getElementById("ss-dual-test")?.value || "t-test";

        appendOutput("command", "agent sample_size_manual", ">>> Calculating sample size...");

        try {
            const resp = await fetch("/api/agent/sample_size_manual", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ effect_size: effectSize, alpha, power, test_type: testType }),
            });
            const data = await resp.json();

            if (data.error || data.result?.error) {
                updateLastOutput("agent sample_size_manual", data.error || data.result.error, "error");
                return;
            }

            const result = data.result;
            let output = "=" .repeat(60) + "\n";
            output += "  MANUAL SAMPLE SIZE CALCULATION\n";
            output += "=" .repeat(60) + "\n\n";
            output += "--- Parameters ---\n";
            output += `  Test Type: ${result.test_type}\n`;
            output += `  Effect Size: ${result.effect_size} (${result.interpretation})\n`;
            output += `  Alpha: ${result.alpha}\n`;
            output += `  Power: ${result.power}\n\n`;
            output += `  >>> REQUIRED N PER GROUP: ${result.n_per_group}\n`;
            output += `  >>> TOTAL N: ${result.total_n}\n`;
            output += "\n" + "=" .repeat(60);

            updateLastOutput("agent sample_size_manual", output);
            showToast("Sample size calculated", "success");

        } catch (err) {
            updateLastOutput("agent sample_size_manual", `Error: ${err.message}`, "error");
        }
    }
}

// ============================================================
// UNIVERSAL STATISTICAL ANALYSIS AGENT (3-LAYER)
// ============================================================

let universalFileData = null;

function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add("drag-over");
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove("drag-over");
}

function handleFileDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove("drag-over");

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        processUniversalFile(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        processUniversalFile(files[0]);
    }
}

// Click handler for drop zone
document.addEventListener("DOMContentLoaded", () => {
    const dropZone = document.getElementById("universal-drop-zone");
    if (dropZone) {
        dropZone.addEventListener("click", () => {
            document.getElementById("universal-file-input").click();
        });
    }
});

function processUniversalFile(file) {
    const validTypes = [".csv", ".xlsx", ".xls"];
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();

    if (!validTypes.includes(ext)) {
        showToast("Please upload a CSV or Excel file", "error");
        return;
    }

    // For CSV, read as text directly
    if (ext === ".csv") {
        const reader = new FileReader();
        reader.onload = (e) => {
            document.getElementById("universal-data-text").value = e.target.result;
            universalFileData = null; // Using text mode
            showFileStatus(file.name);
        };
        reader.readAsText(file);
    } else {
        // For Excel, we'll send the file to the server
        universalFileData = file;
        showFileStatus(file.name);
        document.getElementById("universal-data-text").value = "";
        document.getElementById("universal-data-text").placeholder = `File loaded: ${file.name}\n\nData will be extracted from the Excel file.`;
    }
}

function showFileStatus(filename) {
    const status = document.getElementById("universal-file-status");
    const nameEl = document.getElementById("universal-file-name");
    if (status && nameEl) {
        nameEl.textContent = `File: ${filename}`;
        status.style.display = "block";
    }
}

function clearUniversalFile() {
    universalFileData = null;
    document.getElementById("universal-data-text").value = "";
    document.getElementById("universal-data-text").placeholder = `Paste data from Excel/CSV...

Example formats (AI will understand ANY layout):
Group A: 5.2, 5.4, 5.1, 5.3
Group B: 7.2, 7.0, 7.4, 7.1

OR

Control  Treatment1  Treatment2
5.2      6.1         7.2
5.4      6.3         7.0
5.1      5.9         7.4`;
    document.getElementById("universal-file-status").style.display = "none";
    document.getElementById("universal-file-input").value = "";
}

async function runUniversalAnalysis() {
    const rawText = document.getElementById("universal-data-text")?.value || "";
    const testType = document.getElementById("universal-test-type")?.value || "";
    const context = document.getElementById("universal-context")?.value || "";

    // Check if we have data
    if (!rawText.trim() && !universalFileData) {
        showToast("Paste data or upload a file first", "error");
        return;
    }

    closeModal("modal-universal-analyze");
    switchTab("output");
    appendOutput("command", "agent universal_analyze", ">>> Running 3-Layer Universal Analysis...\n    Layer 1: AI Adapter (extracting structure)\n    Layer 2: Python Math (ANOVA + Tukey)\n    Layer 3: AI Reporter (context-aware interpretation)");
    setStatus("loading", "Universal Agent analyzing data...");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minutes

    try {
        let resp;

        if (universalFileData) {
            // File upload mode
            const formData = new FormData();
            formData.append("file", universalFileData);
            formData.append("proposal_context", context);
            if (testType) formData.append("test_type", testType);

            resp = await fetch("/api/agent/universal_analyze_file", {
                method: "POST",
                body: formData,
                signal: controller.signal,
            });
        } else {
            // Text paste mode
            resp = await fetch("/api/agent/universal_analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    raw_text: rawText,
                    proposal_context: context,
                    test_type: testType || null
                }),
                signal: controller.signal,
            });
        }

        clearTimeout(timeoutId);
        const data = await resp.json();

        if (data.error || data.result?.error) {
            const errorMsg = data.error || data.result.error;
            let output = "=" .repeat(60) + "\n";
            output += "  ANALYSIS ERROR\n";
            output += "=" .repeat(60) + "\n\n";
            output += `Error: ${errorMsg}\n`;
            if (data.result?.layer) {
                output += `Failed at: Layer ${data.result.layer}\n`;
            }
            if (data.result?.details) {
                output += `Details: ${JSON.stringify(data.result.details)}\n`;
            }
            updateLastOutput("agent universal_analyze", output, "error");
            setStatus("error", "Analysis failed");
            return;
        }

        const result = data.result;
        let output = "=" .repeat(60) + "\n";
        output += "  UNIVERSAL STATISTICAL ANALYSIS RESULTS\n";
        output += "=" .repeat(60) + "\n\n";

        // Layer 1: Extraction
        if (result.layer1_extraction) {
            output += ">>> LAYER 1: AI ADAPTER (Structure Extraction)\n";
            output += "-" .repeat(40) + "\n";
            output += `  Groups found: ${result.layer1_extraction.groups_found.join(", ")}\n`;
            output += "  Samples per group:\n";
            Object.entries(result.layer1_extraction.samples_per_group).forEach(([g, n]) => {
                output += `    ${g}: n=${n}\n`;
            });
            output += "\n";
        }

        // Layer 2: Statistics
        if (result.layer2_statistics) {
            const stats = result.layer2_statistics;

            output += ">>> LAYER 2: PYTHON MATH ENGINE (Rigorous Statistics)\n";
            output += "-" .repeat(40) + "\n\n";

            // Descriptive stats
            if (stats.descriptive) {
                output += "  DESCRIPTIVE STATISTICS\n";
                output += "  " + "-".repeat(50) + "\n";
                output += "  Group".padEnd(20) + "N".padStart(6) + "Mean".padStart(10) + "SD".padStart(10) + "95% CI\n";
                output += "  " + "-".repeat(50) + "\n";
                Object.entries(stats.descriptive).forEach(([group, d]) => {
                    output += `  ${group.padEnd(18)} ${String(d.n).padStart(6)} ${d.mean.toFixed(3).padStart(10)} ${d.std.toFixed(3).padStart(10)} [${d.ci_95_lower.toFixed(2)}, ${d.ci_95_upper.toFixed(2)}]\n`;
                });
                output += "\n";
            }

            // ANOVA
            if (stats.anova) {
                output += "  ONE-WAY ANOVA\n";
                output += "  " + "-".repeat(35) + "\n";
                output += `  F-statistic: ${stats.anova.F_statistic}\n`;
                output += `  p-value: ${stats.anova.p_value}`;
                if (stats.anova.significant) {
                    output += " ***\n";
                    output += `  Result: SIGNIFICANT (p < ${stats.anova.alpha})\n`;
                } else {
                    output += "\n";
                    output += `  Result: Not significant (p >= ${stats.anova.alpha})\n`;
                }
                output += `  Groups: ${stats.anova.n_groups}, Total N: ${stats.anova.total_n}\n\n`;
            }

            // Post-hoc Tukey
            if (stats.posthoc && stats.posthoc.comparisons) {
                output += "  POST-HOC TUKEY HSD\n";
                output += "  " + "-".repeat(55) + "\n";
                output += "  Comparison".padEnd(30) + "Diff".padStart(10) + "p-adj".padStart(12) + "Sig\n";
                output += "  " + "-".repeat(55) + "\n";
                stats.posthoc.comparisons.forEach(c => {
                    const comp = `${c.group1} vs ${c.group2}`;
                    const sig = c.significant ? " ***" : "";
                    output += `  ${comp.padEnd(28)} ${c.mean_diff.toFixed(3).padStart(10)} ${c.p_adj.toFixed(6).padStart(12)}${sig}\n`;
                });
                output += "\n";
            }
        }

        // Layer 3: Interpretation
        if (result.layer3_interpretation) {
            output += ">>> LAYER 3: AI CONTEXT-AWARE REPORTER\n";
            output += "-" .repeat(40) + "\n\n";

            const interp = result.layer3_interpretation;
            if (interp.test_type) {
                output += `  Test Type: ${interp.test_type.detected_type || "Auto-detected"}\n`;
                output += `  Interpretation Mode: ${interp.test_type.interpretation}\n\n`;
            }

            if (interp.report) {
                output += "  ACADEMIC RESULTS PARAGRAPH:\n";
                output += "  " + "=".repeat(45) + "\n\n";
                // Word wrap the report
                const words = interp.report.split(" ");
                let line = "  ";
                words.forEach(word => {
                    if (line.length + word.length > 70) {
                        output += line + "\n";
                        line = "  " + word + " ";
                    } else {
                        line += word + " ";
                    }
                });
                output += line + "\n";
            }
        }

        output += "\n" + "=" .repeat(60) + "\n";
        output += "  END OF UNIVERSAL ANALYSIS\n";
        output += "=" .repeat(60);

        updateLastOutput("agent universal_analyze", output);
        setStatus("ok", "Universal analysis complete");
        showToast("Universal analysis complete", "success");

        // Clear the file data
        universalFileData = null;

    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === "AbortError") {
            updateLastOutput("agent universal_analyze", "Error: Analysis timed out. Make sure Ollama is running.", "error");
        } else {
            updateLastOutput("agent universal_analyze", `Error: ${err.message}`, "error");
        }
        setStatus("error", "Analysis failed");
    }
}

// ============================================================
// AGENT: LITERATURE REVIEW
// ============================================================
async function runLiteratureReview() {
    const topic = document.getElementById("lit-review-topic")?.value || "";
    const context = document.getElementById("lit-review-context")?.value || "";

    if (!topic.trim()) {
        showToast("Enter a research topic", "error");
        return;
    }

    closeModal("modal-lit-review");
    switchTab("output");
    appendOutput("command", `agent literature_review "${topic.substring(0, 40)}..."`, ">>> Searching literature and generating review...");
    setStatus("loading", "Agent generating literature review...");

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000);

    try {
        const resp = await fetch("/api/agent/literature_review", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic, context }),
            signal: controller.signal,
        });
        clearTimeout(timeoutId);
        const data = await resp.json();

        if (data.error || data.result?.error) {
            updateLastOutput("agent literature_review", data.error || data.result.error, "error");
            setStatus("error", "Generation failed");
            return;
        }

        const result = data.result;
        let output = "=" .repeat(60) + "\n";
        output += "  LITERATURE REVIEW\n";
        output += "=" .repeat(60) + "\n\n";
        output += `Topic: ${topic}\n`;
        output += `Sources searched: ${result.sources_searched || 0}\n\n`;

        // Review text
        if (result.review) {
            output += "--- Review ---\n\n";
            output += result.review + "\n\n";
        }

        // References
        if (result.references?.length > 0) {
            output += "--- References ---\n";
            result.references.forEach(ref => {
                output += `  [${ref.number}] ${ref.title}\n`;
                output += `      ${ref.url}\n`;
            });
        }

        output += "\n" + "=" .repeat(60);
        updateLastOutput("agent literature_review", output);
        setStatus("ok", "Review complete");
        showToast("Literature review generated", "success");

    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === "AbortError") {
            updateLastOutput("agent literature_review", "Error: Generation timed out.", "error");
        } else {
            updateLastOutput("agent literature_review", `Error: ${err.message}`, "error");
        }
        setStatus("error", "Generation failed");
    }
}
