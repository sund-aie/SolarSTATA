/* Analyze step: categorized analysis menu + inline forms + result cards.
 *
 * Phase 3 fills in:
 *   - Regression: OLS, Logit (with odds ratios, robust/cluster SE)
 *   - Postestimation: Margins (AME), Predict (fitted values), Test (= 0)
 *
 * Descriptives and Comparisons categories are visible but stubbed to redirect
 * to the Inspect step or later phases.
 */

import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type {
  CoefRow,
  ColumnInfo,
  LogitResponse,
  MarginsResponse,
  PredictResponse,
  RegressResponse,
  TestResponse,
} from "../lib/types";
import { useApp } from "../state/store";
import { CommandPreview } from "../components/CommandPreview";
import { ResultsCard } from "../components/ResultsCard";

type Category = "descriptives" | "comparisons" | "regression" | "postest";

type RegressionPick = "ols" | "logit";

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

  if (!dataset) return null;

  return (
    <div className="overflow-y-auto px-10 py-8 pb-20">
      <div className="mb-8">
        <div className="eyebrow mb-2">Step 4 of 6</div>
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
          <CategoryHint
            heading="Descriptives live in Inspect"
            body="Click any variable card on the Inspect step for one-variable descriptives, or use Pro mode for `summarize` / `tabulate` directly."
          />
        )}

        {category === "comparisons" && (
          <CategoryHint
            heading="t-tests / ANOVA arrive in Phase 3.1"
            body="Phase 3 ships Regression and Postestimation. Comparisons (t-test, ANOVA, chi²) is the next slice."
          />
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

  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const setLast = useApp((s) => s.setLastEstimation);

  const indepvars = predictors.map((p) => formatFactor(p, allCols));

  const onRun = async () => {
    if (!depvar || predictors.length === 0) return;
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
        <button
          type="button"
          disabled={busy || !depvar || predictors.length === 0}
          onClick={onRun}
          className="run-btn-primary disabled:opacity-60"
        >
          {busy ? "Fitting…" : "Run regression"}
        </button>
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

  const pushAnalyze = useApp((s) => s.pushAnalyzeRecord);
  const setLast = useApp((s) => s.setLastEstimation);

  const indepvars = predictors.map((p) => formatFactor(p, allCols));

  const onRun = async () => {
    if (!depvar || predictors.length === 0) return;
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
        <button
          type="button"
          disabled={busy || !depvar || predictors.length === 0}
          onClick={onRun}
          className="run-btn-primary disabled:opacity-60"
        >
          {busy ? "Fitting…" : oddsRatios ? "Run logistic" : "Run logit"}
        </button>
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
  const addable = columns.filter((c) => !inUse.has(c.name) && c.kind !== "id" && c.kind !== "string");

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
        <button type="button" onClick={onMargins} disabled={busy !== ""} className="run-btn-secondary !w-auto disabled:opacity-60">
          {busy === "margins" ? "Computing…" : "Margins (AME)"}
        </button>
        <button type="button" onClick={onPredict} disabled={busy !== ""} className="run-btn-secondary !w-auto disabled:opacity-60">
          {busy === "predict" ? "Computing…" : last.cmd_kind === "logit" ? "Predict probability" : "Predict fitted"}
        </button>
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
          <button type="button" onClick={onTest} disabled={busy !== "" || !testCoef} className="run-btn-secondary !w-auto disabled:opacity-60">
            {busy === "test" ? "Testing…" : `Test ${testCoef} = 0`}
          </button>
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
  return (
    <ResultsCard title={COMMAND_LABELS[record.kind] ?? record.kind}>
      <pre className="font-mono text-[11px] text-text-muted whitespace-pre">{record.text}</pre>
    </ResultsCard>
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
// Tables / utilities
// =====================================================================

function CoefficientTable({ rows, columnLabel }: { rows: CoefRow[]; columnLabel: string }) {
  return (
    <div className="mt-4 bg-surface border border-border rounded-md overflow-hidden">
      <div className="flex items-center justify-between px-[14px] py-[10px] bg-surface-2 border-b border-border">
        <div className="font-serif italic text-[13px] text-text">Coefficient table</div>
      </div>
      <div className="p-[14px]">
        <table className="w-full font-mono text-[12px]">
          <thead className="text-text-muted">
            <tr>
              <th className="text-left py-1 pr-3 w-4"></th>
              <th className="text-left py-1 pr-3">Variable</th>
              <th className="text-right py-1 px-2">{columnLabel}</th>
              <th className="text-right py-1 px-2">SE</th>
              <th className="text-right py-1 px-2">{columnLabel === "OR" ? "z" : "t"}</th>
              <th className="text-right py-1 px-2">P</th>
              <th className="text-right py-1 px-2">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t border-border">
                <td className="py-[6px] pr-1 text-center">
                  <SignificanceDot p={r.p} />
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
