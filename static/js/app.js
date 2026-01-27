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

    try {
        const resp = await fetch("/api/ai/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: msg, research: true }),
        });
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
        removeLastAIMessage();
        addAIMessage("assistant", `Error: ${err.message}`);
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
    appendOutput("command", "ai analyze", "Running full AI analysis...");

    try {
        const resp = await fetch("/api/ai/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ proposal, research: true }),
        });
        const data = await resp.json();

        if (data.error) {
            updateLastOutput("ai analyze", data.error, "error");
        } else {
            updateLastOutput("ai analyze", data.result?.stdout || "Complete. See results.");
        }
    } catch (err) {
        updateLastOutput("ai analyze", `Error: ${err.message}`, "error");
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
