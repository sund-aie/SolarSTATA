/* Visualize step.
 *
 * Chart-type picker + per-chart form. The picker uses the same
 * what/how/example Tooltip pattern as the Analyze step. Each chart
 * type filters its variable dropdowns by appropriate kind (histogram
 * X must be numeric, scatter X+Y both numeric, etc.). Run renders the
 * Plotly chart in a result card with a Pro-syntax footer.
 */

import { useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { ColumnInfo, VarKind } from "../lib/types";
import { lastOnewayPosthoc, type OnewayPosthocBlock } from "../lib/posthoc";
import { useApp } from "../state/store";
import { CommandPreview } from "../components/CommandPreview";
import { ResultsCard } from "../components/ResultsCard";
import { Tooltip } from "../components/Tooltip";
import { Plot, type PlotlyFigure } from "../components/Plot";

type ChartKind =
  | "histogram" | "scatter" | "box" | "bar" | "line" | "residuals" | "marginsplot";

interface ChartDef {
  id: ChartKind;
  label: string;
  icon: string;
  what: string;
  how: string;
  example: React.ReactNode;
  needsLastEstimation?: boolean;
}

const CHARTS: ChartDef[] = [
  {
    id: "histogram", label: "Histogram", icon: "▮▮▆▃▁",
    what: "Distribution of a single numeric variable — how often each value range occurs.",
    how: "Pick a numeric X. Optionally group by a categorical to overlay distributions.",
    example: <>X = <code className="font-mono">plaque_index</code> shows a right-skewed Silness–Löe spread.</>,
  },
  {
    id: "scatter", label: "Scatter", icon: "··· ⋰⋱",
    what: "Two-variable cloud — relationship between X and Y, one dot per observation.",
    how: "Pick numeric X and Y. Group colours by a categorical if you'd like.",
    example: <>X = <code className="font-mono">age</code>, Y = <code className="font-mono">periodontal_pocket_depth_mm</code>: rising trend.</>,
  },
  {
    id: "box", label: "Box plot", icon: "├─┬─┤",
    what: "Five-number summary per group: min / Q1 / median / Q3 / max with mean marker.",
    how: "Pick a numeric Y. Group by a categorical to compare distributions side-by-side.",
    example: <>Y = <code className="font-mono">plaque_index</code>, by <code className="font-mono">smoking</code>.</>,
  },
  {
    id: "bar", label: "Bar (mean ± CI)", icon: "█│",
    what: "Group means with 95% confidence intervals. Quick eyeball of effect size.",
    how: "Pick a numeric outcome and a categorical to group on.",
    example: <>Mean <code className="font-mono">plaque_index</code> by <code className="font-mono">education_level</code>.</>,
  },
  {
    id: "line", label: "Line", icon: "╱╲╱",
    what: "Connected dots in X-order. Useful for time-like or ordered variables.",
    how: "Pick X (numeric, usually ordered) and Y (numeric). Group optional.",
    example: <>X = <code className="font-mono">last_visit_months</code>, Y = <code className="font-mono">plaque_index</code>.</>,
  },
  {
    id: "residuals", label: "Residuals", icon: "ⵙ",
    what: "Residuals-vs-fitted scatter — diagnostic for linearity and heteroskedasticity.",
    how: "Run a regression first; then click here. No other inputs needed.",
    example: <>After <code className="font-mono">regress plaque_index age brushing_freq</code>: should look like random noise around y=0.</>,
    needsLastEstimation: true,
  },
  {
    id: "marginsplot", label: "Marginsplot", icon: "│·│·│",
    what: "Average marginal effects with 95% CIs, one dot per predictor.",
    how: "Run a regression or logit first; then click here.",
    example: <>After <code className="font-mono">logistic caries smoking</code>: AME for smoking ≈ +0.10 ± CI.</>,
    needsLastEstimation: true,
  },
];

interface Rendered {
  kind: ChartKind;
  command: string;
  figure: PlotlyFigure;
  timestamp: number;
}

export function VisualizeStep() {
  const dataset = useApp((s) => s.dataset);
  const columns = useApp((s) => s.columns);
  const lastEstimation = useApp((s) => s.lastEstimation);
  const appendCommand = useApp((s) => s.appendCommand);

  const [pick, setPick] = useState<ChartKind>("histogram");
  const [rendered, setRendered] = useState<Rendered[]>([]);

  if (!dataset) return null;

  const handleRendered = (r: Rendered) => {
    setRendered((prev) => [r, ...prev].slice(0, 6));
    appendCommand(r.command);
  };

  const activeDef = CHARTS.find((c) => c.id === pick)!;

  return (
    <div className="overflow-y-auto px-10 py-8 pb-20">
      <div className="mb-8">
        <div className="eyebrow mb-2">Step 5 of 6</div>
        <h1 className="font-serif text-[32px] leading-[1.15] text-text tracking-[-0.01em] mb-1">
          Plot your <em className="text-accent italic">data</em>
        </h1>
        <p className="text-text-muted text-[14px] max-w-[520px]">
          Pick a chart type and fill in the form. Every plot shows the equivalent
          Stata <code className="font-mono">graph …</code> syntax — copy it once you've
          built the muscle memory.
        </p>
      </div>

      <div className="grid gap-2 max-w-[820px]" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
        {CHARTS.map((c) => {
          const active = pick === c.id;
          const disabled = c.needsLastEstimation && !lastEstimation;
          return (
            <Tooltip key={c.id} what={c.what} how={c.how} example={c.example}>
              <button
                type="button"
                onClick={() => !disabled && setPick(c.id)}
                disabled={disabled}
                className={`text-left p-3 rounded-md border transition-colors ${
                  active
                    ? "bg-accent-soft border-accent text-text"
                    : "bg-surface border-border text-text-muted hover:text-text hover:border-border-strong"
                } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
              >
                <div className="font-mono text-[13px] text-accent mb-1">{c.icon}</div>
                <div className="text-[13px] font-medium">{c.label}</div>
                {disabled && (
                  <div className="text-[10px] text-text-faint mt-1 font-mono">needs an estimation</div>
                )}
              </button>
            </Tooltip>
          );
        })}
      </div>

      <div className="mt-6 max-w-[820px]">
        <ChartForm key={pick} chart={activeDef} columns={columns} onRendered={handleRendered} />
      </div>

      {rendered.length > 0 && (
        <div className="mt-10 max-w-[820px]">
          <div className="eyebrow mb-3">Recent plots</div>
          <div className="space-y-4">
            {rendered.map((r) => (
              <ResultsCard key={r.timestamp} title={CHARTS.find((c) => c.id === r.kind)?.label ?? r.kind}>
                <Plot figure={r.figure} height={380} />
                <div className="mt-2 text-[11px] text-text-faint font-mono">{r.command}</div>
              </ResultsCard>
            ))}
          </div>
          <CommandPreview command={rendered[0].command} />
        </div>
      )}
    </div>
  );
}

// =====================================================================
// Per-chart forms
// =====================================================================

/** True for any column whose underlying pandas dtype is numeric. We can't
 * gate scatter/line axes on `kind === "numeric"` alone — integer-coded
 * categoricals like timepoint (1/2/3) and group_id are perfectly usable
 * on an axis. */
const dtypeIsNumeric = (dtype: string): boolean =>
  /^(int|uint|float|bool)/i.test(dtype);

function ChartForm({
  chart,
  columns,
  onRendered,
}: {
  chart: ChartDef;
  columns: ColumnInfo[];
  onRendered: (r: Rendered) => void;
}) {
  // Histogram / box / bar still want continuous-shaped variables.
  const numerics = useMemo(() => columns.filter((c) => c.kind === "numeric"), [columns]);
  // Scatter / line accept anything numerically-encoded.
  const axisEligible = useMemo(
    () => columns.filter((c) => dtypeIsNumeric(c.dtype)),
    [columns],
  );
  const categoricals = useMemo(
    () => columns.filter((c) => c.kind === "binary" || c.kind === "categorical"),
    [columns],
  );

  return (
    <div className="bg-surface border border-border rounded-md p-6">
      {needsContinuous(chart.id) && numerics.length === 0 ? (
        <NeedsContinuousEmptyState columns={columns} chart={chart} />
      ) : (
        <>
          {chart.id === "histogram" && <HistogramForm numerics={numerics} categoricals={categoricals} onRendered={onRendered} />}
          {chart.id === "scatter" && <XYForm chart="scatter" numerics={axisEligible} categoricals={categoricals} onRendered={onRendered} />}
          {chart.id === "box" && <SingleYForm chart="box" numerics={numerics} categoricals={categoricals} onRendered={onRendered} />}
          {chart.id === "bar" && <SingleYForm chart="bar" numerics={numerics} categoricals={categoricals} onRendered={onRendered} />}
          {chart.id === "line" && <XYForm chart="line" numerics={axisEligible} categoricals={categoricals} onRendered={onRendered} />}
          {chart.id === "residuals" && <NoInputForm chart="residuals" onRendered={onRendered} />}
          {chart.id === "marginsplot" && <NoInputForm chart="marginsplot" onRendered={onRendered} />}
        </>
      )}
    </div>
  );
}

/* Histogram, box, and bar all plot the distribution or mean of a
 * continuous variable. For an all-categorical dataset (e.g. a
 * pre/post quiz of binary 0/1 columns) the legacy forms rendered
 * an empty dropdown + dead Run button — a clear bug. */
function needsContinuous(id: ChartKind): boolean {
  return id === "histogram" || id === "box" || id === "bar";
}

/* Empty state surfaced when the user picks histogram/box/bar against
 * a dataset with no numeric-kind columns. Reads the actual columns
 * array to name what kinds ARE present, then points at the Counts
 * chart that handles the categorical-data case. Exported for tests. */
export function NeedsContinuousEmptyState({
  columns,
  chart,
}: {
  columns: ColumnInfo[];
  chart: ChartDef;
}) {
  const present = countKindsPresent(columns);
  const summary = humaniseList(present);
  return (
    <div className="space-y-3 max-w-[560px]">
      <div className="eyebrow">Counts and proportions instead</div>
      <h2 className="font-serif text-[22px] leading-tight text-text">
        Your dataset has no{" "}
        <em className="text-accent italic">continuous</em> variables.
      </h2>
      <p className="text-text text-[13px] leading-relaxed">
        {chart.label} plots a measurement — a column whose values are
        quantities like mean plaque index or blood pressure.
        {summary && (
          <> This dataset has {summary}, no measurements.</>
        )}
      </p>
      <p className="text-text text-[13px] leading-relaxed">
        For counts and proportions across categories, switch to the{" "}
        <strong className="text-accent">Counts</strong> chart above.
      </p>
    </div>
  );
}

const KIND_LABEL: Record<VarKind, string> = {
  binary:      "binary",
  categorical: "categorical",
  numeric:     "numeric",
  string:      "text",
  id:          "id",
};

function countKindsPresent(columns: ColumnInfo[]): string[] {
  const tally: Partial<Record<VarKind, number>> = {};
  for (const c of columns) {
    tally[c.kind] = (tally[c.kind] ?? 0) + 1;
  }
  // Ordered most-relevant-first so the message reads naturally.
  // `numeric` is omitted on purpose — the empty state only shows
  // when there are zero of them.
  const order: VarKind[] = ["binary", "categorical", "id", "string"];
  const parts: string[] = [];
  for (const k of order) {
    const n = tally[k];
    if (n) parts.push(`${n} ${KIND_LABEL[k]}`);
  }
  return parts;
}

function humaniseList(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0]!;
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return items.slice(0, -1).join(", ") + ", and " + items[items.length - 1]!;
}

function HistogramForm({
  numerics, categoricals, onRendered,
}: { numerics: ColumnInfo[]; categoricals: ColumnInfo[]; onRendered: (r: Rendered) => void }) {
  const [varName, setVarName] = useState(numerics[0]?.name ?? "");
  const [group, setGroup] = useState("");
  const [bins, setBins] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const command = `histogram ${varName}, bin(${bins})${group ? ` by(${group})` : ""}`;

  return (
    <div className="space-y-4">
      <FormRow label="Variable (numeric)">
        <Select value={varName} onChange={setVarName} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Bins">
        <input
          type="number"
          min={2}
          max={200}
          value={bins}
          onChange={(e) => setBins(Math.max(2, Math.min(200, Number(e.target.value) || 20)))}
          className="bg-bg border border-border rounded-sm px-3 py-2 text-[13px] font-mono text-text w-[120px]"
        />
      </FormRow>
      <FormRow label="Group by (optional)">
        <Select
          value={group}
          onChange={setGroup}
          options={[{ value: "", label: "— none —" }, ...categoricals.map((c) => ({ value: c.name, label: c.name }))]}
        />
      </FormRow>
      <RunButton command={command} busy={busy} disabled={!varName} onClick={async () => {
        setBusy(true); setError(null);
        try {
          const r = await api.graph("histogram", { var: varName, bins, group: group || null });
          onRendered({ kind: "histogram", command: r.command, figure: r.figure, timestamp: Date.now() });
        } catch (e) { setError(e instanceof ApiError ? e.detail : String(e)); }
        finally { setBusy(false); }
      }} />
      {error && <div className="text-[12px] text-warn">{error}</div>}
    </div>
  );
}

function XYForm({
  chart, numerics, categoricals, onRendered,
}: { chart: "scatter" | "line"; numerics: ColumnInfo[]; categoricals: ColumnInfo[]; onRendered: (r: Rendered) => void }) {
  const [x, setX] = useState(numerics[0]?.name ?? "");
  const [y, setY] = useState(numerics[1]?.name ?? numerics[0]?.name ?? "");
  const [group, setGroup] = useState("");
  const [err, setErr] = useState<ErrSource>("none");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const command = chart === "scatter"
    ? `scatter ${y} ${x}${group ? `, by(${group})` : ""}`
    : `twoway line ${y} ${x}${group ? `, by(${group})` : ""}`;

  return (
    <div className="space-y-4">
      <FormRow label="X (numeric)">
        <Select value={x} onChange={setX} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Y (numeric)">
        <Select value={y} onChange={setY} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Group by (optional)">
        <Select
          value={group}
          onChange={setGroup}
          options={[{ value: "", label: "— none —" }, ...categoricals.map((c) => ({ value: c.name, label: c.name }))]}
        />
      </FormRow>
      {chart === "line" && (
        <ErrorBarRow value={err} onChange={setErr} />
      )}
      <RunButton command={command} busy={busy} disabled={!x || !y} onClick={async () => {
        setBusy(true); setError(null);
        try {
          const body: Record<string, unknown> = { x, y, group: group || null };
          if (chart === "line") body.err = err;
          const r = await api.graph(chart, body);
          onRendered({ kind: chart, command: r.command, figure: r.figure, timestamp: Date.now() });
        } catch (e) { setError(e instanceof ApiError ? e.detail : String(e)); }
        finally { setBusy(false); }
      }} />
      {error && <div className="text-[12px] text-warn">{error}</div>}
    </div>
  );
}

function SingleYForm({
  chart, numerics, categoricals, onRendered,
}: { chart: "box" | "bar"; numerics: ColumnInfo[]; categoricals: ColumnInfo[]; onRendered: (r: Rendered) => void }) {
  const [varName, setVarName] = useState(numerics[0]?.name ?? "");
  const [group, setGroup] = useState(categoricals[0]?.name ?? "");
  // B1: sub-group support for bar charts (the canonical "8 groups × 3
  // timepoints = 24 bars" repeated-measures figure). Off by default.
  const [subgroup, setSubgroup] = useState("");
  const [err, setErr] = useState<ErrSource>("ci95");
  const [showBrackets, setShowBrackets] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Significance brackets — only available on single-group bar
  // charts AND only when the user has already run a matching oneway
  // with posthoc enabled. We render what the engine already
  // computed; no new statistics here.
  const analyzeRecords = useApp((s) => s.analyzeRecords);
  const matchingPosthoc: OnewayPosthocBlock | null = useMemo(
    () => (chart === "bar" && varName && group
      ? lastOnewayPosthoc(analyzeRecords, varName, group)
      : null),
    [chart, varName, group, analyzeRecords],
  );
  const bracketsDisabledByGrouping = Boolean(subgroup);
  const bracketsActive = chart === "bar" && !!matchingPosthoc && showBrackets && !bracketsDisabledByGrouping;

  const command = chart === "box"
    ? `graph box ${varName}${group ? `, over(${group})` : ""}`
    : subgroup && group
      ? `graph bar (mean) ${varName}, over(${subgroup}) over(${group}) asyvars`
      : `graph bar (mean) ${varName}${group ? `, over(${group})` : ""}`;

  return (
    <div className="space-y-4">
      <FormRow label="Variable (numeric)">
        <Select value={varName} onChange={setVarName} options={numerics.map((c) => ({ value: c.name, label: c.name }))} />
      </FormRow>
      <FormRow label="Group by (categorical)">
        <Select
          value={group}
          onChange={setGroup}
          options={[{ value: "", label: "— none —" }, ...categoricals.map((c) => ({ value: c.name, label: c.name }))]}
        />
      </FormRow>
      {chart === "bar" && (
        <FormRow label="Sub-group by (optional, for clustered bars)">
          <Select
            value={subgroup}
            onChange={setSubgroup}
            options={[
              { value: "", label: "— none (single-level bars) —" },
              ...categoricals
                .filter((c) => c.name !== group)
                .map((c) => ({ value: c.name, label: c.name })),
            ]}
          />
        </FormRow>
      )}
      {chart === "bar" && (
        <ErrorBarRow value={err} onChange={setErr} />
      )}
      {chart === "bar" && matchingPosthoc && (
        <BracketsRow
          method={matchingPosthoc.method}
          checked={showBrackets}
          onChange={setShowBrackets}
          disabled={bracketsDisabledByGrouping}
          disabledReason={bracketsDisabledByGrouping
            ? "Brackets apply to single-group comparisons."
            : undefined}
        />
      )}
      <RunButton command={command} busy={busy} disabled={!varName} onClick={async () => {
        setBusy(true); setError(null);
        try {
          const body: Record<string, unknown> = { var: varName, group: group || null };
          if (chart === "bar" && subgroup) body.subgroup = subgroup;
          if (chart === "bar") body.err = err;
          if (bracketsActive && matchingPosthoc) body.pairwise = matchingPosthoc;
          const r = await api.graph(chart, body);
          onRendered({ kind: chart, command: r.command, figure: r.figure, timestamp: Date.now() });
        } catch (e) { setError(e instanceof ApiError ? e.detail : String(e)); }
        finally { setBusy(false); }
      }} />
      {error && <div className="text-[12px] text-warn">{error}</div>}
    </div>
  );
}

type ErrSource = "none" | "sd" | "sem" | "ci95";

const ERR_OPTIONS: { value: ErrSource; label: string }[] = [
  { value: "none", label: "— none —" },
  { value: "sd",   label: "SD (sample standard deviation)" },
  { value: "sem",  label: "SEM (standard error of the mean)" },
  { value: "ci95", label: "95% CI" },
];

function ErrorBarRow({
  value, onChange,
}: { value: ErrSource; onChange: (v: ErrSource) => void }) {
  return (
    <FormRow label="Error bars">
      <Select
        value={value}
        onChange={(v) => onChange(v as ErrSource)}
        options={ERR_OPTIONS}
      />
    </FormRow>
  );
}

function BracketsRow({
  method, checked, onChange, disabled, disabledReason,
}: {
  method: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled: boolean;
  disabledReason?: string;
}) {
  return (
    <FormRow label="Significance brackets">
      <label className={`flex items-center gap-2 text-[13px] ${disabled ? "text-text-faint" : "text-text"}`}>
        <input
          type="checkbox"
          checked={checked && !disabled}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>
          Show {method} brackets (
          <span className="font-mono">*</span> /
          <span className="font-mono"> **</span> /
          <span className="font-mono"> ***</span>
          {" "}at <span className="font-mono">p &lt; .05 / .01 / .001</span>)
        </span>
      </label>
      {disabled && disabledReason && (
        <div className="text-[11px] text-text-muted italic mt-1">{disabledReason}</div>
      )}
    </FormRow>
  );
}

function NoInputForm({
  chart, onRendered,
}: { chart: "residuals" | "marginsplot"; onRendered: (r: Rendered) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const command = chart === "residuals" ? "rvfplot" : "marginsplot";

  return (
    <div className="space-y-4">
      <p className="text-[13px] text-text-muted">
        Uses your most recent regression/logit. No other inputs needed.
      </p>
      <RunButton command={command} busy={busy} disabled={false} onClick={async () => {
        setBusy(true); setError(null);
        try {
          const r = await api.graph(chart);
          onRendered({ kind: chart, command: r.command, figure: r.figure, timestamp: Date.now() });
        } catch (e) { setError(e instanceof ApiError ? e.detail : String(e)); }
        finally { setBusy(false); }
      }} />
      {error && <div className="text-[12px] text-warn">{error}</div>}
    </div>
  );
}

// =====================================================================
// Atoms
// =====================================================================

function RunButton({
  command, busy, disabled, onClick,
}: { command: string; busy: boolean; disabled: boolean; onClick: () => void }) {
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled || busy}
        className="run-btn-primary disabled:opacity-60"
      >
        {busy ? "Rendering…" : "Render chart"}
      </button>
      <div className="text-[11px] text-text-faint font-mono">Pro syntax: {command}</div>
    </div>
  );
}

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
  value, onChange, options,
}: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
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

// Suppress unused-import lint (VarKind needed for some downstream filter logic later).
export type _KindHelper = VarKind;
