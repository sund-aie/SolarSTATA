/* Analyze step: categorized analysis menu + inline forms + result cards.
 *
 * v3.0.2 fills in Descriptives (tabstat by group), Comparisons (oneway with
 * Bartlett + posthoc, two-way ANOVA, repeated-measures ANOVA), and a new
 * Diagnostics category (Shapiro-Wilk, Levene). The Regression and
 * Postestimation categories are unchanged from Phase 3.
 */

import { useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type {
  AnovaRmResponse,
  AnovaTwoResponse,
  CoefRow,
  ColumnInfo,
  LeveneResponse,
  LogitResponse,
  MarginsResponse,
  OnewayResponse,
  PredictResponse,
  RegressResponse,
  ShapiroResponse,
  TabstatResponse,
  TestResponse,
} from "../lib/types";
import { useApp } from "../state/store";
import { CommandPreview } from "../components/CommandPreview";
import { ResultsCard } from "../components/ResultsCard";
import { Tooltip } from "../components/Tooltip";

type Category = "descriptives" | "comparisons" | "diagnostics" | "regression" | "postest";

type RegressionPick = "ols" | "logit";
type ComparisonPick = "oneway" | "anova_two" | "anova_rm";
type DiagnosticPick = "shapiro" | "levene";

interface FactorState {
  name: string;
  // i. (categorical, drop reference) | c. (continuous) | none (default = c. for numeric, i. otherwise)
  mode: "auto" | "i" | "c";
}

const COMMAND_LABELS: Record<string, string> = {
  regress: "Linear regression",
  logit: "Logistic regression",
  margins: "Average marginal effects",
  predict: "Predicted values",
  test: "Wald test",
};

export function AnalyzeStep() {
  const dataset = useApp((s) => s.dataset);
  const columns = useApp((s) => s.columns);
  const records = useApp((s) => s.analyzeRecords);
  const lastEst = useApp((s) => s.lastEstimation);

  const [category, setCategory] = useState<Category>("regression");
  const [pick, setPick] = useState<RegressionPick>("ols");
  const [comparisonPick, setComparisonPick] = useState<ComparisonPick>("oneway");
  const [diagnosticPick, setDiagnosticPick] = useState<DiagnosticPick>("shapiro");

  if (!dataset) return null;

  return (
    <div className="overflow-y-auto px-10 py-8 pb-20">
      <div className="mb-8">
        <div className="eyebrow mb-2">Step 3 of 5</div>
        <h1 className="font-serif text-[32px] leading-[1.15] text-text tracking-[-0.01em] mb-1">
          Run an <em className="text-accent italic">analysis</em>
        </h1>
        <p className="text-text-muted text-[14px] max-w-[520px]">
          Pick a category, fill in the form, and see the result render below. Every
          action shows the equivalent Pro syntax — copy it to learn the command.
        </p>
      </div>

      <CategoryTabs current={category} onPick={setCategory} />

      <div className="mt-6 space-y-6">
        {category === "regression" && (
          <RegressionPicker pick={pick} setPick={setPick} columns={columns} />
        )}

        {category === "descriptives" && (
          <TabstatForm columns={columns} />
        )}

        {category === "comparisons" && (
          <ComparisonPicker pick={comparisonPick} setPick={setComparisonPick} columns={columns} />
        )}

        {category === "diagnostics" && (
          <DiagnosticPicker pick={diagnosticPick} setPick={setDiagnosticPick} columns={columns} />
        )}

        {category === "postest" && lastEst && (
          <PostestPanel last={lastEst} />
        )}
        {category === "postest" && !lastEst && (
          <CategoryHint
            heading="Run an estimation first"
            body="Postestimation operates on the most-recent regress or logit fit. Run one from the Regression tab, then come back."
          />
        )}
      </div>

      {records.length > 0 && (
        <div className="mt-10">
          <div className="eyebrow mb-3">Recent results</div>
          <div className="space-y-4">
            {records.slice().reverse().map((r) => (
              <RecordCard key={r.timestamp} record={r} />
            ))}
          </div>
        </div>
      )}

      {lastEst && (
        <div className="mt-10">
          <CommandPreview command={lastEst.command} />
        </div>
      )}
    </div>
  );
}

// =====================================================================
// Categories tab strip
// =====================================================================

const CATEGORIES: { id: Category; label: string }[] = [
  { id: "descriptives", label: "Descriptives" },
  { id: "comparisons",  label: "Comparisons" },
  { id: "diagnostics",  label: "Diagnostics" },
  { id: "regression",   label: "Regression" },
  { id: "postest",      label: "Postestimation" },
];

function CategoryTabs({ current, onPick }: { current: Category; onPick: (c: Category) => void }) {
  return (
    <div className="flex gap-1 p-1 bg-surface rounded-md border border-border w-fit">
      {CATEGORIES.map((c) => {
        const active = current === c.id;
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => onPick(c.id)}
            className={`px-3 py-[6px] rounded-sm text-[13px] font-medium transition-colors ${
              active ? "bg-accent text-bg" : "text-text-muted hover:text-text hover:bg-surface-2"
            }`}
          >
            {c.label}
          </button>
        );
      })}
    </div>
  );
}

function CategoryHint({ heading, body }: { heading: string; body: string }) {
  return (
    <div className="bg-surface border border-border rounded-md p-5 max-w-[520px]">
      <div className="font-serif italic text-[16px] mb-1">{heading}</div>
      <div className="text-[13px] text-text-muted">{body}</div>
    </div>
  );
}

// =====================================================================
// Regression picker (OLS / Logit)
// =====================================================================

function RegressionPicker({
  pick,
  setPick,
  columns,
}: {
  pick: RegressionPick;
  setPick: (p: RegressionPick) => void;
  columns: ColumnInfo[];
}) {
  return (
    <>
      <div className="flex gap-2">
        <PickerButton active={pick === "ols"} onClick={() => setPick("ols")} title="OLS">
          Linear (OLS)
        </PickerButton>
        <PickerButton active={pick === "logit"} onClick={() => setPick("logit")} title="Logit">
          Logistic
        </PickerButton>
      </div>

      <div className="bg-surface border border-border rounded-md p-6 max-w-[760px]">
        {pick === "ols" ? (
          <OlsForm columns={columns} />
        ) : (
          <LogitForm columns={columns} />
        )}
      </div>
    </>
  );
}

function PickerButton({
  children,
  active,
  ...rest
}: { children: React.ReactNode; active: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`px-4 py-2 rounded-sm border text-[13px] font-medium transition-colors ${
        active
          ? "bg-accent-soft border-accent text-text"
          : "bg-surface border-border text-text-muted hover:text-text hover:border-border-strong"
      }`}
    >
      {children}
    </button>
  );
}

// =====================================================================
// OLS form
// =====================================================================

function OlsForm({ columns }: { columns: ColumnInfo[] }) {
  const numericCols = columns.filter((c) => c.kind === "numeric" || c.kind === "binary");
  const allCols = columns;

  const [depvar, setDepvar] = useState<string>(numericCols[0]?.name ?? "");
  const [predictors, setPredictors] = useState<FactorState[]>([]);
  const [robust, setRobust] = useState(false);
  const [cluster, setCluster] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Synchronous in-flight lock — `busy` is React state that doesn't update
  // until the next render, so rapid clicks can fire multiple requests before
  // the button visibly disables. A ref blocks them immediately.
  const inFlight = useRef(false);

  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const setLast = useApp((s) => s.setLastEstimation);

  const indepvars = predictors.map((p) => formatFactor(p, allCols));

  const onRun = async () => {
    if (inFlight.current) return;
    if (!depvar || predictors.length === 0) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const r = await api.regress({
        depvar,
        indepvars,
        vce: robust ? "robust" : (cluster ? "cluster" : "ols"),
        cluster: cluster || null,
      });
      pushAnalyze({
        command: r.command,
        kind: "regress",
        payload: r,
        text: r.text,
        timestamp: Date.now(),
      });
      setLast({
        command: r.command,
        cmd_kind: "regress",
        depvar,
        indepvars,
        designColumns: r.result.design_columns,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <FormRow label="Outcome (continuous)">
        <Select
          value={depvar}
          onChange={setDepvar}
          options={numericCols.map((c) => ({ value: c.name, label: c.name }))}
        />
      </FormRow>

      <FormRow label="Predictors">
        <PredictorsEditor
          columns={allCols.filter((c) => c.name !== depvar)}
          value={predictors}
          onChange={setPredictors}
        />
      </FormRow>

      <FormRow label="Robust SE">
        <label className="inline-flex items-center gap-2 text-[13px] text-text-muted">
          <input
            type="checkbox"
            checked={robust}
            onChange={(e) => {
              setRobust(e.target.checked);
              if (e.target.checked) setCluster("");
            }}
            className="accent-accent"
          />
          vce(robust) — HC1 heteroskedasticity-robust
        </label>
      </FormRow>

      <FormRow label="Cluster (optional)">
        <Select
          value={cluster}
          onChange={(v) => {
            setCluster(v);
            if (v) setRobust(false);
          }}
          options={[
            { value: "", label: "— none —" },
            ...allCols.filter((c) => c.kind !== "numeric").map((c) => ({ value: c.name, label: c.name })),
          ]}
        />
      </FormRow>

      <div className="pt-2">
        <Tooltip
          what="Linear (OLS) regression. Fits y = β₀ + β₁·x₁ + … + βₖ·xₖ + ε by least squares."
          how="Pick a continuous outcome, add one or more predictors, optionally check Robust SE if you suspect heteroskedasticity. Hit Run regression."
          example={<>Outcome = <code className="font-mono">plaque_index</code>, Predictors = <code className="font-mono">age, i.sex, brushing_freq</code>. Negative coefficient on <code className="font-mono">brushing_freq</code> ⇒ more brushing → lower plaque.</>}
        >
          <button
            type="button"
            disabled={busy || !depvar || predictors.length === 0}
            onClick={onRun}
            className="run-btn-primary disabled:opacity-60"
          >
            {busy ? "Fitting…" : "Run regression"}
          </button>
        </Tooltip>
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>

      <div className="text-[11px] text-text-faint font-mono">
        Pro syntax: {previewCommand("regress", depvar, indepvars, { robust, cluster })}
      </div>
    </div>
  );
}

// =====================================================================
// Logit form
// =====================================================================

function LogitForm({ columns }: { columns: ColumnInfo[] }) {
  const binaryCols = columns.filter((c) => c.kind === "binary");
  const allCols = columns;

  const [depvar, setDepvar] = useState<string>(binaryCols[0]?.name ?? "");
  const [predictors, setPredictors] = useState<FactorState[]>([]);
  const [oddsRatios, setOddsRatios] = useState(true);
  const [robust, setRobust] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const setLast = useApp((s) => s.setLastEstimation);

  const indepvars = predictors.map((p) => formatFactor(p, allCols));

  const onRun = async () => {
    if (inFlight.current) return;
    if (!depvar || predictors.length === 0) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const r = await api.logit({
        depvar,
        indepvars,
        odds_ratios: oddsRatios,
        vce: robust ? "robust" : "mle",
      });
      pushAnalyze({
        command: r.command,
        kind: "logit",
        payload: r,
        text: r.text,
        timestamp: Date.now(),
      });
      setLast({
        command: r.command,
        cmd_kind: "logit",
        depvar,
        indepvars,
        designColumns: r.result.design_columns,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <FormRow label="Outcome (binary 0/1)">
        <Select
          value={depvar}
          onChange={setDepvar}
          options={binaryCols.map((c) => ({ value: c.name, label: c.name }))}
        />
      </FormRow>
      <FormRow label="Predictors">
        <PredictorsEditor
          columns={allCols.filter((c) => c.name !== depvar)}
          value={predictors}
          onChange={setPredictors}
        />
      </FormRow>
      <FormRow label="Display">
        <label className="inline-flex items-center gap-2 text-[13px] text-text-muted">
          <input
            type="checkbox"
            checked={oddsRatios}
            onChange={(e) => setOddsRatios(e.target.checked)}
            className="accent-accent"
          />
          Odds ratios (logistic)
        </label>
      </FormRow>
      <FormRow label="Robust SE">
        <label className="inline-flex items-center gap-2 text-[13px] text-text-muted">
          <input
            type="checkbox"
            checked={robust}
            onChange={(e) => setRobust(e.target.checked)}
            className="accent-accent"
          />
          vce(robust)
        </label>
      </FormRow>
      <div className="pt-2">
        <Tooltip
          what="Logistic regression for a binary 0/1 outcome. Models log-odds(y=1) as a linear combination of predictors."
          how="Pick a binary outcome (0/1 only), add predictors, decide whether to display odds ratios. Robust SE optional."
          example={<>Outcome = <code className="font-mono">caries</code>, Predictors = <code className="font-mono">age, smoking, diabetes, brushing_freq</code>. Odds ratio for <code className="font-mono">smoking</code> &gt; 1 ⇒ smokers have higher odds of caries.</>}
        >
          <button
            type="button"
            disabled={busy || !depvar || predictors.length === 0}
            onClick={onRun}
            className="run-btn-primary disabled:opacity-60"
          >
            {busy ? "Fitting…" : oddsRatios ? "Run logistic" : "Run logit"}
          </button>
        </Tooltip>
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>

      <div className="text-[11px] text-text-faint font-mono">
        Pro syntax: {previewCommand(oddsRatios ? "logistic" : "logit", depvar, indepvars, { robust, odds: oddsRatios })}
      </div>
    </div>
  );
}

// =====================================================================
// Predictor editor (multi-select with per-row factor toggles)
// =====================================================================

function PredictorsEditor({
  columns,
  value,
  onChange,
}: {
  columns: ColumnInfo[];
  value: FactorState[];
  onChange: (next: FactorState[]) => void;
}) {
  const inUse = new Set(value.map((v) => v.name));
  // ID-typed columns are only hidden when they look like row identifiers
  // (high uniqueness). A column named `group_id` with 8 unique values out
  // of 400 rows is plainly a grouping factor and should stay selectable.
  const addable = columns.filter((c) => {
    if (inUse.has(c.name)) return false;
    if (c.kind === "string") return false;
    if (c.kind === "id" && c.n > 0 && c.n_unique > c.n / 3) return false;
    return true;
  });

  const add = (name: string) => onChange([...value, { name, mode: "auto" }]);
  const remove = (name: string) => onChange(value.filter((v) => v.name !== name));
  const setMode = (name: string, mode: FactorState["mode"]) =>
    onChange(value.map((v) => (v.name === name ? { ...v, mode } : v)));

  return (
    <div className="space-y-3">
      {value.length === 0 && (
        <div className="text-[12px] text-text-faint">No predictors yet — pick from below.</div>
      )}
      {value.map((p) => {
        const col = columns.find((c) => c.name === p.name);
        return (
          <div key={p.name} className="flex items-center gap-3 bg-bg border border-border rounded-sm p-2">
            <span className="font-mono text-[12px] text-text flex-1">{p.name}</span>
            <span className="font-mono text-[10px] text-text-faint">{col?.kind ?? "?"}</span>
            <div className="flex gap-1">
              <FactorPill active={p.mode === "auto"} onClick={() => setMode(p.name, "auto")}>auto</FactorPill>
              <FactorPill active={p.mode === "c"} onClick={() => setMode(p.name, "c")}>c.</FactorPill>
              <FactorPill active={p.mode === "i"} onClick={() => setMode(p.name, "i")}>i.</FactorPill>
            </div>
            <button
              type="button"
              onClick={() => remove(p.name)}
              className="text-[11px] text-text-muted hover:text-warn px-2"
              aria-label={`Remove ${p.name}`}
            >
              ×
            </button>
          </div>
        );
      })}
      {addable.length > 0 && (
        <details className="bg-bg border border-border rounded-sm">
          <summary className="px-3 py-2 cursor-pointer text-[12px] text-text-muted font-mono">
            Add predictor…
          </summary>
          <div className="px-3 pb-3 grid grid-cols-2 gap-1">
            {addable.map((c) => (
              <button
                key={c.name}
                type="button"
                onClick={() => add(c.name)}
                className="text-left text-[12px] font-mono text-text hover:text-accent hover:bg-accent-soft px-2 py-1 rounded-sm"
              >
                + {c.name}{" "}
                <span className="text-[10px] text-text-faint">{c.kind}</span>
              </button>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function FactorPill({
  children,
  active,
  ...rest
}: { children: React.ReactNode; active: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`px-2 py-[2px] rounded-sm text-[10px] font-mono uppercase tracking-[0.04em] border transition-colors ${
        active
          ? "bg-accent text-bg border-accent"
          : "bg-surface text-text-muted border-border hover:text-text hover:border-border-strong"
      }`}
    >
      {children}
    </button>
  );
}

// =====================================================================
// Postestimation panel
// =====================================================================

function PostestPanel({ last }: { last: { command: string; cmd_kind: "regress" | "logit"; designColumns: string[] } }) {
  const refreshColumns = useApp((s) => s.refreshColumns);
  const dataset = useApp((s) => s.dataset);
  const setDataset = useApp((s) => s.setDataset);
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);

  const [busy, setBusy] = useState<"" | "margins" | "predict" | "test">("");
  const [error, setError] = useState<string | null>(null);
  const [testCoef, setTestCoef] = useState<string>(last.designColumns.find((c) => c !== "_cons") ?? "");

  const onMargins = async () => {
    setBusy("margins");
    setError(null);
    try {
      const r = await api.margins(false);
      pushAnalyze({
        command: r.command,
        kind: "margins",
        payload: r,
        text: r.text,
        timestamp: Date.now(),
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy("");
    }
  };

  const onPredict = async () => {
    setBusy("predict");
    setError(null);
    try {
      const r = await api.predictFitted({
        kind: last.cmd_kind === "logit" ? "pr" : "xb",
        new_var: last.cmd_kind === "logit" ? "predicted_pr" : "fitted_values",
      });
      // Re-fetch columns so the new variable becomes selectable in Inspect.
      const refreshed = await api.columns();
      refreshColumns(refreshed.columns);
      if (dataset) {
        setDataset(
          { ...dataset, n_vars: refreshed.columns.length, columns: refreshed.columns.map((c) => c.name) },
          refreshed.columns,
        );
      }
      pushAnalyze({
        command: r.command,
        kind: "predict",
        payload: r,
        text: r.text,
        timestamp: Date.now(),
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy("");
    }
  };

  const onTest = async () => {
    if (!testCoef) return;
    setBusy("test");
    setError(null);
    try {
      const r = await api.test([`${testCoef} = 0`]);
      pushAnalyze({
        command: r.command,
        kind: "test",
        payload: r,
        text: r.text,
        timestamp: Date.now(),
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="bg-surface border border-border rounded-md p-6 max-w-[760px] space-y-5">
      <div>
        <div className="eyebrow mb-2">Last estimation</div>
        <code className="font-mono text-[12px] text-text">{last.command}</code>
      </div>
      <div className="flex flex-wrap gap-2">
        <Tooltip
          what="Average Marginal Effect: how much does the outcome change when each predictor moves by one unit, averaged across the sample?"
          how="Click after running a regression or logit. The result card lists dy/dx, SE, and significance for every predictor."
          example={<>After <code className="font-mono">logit caries …</code>: AME for <code className="font-mono">smoking</code> ≈ +0.10 ⇒ smoking raises the predicted probability of caries by about 10 percentage points.</>}
        >
          <button type="button" onClick={onMargins} disabled={busy !== ""} className="run-btn-secondary !w-auto disabled:opacity-60">
            {busy === "margins" ? "Computing…" : "Margins (AME)"}
          </button>
        </Tooltip>
        <Tooltip
          what={last.cmd_kind === "logit"
            ? "Generates a fitted-probability column (Pr(y=1)) from the current logit fit and writes it back into the dataset."
            : "Generates fitted values (xb) from the current OLS fit and writes them back into the dataset as a new column."}
          how="Click once. The new variable shows up in Inspect under the existing columns and is ready to plot or summarize."
          example={last.cmd_kind === "logit"
            ? <>After fitting caries on age + smoking, this writes <code className="font-mono">predicted_pr</code> (one probability per patient).</>
            : <>After fitting plaque on age + brushing, this writes <code className="font-mono">fitted_values</code> (one prediction per patient).</>
          }
        >
          <button type="button" onClick={onPredict} disabled={busy !== ""} className="run-btn-secondary !w-auto disabled:opacity-60">
            {busy === "predict" ? "Computing…" : last.cmd_kind === "logit" ? "Predict probability" : "Predict fitted"}
          </button>
        </Tooltip>
        <div className="flex items-center gap-2">
          <select
            value={testCoef}
            onChange={(e) => setTestCoef(e.target.value)}
            className="bg-bg border border-border rounded-sm px-2 py-1 text-[12px] font-mono text-text"
          >
            {last.designColumns.filter((c) => c !== "_cons").map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <Tooltip
            what="Wald test of a single coefficient = 0. Asks: is this predictor's effect distinguishable from zero?"
            how="Pick a coefficient from the dropdown (mostly useful for joint or non-default tests; the regression card already gives you the marginal p-values). Click Test."
            example={<>Test <code className="font-mono">brushing_freq = 0</code> after a regression. p &lt; 0.05 ⇒ brushing's effect is real (after controls).</>}
          >
            <button type="button" onClick={onTest} disabled={busy !== "" || !testCoef} className="run-btn-secondary !w-auto disabled:opacity-60">
              {busy === "test" ? "Testing…" : `Test ${testCoef} = 0`}
            </button>
          </Tooltip>
        </div>
      </div>
      {error && <div className="text-[12px] text-warn">{error}</div>}
    </div>
  );
}

// =====================================================================
// Result rendering
// =====================================================================

function RecordCard({ record }: { record: { kind: string; command: string; payload: unknown; timestamp: number; text: string } }) {
  if (record.kind === "regress") {
    return <RegressionResult resp={record.payload as RegressResponse} command={record.command} />;
  }
  if (record.kind === "logit") {
    return <LogitResult resp={record.payload as LogitResponse} command={record.command} />;
  }
  if (record.kind === "margins") {
    return <MarginsResult resp={record.payload as MarginsResponse} command={record.command} />;
  }
  if (record.kind === "predict") {
    return <PredictResult resp={record.payload as PredictResponse} command={record.command} />;
  }
  if (record.kind === "test") {
    return <TestResult resp={record.payload as TestResponse} command={record.command} />;
  }
  if (record.kind === "oneway") {
    return <OnewayCard resp={record.payload as OnewayResponse & { _perLevelLabel?: string }} command={record.command} />;
  }
  if (record.kind === "anova_two") {
    return <AnovaTwoCard resp={record.payload as AnovaTwoResponse} command={record.command} />;
  }
  if (record.kind === "anova_rm") {
    return <AnovaRmCard resp={record.payload as AnovaRmResponse} command={record.command} />;
  }
  if (record.kind === "shapiro") {
    return <ShapiroCard resp={record.payload as ShapiroResponse} command={record.command} />;
  }
  if (record.kind === "levene") {
    return <LeveneCard resp={record.payload as LeveneResponse} command={record.command} />;
  }
  if (record.kind === "tabstat") {
    return <TabstatCard resp={record.payload as TabstatResponse} command={record.command} />;
  }
  return (
    <ResultsCard title={COMMAND_LABELS[record.kind] ?? record.kind}>
      <pre className="font-mono text-[11px] text-text-muted whitespace-pre">{record.text}</pre>
    </ResultsCard>
  );
}


function OnewayCard({ resp, command }: { resp: OnewayResponse & { _perLevelLabel?: string }; command: string }) {
  const r = resp.result;
  const title = resp._perLevelLabel
    ? `One-way ANOVA — ${r.depvar} by ${r.groupvar}  ·  ${resp._perLevelLabel}`
    : `One-way ANOVA — ${r.depvar} by ${r.groupvar}`;
  return (
    <>
      <ResultsCard title={title}>
        <HeaderGrid rows={[
          ["N",        fmt(r.n)],
          ["Groups",   fmt(r.k)],
          ["F",        fmt(r.F)],
          ["Prob > F", fmt(r.p, 4)],
        ]} />

        <div className="mt-4">
          <table className="w-full font-mono text-[12px]">
            <thead className="text-text-muted text-[11px] uppercase tracking-[0.04em]">
              <tr>
                <th className="text-left py-2 pr-3">Source</th>
                <th className="text-right py-2 px-2">SS</th>
                <th className="text-right py-2 px-2">df</th>
                <th className="text-right py-2 px-2">MS</th>
                <th className="text-right py-2 px-2">F</th>
                <th className="text-right py-2 px-2">Prob &gt; F</th>
              </tr>
            </thead>
            <tbody>
              {r.anova_table.Source.map((src, i) => (
                <tr key={src} className="border-t border-border">
                  <td className="py-1 pr-3 text-text">{src}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{fmt(r.anova_table.SS[i])}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{r.anova_table.df[i]}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{fmt(r.anova_table.MS[i])}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{fmt(r.anova_table.F[i])}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{fmt(r.anova_table.Prob_F[i], 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {r.bartlett && (
          <div className="mt-4 pt-3 border-t border-border">
            <div className="text-[11px] uppercase tracking-[0.08em] text-text-faint mb-1">
              Bartlett's test for equal variances
            </div>
            <div className="font-mono text-[12px] text-text">
              χ²({r.bartlett.df}) = {fmt(r.bartlett.chi2)} &nbsp;·&nbsp; Prob &gt; χ² = {fmt(r.bartlett.p, 4)}
              {r.bartlett.p != null && r.bartlett.p < 0.05 && (
                <span className="ml-2 text-warn">→ variances likely unequal</span>
              )}
            </div>
            {r.bartlett.note && (
              <div className="text-[11px] text-text-faint mt-1">{r.bartlett.note}</div>
            )}
          </div>
        )}

        {r.posthoc !== "none" && r.posthoc_block && (
          <div className="mt-4 pt-3 border-t border-border">
            <div className="text-[11px] uppercase tracking-[0.08em] text-text-faint mb-2">
              Pairwise comparisons — {r.posthoc} adjusted
            </div>
            <PairwiseMatrix block={r.posthoc_block} />
          </div>
        )}
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function PairwiseMatrix({ block }: { block: NonNullable<OnewayResponse["result"]["posthoc_block"]> }) {
  const allGroups = Array.from(new Set(block.comparisons.flatMap((c) => [c.a, c.b])));
  // sort for stable layout
  allGroups.sort();
  const lookup = (a: string, b: string) => block.matrix[a]?.[b] ?? null;
  return (
    <div className="overflow-x-auto">
      <table className="font-mono text-[11px]">
        <thead className="text-text-muted">
          <tr>
            <th className="text-left p-1 pr-3"></th>
            {allGroups.map((g) => (
              <th key={g} className="text-right p-1 px-2">{g}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {allGroups.map((row) => (
            <tr key={row} className="border-t border-border">
              <td className="py-1 pr-3 text-text">{row}</td>
              {allGroups.map((col) => {
                if (row === col) return <td key={col} className="text-right p-1 px-2 text-text-faint">—</td>;
                const cell = lookup(row, col);
                if (!cell) return <td key={col} className="text-right p-1 px-2 text-text-faint">·</td>;
                const sig = cell.p_adj != null && cell.p_adj < 0.05;
                return (
                  <td key={col} className={`text-right p-1 px-2 ${sig ? "text-accent" : "text-text-muted"}`}>
                    <div>{fmt(cell.mean_diff)}</div>
                    <div className="text-[10px] text-text-faint">p={fmt(cell.p_adj, 4)}</div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnovaTwoCard({ resp, command }: { resp: AnovaTwoResponse; command: string }) {
  const r = resp.result;
  return (
    <>
      <ResultsCard title={`Two-way ANOVA — ${r.depvar} ~ ${r.factor_a} ${r.interaction ? "×" : "+"} ${r.factor_b}`}>
        <HeaderGrid rows={[
          ["N",       fmt(r.n)],
          ["R²",      fmt(r.r_squared, 4)],
          ["Adj. R²", fmt(r.r_squared_adj, 4)],
        ]} />
        <div className="mt-4">
          <table className="w-full font-mono text-[12px]">
            <thead className="text-text-muted text-[11px] uppercase tracking-[0.04em]">
              <tr>
                <th className="text-left py-2 pr-3">Source</th>
                <th className="text-right py-2 px-2">SS</th>
                <th className="text-right py-2 px-2">df</th>
                <th className="text-right py-2 px-2">MS</th>
                <th className="text-right py-2 px-2">F</th>
                <th className="text-right py-2 px-2">Prob &gt; F</th>
              </tr>
            </thead>
            <tbody>
              {r.rows.map((row) => {
                const sig = row.Prob_F != null && row.Prob_F < 0.05;
                return (
                  <tr key={row.Source} className="border-t border-border">
                    <td className={`py-1 pr-3 ${sig ? "text-accent" : "text-text"}`}>{row.Source}</td>
                    <td className="text-right py-1 px-2 text-text-muted">{fmt(row.SS)}</td>
                    <td className="text-right py-1 px-2 text-text-muted">{row.df}</td>
                    <td className="text-right py-1 px-2 text-text-muted">{fmt(row.MS)}</td>
                    <td className="text-right py-1 px-2 text-text-muted">{fmt(row.F)}</td>
                    <td className="text-right py-1 px-2 text-text-muted">{fmt(row.Prob_F, 4)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function AnovaRmCard({ resp, command }: { resp: AnovaRmResponse; command: string }) {
  const r = resp.result;
  const hasCorr = r.correction !== "none";
  const bs = r.between_summary;
  const bsSig = bs?.p != null && bs.p < 0.05;
  return (
    <>
      <ResultsCard title={`Repeated-measures ANOVA — ${r.depvar}`}>
        <HeaderGrid rows={[
          ["Subjects",   fmt(r.n_subjects)],
          ["Obs",        fmt(r.n_obs)],
          ["Within",     r.within],
          ["Between",    r.between ?? "—"],
          ["Correction", r.correction === "gg" ? "Greenhouse-Geisser" : r.correction === "hf" ? "Huynh-Feldt" : "none"],
        ]} />
        <div className="mt-4">
          <table className="w-full font-mono text-[12px]">
            <thead className="text-text-muted text-[11px] uppercase tracking-[0.04em]">
              <tr>
                <th className="text-left py-2 pr-3">Source</th>
                <th className="text-right py-2 px-2">F</th>
                <th className="text-right py-2 px-2">df (num, den)</th>
                <th className="text-right py-2 px-2">P</th>
                {hasCorr && <th className="text-right py-2 px-2">ε</th>}
                {hasCorr && <th className="text-right py-2 px-2">P (adj)</th>}
              </tr>
            </thead>
            <tbody>
              {r.rows.map((row) => {
                const pUsed = hasCorr ? row.p_adj : row.p;
                const sig = pUsed != null && pUsed < 0.05;
                return (
                  <tr key={row.Source} className="border-t border-border">
                    <td className={`py-1 pr-3 ${sig ? "text-accent" : "text-text"}`}>{row.Source}</td>
                    <td className="text-right py-1 px-2 text-text-muted">{fmt(row.F)}</td>
                    <td className="text-right py-1 px-2 text-text-muted">({fmt(row.df_num)}, {fmt(row.df_den)})</td>
                    <td className="text-right py-1 px-2 text-text-muted">{fmt(row.p, 4)}</td>
                    {hasCorr && <td className="text-right py-1 px-2 text-text-muted">{fmt(row.epsilon, 3)}</td>}
                    {hasCorr && <td className="text-right py-1 px-2 text-text-muted">{fmt(row.p_adj, 4)}</td>}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {r.between && bs && (
          <div className="mt-4 p-3 rounded-md border border-border bg-surface-2">
            <div className="text-[11px] uppercase tracking-[0.04em] text-text-muted mb-2">
              Between-subjects effect — {r.between}
            </div>
            <div className="font-mono text-[12px] flex gap-6">
              <div>F = <span className={bsSig ? "text-accent" : "text-text"}>{fmt(bs.F)}</span></div>
              <div>P = <span className={bsSig ? "text-accent" : "text-text"}>{fmt(bs.p, 4)}</span></div>
              <div className="text-text-muted">k = {bs.k ?? "—"}</div>
              <div className="text-text-muted">subjects = {bs.n_subjects ?? "—"}</div>
            </div>
            <div className="mt-2 text-[11px] text-text-faint">
              Computed from subject-level means (split-plot workaround). A proper
              mixed-effects between×within fit lands in v3.1.
            </div>
          </div>
        )}
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function ShapiroCard({ resp, command }: { resp: ShapiroResponse; command: string }) {
  const r = resp.result;
  return (
    <>
      <ResultsCard title={`Shapiro-Wilk — ${r.variable}${r.by ? ` by ${r.by}` : ""}`}>
        <table className="w-full font-mono text-[12px]">
          <thead className="text-text-muted text-[11px] uppercase tracking-[0.04em]">
            <tr>
              <th className="text-left py-2 pr-3">Group</th>
              <th className="text-right py-2 px-2">N</th>
              <th className="text-right py-2 px-2">W</th>
              <th className="text-right py-2 px-2">P</th>
            </tr>
          </thead>
          <tbody>
            {r.rows.map((row, i) => {
              const reject = row.p != null && row.p < 0.05;
              return (
                <tr key={i} className="border-t border-border">
                  <td className="py-1 pr-3 text-text">{row.group ?? "(all)"}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{row.n}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{fmt(row.W, 4)}</td>
                  <td className={`text-right py-1 px-2 ${reject ? "text-warn" : "text-text-muted"}`}>{fmt(row.p, 4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="mt-3 text-[11px] text-text-faint">
          p &lt; 0.05 ⇒ reject normality. Consider Mann-Whitney, Kruskal-Wallis,
          or Friedman if the assumption fails.
        </div>
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function LeveneCard({ resp, command }: { resp: LeveneResponse; command: string }) {
  const r = resp.result;
  const reject = r.p != null && r.p < 0.05;
  return (
    <>
      <ResultsCard title={`Levene's test — ${r.depvar} by ${r.groupvar}`}>
        <HeaderGrid rows={[
          ["W₀",       fmt(r.W, 4)],
          ["df",       `(${r.df1}, ${r.df2})`],
          ["Prob > F", fmt(r.p, 4)],
          ["Center",   r.center],
        ]} />
        <div className="mt-3">
          <table className="w-full font-mono text-[12px]">
            <thead className="text-text-muted text-[11px] uppercase tracking-[0.04em]">
              <tr>
                <th className="text-left py-2 pr-3">{r.groupvar}</th>
                <th className="text-right py-2 px-2">N</th>
                <th className="text-right py-2 px-2">Mean</th>
                <th className="text-right py-2 px-2">SD</th>
              </tr>
            </thead>
            <tbody>
              {r.groups.map((g) => (
                <tr key={g.group} className="border-t border-border">
                  <td className="py-1 pr-3 text-text">{g.group}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{g.n}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{fmt(g.mean, 4)}</td>
                  <td className="text-right py-1 px-2 text-text-muted">{fmt(g.sd, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={`mt-3 text-[11px] ${reject ? "text-warn" : "text-text-faint"}`}>
          {reject
            ? "p < 0.05 ⇒ variances differ across groups. Consider Welch's correction or non-parametric tests."
            : "p ≥ 0.05 ⇒ no strong evidence of unequal variances."}
        </div>
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function TabstatCard({ resp, command }: { resp: TabstatResponse; command: string }) {
  const r = resp.result;
  return (
    <>
      <ResultsCard title={r.by ? `Summary statistics by ${r.by}` : "Summary statistics"}>
        {r.groups == null ? (
          // No `by`: simple var × stat matrix
          <table className="w-full font-mono text-[12px]">
            <thead className="text-text-muted text-[11px] uppercase tracking-[0.04em]">
              <tr>
                <th className="text-left py-2 pr-3">Variable</th>
                {r.stats.map((s) => (
                  <th key={s} className="text-right py-2 px-2">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.variables.map((v) => {
                const row = (r.matrix as Record<string, Record<string, number | null>>)[v] || {};
                return (
                  <tr key={v} className="border-t border-border">
                    <td className="py-1 pr-3 text-text">{v}</td>
                    {r.stats.map((s) => (
                      <td key={s} className="text-right py-1 px-2 text-text-muted">{fmt(row[s])}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          // With `by`: group × var × stat
          <div className="space-y-4">
            {(r.groups as string[]).map((g) => {
              const block = (r.matrix as Record<string, Record<string, Record<string, number | null>>>)[g] || {};
              return (
                <div key={g}>
                  <div className="text-[11px] uppercase tracking-[0.08em] text-text-faint mb-1">
                    {r.by} = <span className="text-accent">{g}</span>
                  </div>
                  <table className="w-full font-mono text-[12px]">
                    <thead className="text-text-muted text-[11px]">
                      <tr>
                        <th className="text-left py-1 pr-3">Variable</th>
                        {r.stats.map((s) => (
                          <th key={s} className="text-right py-1 px-2">{s}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {r.variables.map((v) => (
                        <tr key={v} className="border-t border-border">
                          <td className="py-1 pr-3 text-text">{v}</td>
                          {r.stats.map((s) => (
                            <td key={s} className="text-right py-1 px-2 text-text-muted">{fmt(block[v]?.[s])}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        )}
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function RegressionResult({ resp, command }: { resp: RegressResponse; command: string }) {
  const h = resp.result.header;
  return (
    <>
      <ResultsCard title={`Linear regression — ${resp.result.depvar}`}>
        <HeaderGrid
          rows={[
            ["N",          fmt(h.N)],
            ["F",          fmt(h.F)],
            ["Prob > F",   fmt(h.Prob_F)],
            ["R²",         fmt(h.R2)],
            ["Adj. R²",    fmt(h.R2_adj)],
            ["Root MSE",   fmt(h.RMSE)],
          ]}
        />
        {h.vce !== "ols" && (
          <div className="text-[11px] text-text-faint mt-2 font-mono">
            {h.vce === "robust" && "Robust SE (HC1)"}
            {h.vce === "hc3" && "Robust SE (HC3)"}
            {h.vce === "cluster" && `Clustered on ${h.cluster}`}
          </div>
        )}
      </ResultsCard>
      <CoefficientTable rows={resp.result.coefficients} columnLabel="Coef." />
      <PostestActionsRow />
      <CommandLine command={command} />
    </>
  );
}

function LogitResult({ resp, command }: { resp: LogitResponse; command: string }) {
  const h = resp.result.header;
  return (
    <>
      <ResultsCard title={`Logistic regression — ${resp.result.depvar}`}>
        <HeaderGrid
          rows={[
            ["N",                fmt(h.N)],
            ["LR χ²",            fmt(h.LR_chi2)],
            ["Prob > χ²",        fmt(h.Prob_chi2)],
            ["Pseudo R²",        fmt(h.Pseudo_R2)],
            ["Log likelihood",   fmt(h.log_likelihood)],
            ["Display",          h.odds_ratios ? "Odds ratios" : "Coefficients"],
          ]}
        />
      </ResultsCard>
      <CoefficientTable
        rows={resp.result.coefficients}
        columnLabel={h.odds_ratios ? "OR" : "Coef."}
      />
      <PostestActionsRow />
      <CommandLine command={command} />
    </>
  );
}

function MarginsResult({ resp, command }: { resp: MarginsResponse; command: string }) {
  return (
    <>
      <ResultsCard title="Average marginal effects">
        <table className="w-full font-mono text-[12px]">
          <thead className="text-text-muted">
            <tr>
              <th className="text-left py-1 pr-3">Variable</th>
              <th className="text-right py-1 px-2">dy/dx</th>
              <th className="text-right py-1 px-2">SE</th>
              <th className="text-right py-1 px-2">P&gt;|z|</th>
              <th className="text-right py-1 px-2">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {resp.result.rows.map((r) => (
              <tr key={r.name} className="border-t border-border">
                <td className="py-[6px] pr-3 text-text">
                  <SignificanceDot p={r.p} />
                  {r.name}
                </td>
                <td className="text-right py-[6px] px-2 text-text">{fmt(r.dy_dx)}</td>
                <td className="text-right py-[6px] px-2 text-text-muted">{fmt(r.se)}</td>
                <td className="text-right py-[6px] px-2 text-text-muted">{fmt(r.p, 4)}</td>
                <td className="text-right py-[6px] px-2 text-text-muted">
                  [{fmt(r.ci_low)}, {fmt(r.ci_high)}]
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function PredictResult({ resp, command }: { resp: PredictResponse; command: string }) {
  return (
    <>
      <ResultsCard title="Predict">
        <div className="font-mono text-[12px] text-text">
          Wrote <span className="text-accent">{resp.result.new_var}</span> to dataset (
          {resp.result.label}, {resp.result.n_filled.toLocaleString()} non-missing).
        </div>
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

function TestResult({ resp, command }: { resp: TestResponse; command: string }) {
  const stat = resp.result.chi2 ?? resp.result.F;
  return (
    <>
      <ResultsCard title="Wald test">
        <div className="font-mono text-[12px] text-text space-y-1">
          <div>{resp.result.restrictions.join(", ")}</div>
          <div>statistic = {fmt(stat)}</div>
          <div>p = {fmt(resp.result.p, 4)}</div>
        </div>
      </ResultsCard>
      <CommandLine command={command} />
    </>
  );
}

// =====================================================================
// v3.0.2 — Descriptives (tabstat)
// =====================================================================

function TabstatForm({ columns }: { columns: ColumnInfo[] }) {
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const numerics = columns.filter((c) => c.kind === "numeric" || c.kind === "binary");
  const categoricals = columns.filter((c) => c.kind !== "id" && c.kind !== "numeric");

  const DEFAULT_STATS = ["n", "mean", "sd", "min", "median", "max"];
  const [vars, setVars] = useState<string[]>([]);
  const [by, setBy] = useState("");
  const [chosenStats, setChosenStats] = useState<string[]>(DEFAULT_STATS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const toggleVar = (name: string) =>
    setVars((cur) => (cur.includes(name) ? cur.filter((v) => v !== name) : [...cur, name]));
  const toggleStat = (st: string) =>
    setChosenStats((cur) => (cur.includes(st) ? cur.filter((s) => s !== st) : [...cur, st]));

  const command = vars.length
    ? `tabstat ${vars.join(" ")}, ${by ? `by(${by}) ` : ""}stats(${chosenStats.join(" ")})`
    : "tabstat <vars>";

  const onRun = async () => {
    if (inFlight.current) return;
    if (vars.length === 0) return;
    inFlight.current = true;
    setBusy(true); setError(null);
    try {
      const r = await api.tabstat({ variables: vars, by: by || null, stats: chosenStats });
      pushAnalyze({ command: r.command, kind: "tabstat", payload: r, text: r.text, timestamp: Date.now() });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-md p-6 max-w-[820px] space-y-5">
      <div>
        <div className="font-serif italic text-[16px] text-text mb-1">Summary by group</div>
        <div className="text-[12px] text-text-muted">
          Stata <code className="font-mono">tabstat</code> — n / mean / SD / min / median / max
          per variable, optionally split by a grouping factor. This is Table 2 of
          most clinical papers.
        </div>
      </div>

      <FormRow label="Variables (numeric)">
        <div className="flex flex-wrap gap-2">
          {numerics.map((c) => {
            const active = vars.includes(c.name);
            return (
              <button
                key={c.name}
                type="button"
                onClick={() => toggleVar(c.name)}
                className={`px-2 py-1 rounded-sm text-[11px] font-mono border ${
                  active
                    ? "bg-accent-soft border-accent text-text"
                    : "bg-bg border-border text-text-muted hover:text-text hover:border-border-strong"
                }`}
              >
                {c.name}
              </button>
            );
          })}
          {numerics.length === 0 && (
            <div className="text-[12px] text-text-faint">No numeric variables in this dataset.</div>
          )}
        </div>
      </FormRow>

      <FormRow label="Group by (optional)">
        <Select
          value={by}
          onChange={setBy}
          options={[{ value: "", label: "— none —" }, ...categoricals.map((c) => ({ value: c.name, label: c.name }))]}
        />
      </FormRow>

      <FormRow label="Statistics">
        <div className="flex flex-wrap gap-2">
          {DEFAULT_STATS.map((st) => {
            const active = chosenStats.includes(st);
            return (
              <button
                key={st}
                type="button"
                onClick={() => toggleStat(st)}
                className={`px-2 py-1 rounded-sm text-[11px] font-mono border ${
                  active
                    ? "bg-accent-soft border-accent text-text"
                    : "bg-bg border-border text-text-muted hover:text-text"
                }`}
              >
                {st}
              </button>
            );
          })}
        </div>
      </FormRow>

      <div className="pt-2">
        <Tooltip
          what="By-group descriptives matrix: rows are variables, columns are stats, optionally split by a grouping factor."
          how="Pick one or more numeric variables, choose an optional grouping factor, and run."
          example={<>Pick <code className="font-mono">plaque_index, gingival_index</code>, group by <code className="font-mono">smoking</code> &mdash; instant Table 2.</>}
        >
          <button
            type="button"
            disabled={busy || vars.length === 0}
            onClick={onRun}
            className="run-btn-primary disabled:opacity-60"
          >
            {busy ? "Computing…" : "Run tabstat"}
          </button>
        </Tooltip>
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>

      <div className="text-[11px] text-text-faint font-mono">Pro syntax: {command}</div>
    </div>
  );
}


// =====================================================================
// v3.0.2 — Comparisons picker (one-way / two-way / RM ANOVA)
// =====================================================================

function ComparisonPicker({
  pick, setPick, columns,
}: { pick: ComparisonPick; setPick: (p: ComparisonPick) => void; columns: ColumnInfo[] }) {
  return (
    <>
      <div className="flex gap-2 flex-wrap">
        <PickerButton active={pick === "oneway"} onClick={() => setPick("oneway")} title="One-way ANOVA">
          One-way ANOVA
        </PickerButton>
        <PickerButton active={pick === "anova_two"} onClick={() => setPick("anova_two")} title="Two-way ANOVA">
          Two-way ANOVA
        </PickerButton>
        <PickerButton active={pick === "anova_rm"} onClick={() => setPick("anova_rm")} title="Repeated-measures ANOVA">
          Repeated-measures ANOVA
        </PickerButton>
      </div>

      <div className="bg-surface border border-border rounded-md p-6 max-w-[820px]">
        {pick === "oneway" && <OnewayForm columns={columns} />}
        {pick === "anova_two" && <AnovaTwoForm columns={columns} />}
        {pick === "anova_rm" && <AnovaRmForm columns={columns} />}
      </div>
    </>
  );
}


// =====================================================================
// One-way ANOVA form (with Bartlett's footer, post-hoc, "by each level")
// =====================================================================

function OnewayForm({ columns }: { columns: ColumnInfo[] }) {
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const numerics = columns.filter((c) => c.kind === "numeric");
  const groupable = columns.filter((c) => c.kind !== "id" && c.kind !== "numeric");

  const [depvar, setDepvar] = useState(numerics[0]?.name ?? "");
  const [groupvar, setGroupvar] = useState(groupable[0]?.name ?? "");
  const [posthoc, setPosthoc] = useState<"none" | "bonferroni" | "scheffe" | "sidak">("none");
  const [perLevel, setPerLevel] = useState("");          // A1.5 — "Run for each level of X"
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const command = perLevel
    ? `foreach lvl in <levels of ${perLevel}> {\n  oneway ${depvar} ${groupvar} if ${perLevel} == "\`lvl'"${posthoc !== "none" ? `, ${posthoc}` : ""}\n}`
    : `oneway ${depvar} ${groupvar}${posthoc !== "none" ? `, ${posthoc}` : ""}`;

  const onRun = async () => {
    if (inFlight.current) return;
    if (!depvar || !groupvar) return;
    inFlight.current = true;
    setBusy(true); setError(null); setProgress("");
    try {
      if (perLevel) {
        // Fetch the distinct levels of perLevel from the dataset's frame.
        // Quick path: re-run a tabstat to learn the levels; simpler still
        // is hitting /api/data/preview, but tabulate gives us a cleaner list.
        const t = await api.tabulate(perLevel);
        const levels: (string | number)[] = (t.result.rows || []).map((r) => r.value as string | number);
        let count = 0;
        for (const lvl of levels) {
          setProgress(`Running for ${perLevel} = ${String(lvl)} (${count + 1} / ${levels.length})…`);
          const ifExpr = typeof lvl === "number"
            ? `${perLevel} == ${lvl}`
            : `${perLevel} == "${String(lvl).replace(/"/g, '\\"')}"`;
          const r = await api.oneway({
            depvar, groupvar, posthoc,
            if_expr: ifExpr,
          });
          pushAnalyze({
            command: `${r.command}   /* ${perLevel} = ${String(lvl)} */`,
            kind: "oneway",
            payload: { ...r, _perLevelLabel: `${perLevel} = ${String(lvl)}` },
            text: r.text,
            timestamp: Date.now() + count,    // unique timestamps for stable keys
          });
          count++;
        }
        setProgress(`Done — ${count} ANOVAs at each level of ${perLevel}.`);
      } else {
        const r = await api.oneway({ depvar, groupvar, posthoc });
        pushAnalyze({ command: r.command, kind: "oneway", payload: r, text: r.text, timestamp: Date.now() });
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <FormRow label="Outcome (numeric)">
        <Select value={depvar} onChange={setDepvar} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Grouping variable">
        <Select value={groupvar} onChange={setGroupvar} options={groupable.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Post-hoc multiple-comparison correction">
        <Select
          value={posthoc}
          onChange={(v) => setPosthoc(v as typeof posthoc)}
          options={[
            { value: "none", label: "None" },
            { value: "bonferroni", label: "Bonferroni" },
            { value: "scheffe", label: "Scheffé" },
            { value: "sidak", label: "Sidak" },
          ]}
        />
      </FormRow>
      <FormRow label="Run separately for each level of (optional)">
        <Select
          value={perLevel}
          onChange={setPerLevel}
          options={[
            { value: "", label: "— no, just one ANOVA —" },
            ...groupable.filter((c) => c.name !== groupvar && c.name !== depvar)
                        .map((c) => ({ value: c.name, label: c.name })),
          ]}
        />
      </FormRow>

      <div className="pt-2">
        <Tooltip
          what="One-way analysis of variance. Tests whether the mean of the outcome differs across levels of one grouping factor. Bartlett's test for equal variances is appended automatically."
          how="Pick a numeric outcome and a categorical grouping variable. Choose a post-hoc correction if you want pairwise comparisons. Toggle 'Run separately for each level of X' to loop the ANOVA across another factor (one card per level)."
          example={<>Outcome = <code className="font-mono">mean_VHN</code>, group = <code className="font-mono">group_id</code>, post-hoc = Bonferroni. Repeated across the 8 ratios via "Run separately for each level of <code className="font-mono">ratio</code>".</>}
        >
          <button
            type="button"
            disabled={busy || !depvar || !groupvar}
            onClick={onRun}
            className="run-btn-primary disabled:opacity-60"
          >
            {busy ? "Computing…" : perLevel ? `Run for each level of ${perLevel}` : "Run one-way ANOVA"}
          </button>
        </Tooltip>
        {progress && <div className="mt-3 text-[12px] text-text-muted">{progress}</div>}
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>

      <div className="text-[11px] text-text-faint font-mono whitespace-pre">Pro syntax: {command}</div>
    </div>
  );
}


// =====================================================================
// Two-way ANOVA form
// =====================================================================

function AnovaTwoForm({ columns }: { columns: ColumnInfo[] }) {
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const numerics = columns.filter((c) => c.kind === "numeric");
  const factorable = columns.filter((c) => c.kind !== "id" && c.kind !== "numeric");

  const [depvar, setDepvar] = useState(numerics[0]?.name ?? "");
  const [factorA, setFactorA] = useState(factorable[0]?.name ?? "");
  const [factorB, setFactorB] = useState(factorable[1]?.name ?? factorable[0]?.name ?? "");
  const [interaction, setInteraction] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const command = `anova ${depvar} ${factorA}${interaction ? "##" : "+"}${factorB}`;

  const onRun = async () => {
    if (inFlight.current) return;
    if (!depvar || !factorA || !factorB) return;
    inFlight.current = true;
    setBusy(true); setError(null);
    try {
      const r = await api.anovaTwo({ depvar, factor_a: factorA, factor_b: factorB, interaction });
      pushAnalyze({ command: r.command, kind: "anova_two", payload: r, text: r.text, timestamp: Date.now() });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <FormRow label="Outcome (numeric)">
        <Select value={depvar} onChange={setDepvar} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Factor A">
        <Select value={factorA} onChange={setFactorA} options={factorable.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Factor B">
        <Select value={factorB} onChange={setFactorB} options={factorable.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Include interaction term">
        <label className="inline-flex items-center gap-2 text-[13px] text-text-muted">
          <input type="checkbox" checked={interaction} onChange={(e) => setInteraction(e.target.checked)} className="accent-accent" />
          {factorA} × {factorB}
        </label>
      </FormRow>
      <div className="pt-2">
        <Tooltip
          what="Two-way ANOVA: tests main effects of two factors and (optionally) their interaction on a continuous outcome."
          how="Pick the outcome, the two factors, and decide whether to include the interaction. Keep it on for dose-response / time-course designs."
          example={<>Outcome = <code className="font-mono">mean_VHN</code>, A = <code className="font-mono">group_id</code>, B = <code className="font-mono">ratio</code>, with interaction.</>}
        >
          <button
            type="button"
            disabled={busy || !depvar || !factorA || !factorB}
            onClick={onRun}
            className="run-btn-primary disabled:opacity-60"
          >
            {busy ? "Computing…" : "Run two-way ANOVA"}
          </button>
        </Tooltip>
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>
      <div className="text-[11px] text-text-faint font-mono">Pro syntax: {command}</div>
    </div>
  );
}


// =====================================================================
// Repeated-measures ANOVA form
// =====================================================================

function AnovaRmForm({ columns }: { columns: ColumnInfo[] }) {
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const numerics = columns.filter((c) => c.kind === "numeric");
  const idable = columns.filter((c) => c.kind !== "numeric");

  const [depvar, setDepvar] = useState(numerics[0]?.name ?? "");
  const [subject, setSubject] = useState(idable.find((c) => c.kind === "id")?.name ?? idable[0]?.name ?? "");
  const [within, setWithin] = useState(idable[0]?.name ?? "");
  const [between, setBetween] = useState("");
  const [correction, setCorrection] = useState<"none" | "gg" | "hf">("none");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const command = `anova ${depvar} ${subject}##${within}${between ? `##${between}` : ""}, repeated(${within})${correction !== "none" ? ` ${correction}` : ""}`;

  const onRun = async () => {
    if (inFlight.current) return;
    if (!depvar || !subject || !within) return;
    inFlight.current = true;
    setBusy(true); setError(null);
    try {
      const r = await api.anovaRm({ depvar, subject, within, between: between || null, correction });
      pushAnalyze({ command: r.command, kind: "anova_rm", payload: r, text: r.text, timestamp: Date.now() });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <FormRow label="Outcome (numeric)">
        <Select value={depvar} onChange={setDepvar} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Subject ID (one row per subject × within-level)">
        <Select value={subject} onChange={setSubject} options={idable.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Within-subject factor (e.g. timepoint)">
        <Select value={within} onChange={setWithin} options={idable.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Between-subject factor (optional)">
        <Select
          value={between}
          onChange={setBetween}
          options={[{ value: "", label: "— none —" },
                    ...idable.filter((c) => c.name !== subject && c.name !== within)
                              .map((c) => ({ value: c.name, label: c.name }))]}
        />
      </FormRow>
      <FormRow label="Sphericity correction">
        <Select
          value={correction}
          onChange={(v) => setCorrection(v as typeof correction)}
          options={[
            { value: "none", label: "None" },
            { value: "gg", label: "Greenhouse-Geisser" },
            { value: "hf", label: "Huynh-Feldt" },
          ]}
        />
      </FormRow>
      <div className="pt-2">
        <Tooltip
          what="Repeated-measures ANOVA: tests the effect of a within-subjects factor (e.g. time) and optionally a between-subjects factor on a continuous outcome. Sphericity correction adjusts the p-value when within-level variances differ."
          how="Each subject must contribute one row per within-level. Pick subject ID, within-factor, optional between-factor, and a correction."
          example={<>Outcome = <code className="font-mono">mean_VHN</code>, subject = <code className="font-mono">specimen_id</code>, within = <code className="font-mono">timepoint</code>, between = <code className="font-mono">group_id</code>.</>}
        >
          <button
            type="button"
            disabled={busy || !depvar || !subject || !within}
            onClick={onRun}
            className="run-btn-primary disabled:opacity-60"
          >
            {busy ? "Computing…" : "Run RM-ANOVA"}
          </button>
        </Tooltip>
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>
      <div className="text-[11px] text-text-faint font-mono">Pro syntax: {command}</div>
    </div>
  );
}


// =====================================================================
// Diagnostics picker (Shapiro / Levene)
// =====================================================================

function DiagnosticPicker({
  pick, setPick, columns,
}: { pick: DiagnosticPick; setPick: (p: DiagnosticPick) => void; columns: ColumnInfo[] }) {
  return (
    <>
      <div className="flex gap-2 flex-wrap">
        <PickerButton active={pick === "shapiro"} onClick={() => setPick("shapiro")} title="Shapiro-Wilk">
          Normality (Shapiro-Wilk)
        </PickerButton>
        <PickerButton active={pick === "levene"} onClick={() => setPick("levene")} title="Levene's">
          Variance homogeneity (Levene's)
        </PickerButton>
      </div>
      <div className="bg-surface border border-border rounded-md p-6 max-w-[820px]">
        {pick === "shapiro" && <ShapiroForm columns={columns} />}
        {pick === "levene" && <LeveneForm columns={columns} />}
      </div>
    </>
  );
}

function ShapiroForm({ columns }: { columns: ColumnInfo[] }) {
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const numerics = columns.filter((c) => c.kind === "numeric");
  const groupable = columns.filter((c) => c.kind !== "id" && c.kind !== "numeric");

  const [variable, setVariable] = useState(numerics[0]?.name ?? "");
  const [by, setBy] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const command = `swilk ${variable}${by ? `, by(${by})` : ""}`;

  const onRun = async () => {
    if (inFlight.current) return;
    if (!variable) return;
    inFlight.current = true;
    setBusy(true); setError(null);
    try {
      const r = await api.shapiro({ var: variable, by: by || null });
      pushAnalyze({ command: r.command, kind: "shapiro", payload: r, text: r.text, timestamp: Date.now() });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <FormRow label="Variable (numeric)">
        <Select value={variable} onChange={setVariable} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Group by (optional)">
        <Select value={by} onChange={setBy} options={[{ value: "", label: "— overall —" }, ...groupable.map((c) => ({ value: c.name, label: c.name }))]} />
      </FormRow>
      <div className="pt-2">
        <Tooltip
          what="Shapiro-Wilk test for normality of a numeric variable. p > 0.05 = consistent with normal."
          how="Pick a variable; optionally split by a categorical to test each subgroup separately."
          example={<>Run on <code className="font-mono">mean_VHN</code> before deciding between t-test and Mann-Whitney.</>}
        >
          <button type="button" disabled={busy || !variable} onClick={onRun} className="run-btn-primary disabled:opacity-60">
            {busy ? "Computing…" : "Run Shapiro-Wilk"}
          </button>
        </Tooltip>
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>
      <div className="text-[11px] text-text-faint font-mono">Pro syntax: {command}</div>
    </div>
  );
}

function LeveneForm({ columns }: { columns: ColumnInfo[] }) {
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const numerics = columns.filter((c) => c.kind === "numeric");
  const groupable = columns.filter((c) => c.kind !== "id" && c.kind !== "numeric");

  const [depvar, setDepvar] = useState(numerics[0]?.name ?? "");
  const [groupvar, setGroupvar] = useState(groupable[0]?.name ?? "");
  const [center, setCenter] = useState<"median" | "mean" | "trimmed">("median");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const command = `robvar ${depvar}, by(${groupvar})${center !== "median" ? ` center(${center})` : ""}`;

  const onRun = async () => {
    if (inFlight.current) return;
    if (!depvar || !groupvar) return;
    inFlight.current = true;
    setBusy(true); setError(null);
    try {
      const r = await api.levene({ depvar, groupvar, center });
      pushAnalyze({ command: r.command, kind: "levene", payload: r, text: r.text, timestamp: Date.now() });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <FormRow label="Outcome (numeric)">
        <Select value={depvar} onChange={setDepvar} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Grouping variable">
        <Select value={groupvar} onChange={setGroupvar} options={groupable.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Center">
        <Select
          value={center}
          onChange={(v) => setCenter(v as typeof center)}
          options={[
            { value: "median", label: "Median (robust — Brown-Forsythe, default)" },
            { value: "mean", label: "Mean (classic Levene)" },
            { value: "trimmed", label: "Trimmed mean" },
          ]}
        />
      </FormRow>
      <div className="pt-2">
        <Tooltip
          what="Levene's test for equality of variance across groups. p < 0.05 = variances differ; consider Welch's correction or non-parametric tests."
          how="Pick a numeric outcome, a grouping factor, and a center (median is the robust default; mean is classic)."
          example={<>Outcome = <code className="font-mono">mean_VHN</code>, group = <code className="font-mono">group_id</code>, center = median.</>}
        >
          <button type="button" disabled={busy || !depvar || !groupvar} onClick={onRun} className="run-btn-primary disabled:opacity-60">
            {busy ? "Computing…" : "Run Levene's"}
          </button>
        </Tooltip>
        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>
      <div className="text-[11px] text-text-faint font-mono">Pro syntax: {command}</div>
    </div>
  );
}


// =====================================================================
// Post-estimation action row — appears beneath every regress/logit card.
// Operates on `lastEstimation` (most recent fit), same semantics as the
// dedicated Postestimation tab. Clicking pushes a new analyze record so
// the result shows up at the top of the recent-results list.
// =====================================================================

function PostestActionsRow() {
  const last = useApp((s) => s.lastEstimation);
  const refreshColumns = useApp((s) => s.refreshColumns);
  const dataset = useApp((s) => s.dataset);
  const setDataset = useApp((s) => s.setDataset);
  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);

  const [busy, setBusy] = useState<"" | "margins" | "predict" | "test">("");
  const [error, setError] = useState<string | null>(null);
  const [testCoef, setTestCoef] = useState<string>("");
  const inFlight = useRef(false);

  if (!last) return null;
  const designCoefs = last.designColumns.filter((c) => c !== "_cons");
  const currentTestCoef = testCoef || designCoefs[0] || "";

  const guard = async (key: "margins" | "predict" | "test", fn: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(key); setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  };

  const onMargins = () => guard("margins", async () => {
    const r = await api.margins(false);
    pushAnalyze({ command: r.command, kind: "margins", payload: r, text: r.text, timestamp: Date.now() });
  });

  const onPredict = () => guard("predict", async () => {
    const r = await api.predictFitted({
      kind: last.cmd_kind === "logit" ? "pr" : "xb",
      new_var: last.cmd_kind === "logit" ? "predicted_pr" : "fitted_values",
    });
    const refreshed = await api.columns();
    refreshColumns(refreshed.columns);
    if (dataset) {
      setDataset(
        { ...dataset, n_vars: refreshed.columns.length, columns: refreshed.columns.map((c) => c.name) },
        refreshed.columns,
      );
    }
    pushAnalyze({ command: r.command, kind: "predict", payload: r, text: r.text, timestamp: Date.now() });
  });

  const onTest = () => guard("test", async () => {
    if (!currentTestCoef) return;
    const r = await api.test([`${currentTestCoef} = 0`]);
    pushAnalyze({ command: r.command, kind: "test", payload: r, text: r.text, timestamp: Date.now() });
  });

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 pt-3 border-t border-border">
      <span className="text-[10px] uppercase tracking-[0.08em] text-text-faint mr-1">Postestimation</span>
      <button type="button" onClick={onMargins} disabled={busy !== ""} className="run-btn-secondary !w-auto !py-[6px] !px-3 !text-[12px] disabled:opacity-60">
        {busy === "margins" ? "Computing…" : "Margins"}
      </button>
      <button type="button" onClick={onPredict} disabled={busy !== ""} className="run-btn-secondary !w-auto !py-[6px] !px-3 !text-[12px] disabled:opacity-60">
        {busy === "predict" ? "Computing…" : last.cmd_kind === "logit" ? "Predict probability" : "Predict fitted"}
      </button>
      <div className="inline-flex items-center gap-1">
        <select
          value={currentTestCoef}
          onChange={(e) => setTestCoef(e.target.value)}
          className="bg-bg border border-border rounded-sm px-2 py-[6px] text-[11px] font-mono text-text"
        >
          {designCoefs.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <button type="button" onClick={onTest} disabled={busy !== "" || !currentTestCoef} className="run-btn-secondary !w-auto !py-[6px] !px-3 !text-[12px] disabled:opacity-60">
          {busy === "test" ? "Testing…" : `Test = 0`}
        </button>
      </div>
      {error && <span className="text-[11px] text-warn ml-2">{error}</span>}
    </div>
  );
}


// =====================================================================
// Tables / utilities
// =====================================================================

function CoefficientTable({ rows, columnLabel }: { rows: CoefRow[]; columnLabel: string }) {
  return (
    <div className="mt-4 bg-surface border border-border rounded-md overflow-hidden">
      <div className="flex items-center justify-between px-[14px] py-[10px] bg-surface-2 border-b border-border">
        <div className="font-serif italic text-[13px] text-text">Coefficient table</div>
      </div>
      <div className="p-[14px]">
        <table className="w-full font-mono text-[13px]">
          <thead className="text-text-muted text-[12px] uppercase tracking-[0.04em]">
            <tr>
              <th className="text-left py-2 pr-3 w-4"></th>
              <th className="text-left py-2 pr-4">Variable</th>
              <th className="text-right py-2 px-3">{columnLabel}</th>
              <th className="text-right py-2 px-3">SE</th>
              <th className="text-right py-2 px-3">{columnLabel === "OR" ? "z" : "t"}</th>
              <th className="text-right py-2 px-3">P</th>
              <th className="text-right py-2 px-3">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t border-border">
                <td className="py-[6px] pr-1 text-center">
                  {/* _cons is the baseline mean, not a hypothesis test in the
                      same sense as the predictors — suppress its dot. */}
                  {r.name === "_cons" ? <span className="inline-block w-[6px] h-[6px]" /> : <SignificanceDot p={r.p} />}
                </td>
                <td className="py-[6px] pr-3 text-text">{r.name}</td>
                <td className="text-right py-[6px] px-2 text-text">{fmt(r.coef)}</td>
                <td className="text-right py-[6px] px-2 text-text-muted">{fmt(r.se)}</td>
                <td className="text-right py-[6px] px-2 text-text-muted">{fmt(r.t ?? r.z, 2)}</td>
                <td className="text-right py-[6px] px-2 text-text-muted">{fmt(r.p, 4)}</td>
                <td className="text-right py-[6px] px-2 text-text-muted">
                  [{fmt(r.ci_low)}, {fmt(r.ci_high)}]
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HeaderGrid({ rows }: { rows: [string, string][] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 font-mono text-[12px]">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between">
          <span className="text-text-muted">{k}</span>
          <span className="text-text">{v}</span>
        </div>
      ))}
    </div>
  );
}

function SignificanceDot({ p }: { p: number | null }) {
  const sig = p != null && p < 0.05;
  return (
    <span
      className="inline-block w-[6px] h-[6px] rounded-full"
      style={{ background: sig ? "var(--accent)" : "transparent" }}
      aria-hidden
    />
  );
}

function CommandLine({ command }: { command: string }) {
  return (
    <div className="mt-3 px-[14px] py-2 bg-bg border border-border rounded-sm font-mono text-[11px] text-text-faint">
      <span className="text-text-faint mr-2">→</span>
      <span className="text-text">{command}</span>
    </div>
  );
}

// =====================================================================
// Form atoms
// =====================================================================

function FormRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block font-mono text-[11px] uppercase tracking-[0.08em] text-text-faint mb-2">
        {label}
      </label>
      {children}
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-bg border border-border rounded-sm px-3 py-2 text-[13px] font-mono text-text w-full max-w-[320px]"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

// =====================================================================
// Helpers
// =====================================================================

function fmt(n: number | null | undefined, digits = 4): string {
  if (n == null || Number.isNaN(n as number)) return "—";
  if (typeof n === "number" && Math.abs(n) >= 10_000) return n.toExponential(2);
  if (typeof n === "number" && Math.abs(n) < 0.0001 && n !== 0) return n.toExponential(2);
  return Number((n as number).toFixed(digits)).toString();
}

function formatFactor(p: FactorState, columns: ColumnInfo[]): string {
  const col = columns.find((c) => c.name === p.name);
  // auto: i. for binary/categorical, c. for numeric
  if (p.mode === "i") return `i.${p.name}`;
  if (p.mode === "c") return `c.${p.name}`;
  if (col?.kind === "binary" || col?.kind === "categorical") return `i.${p.name}`;
  return p.name;
}

function previewCommand(
  cmd: "regress" | "logit" | "logistic",
  depvar: string,
  indepvars: string[],
  opts: { robust?: boolean; cluster?: string; odds?: boolean } = {},
): string {
  if (!depvar || indepvars.length === 0) return `${cmd} <outcome> <predictors>`;
  let out = `${cmd} ${depvar} ${indepvars.join(" ")}`;
  const tail: string[] = [];
  if (opts.robust) tail.push("vce(robust)");
  if (opts.cluster) tail.push(`vce(cluster ${opts.cluster})`);
  if (tail.length) out += ", " + tail.join(" ");
  return out;
}
