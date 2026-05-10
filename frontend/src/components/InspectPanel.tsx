/* Right-rail Inspect panel:
 *   header (eyebrow / var name / serif label)
 *   2x2 stats (Type / Obs / Missing / Range)
 *   distribution histogram with axis labels
 *   "Run summarize" + result card, then "Run summarize, detail"
 *   sticky "Pro command equivalent" footer
 */

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { summarizeKey, useApp } from "../state/store";
import type { ColumnInfo, HistogramResponse, SummarizeResult } from "../lib/types";
import { CommandPreview } from "./CommandPreview";
import { ResultsCard, ResultRow } from "./ResultsCard";
import { Tooltip } from "./Tooltip";

interface Props {
  info: ColumnInfo;
}

export function InspectPanel({ info }: Props) {
  const summarizeCache = useApp((s) => s.summarizeCache);
  const setSummarize = useApp((s) => s.setSummarize);
  const appendCommand = useApp((s) => s.appendCommand);

  const [hist, setHist] = useState<HistogramResponse | null>(null);
  const [busy, setBusy] = useState<"" | "summary" | "detail">("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setHist(null);
    api
      .histogram(info.name, 15)
      .then((r) => {
        if (!cancelled) setHist(r);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [info.name]);

  const summaryKey = summarizeKey([info.name], false);
  const detailKey = summarizeKey([info.name], true);
  const summaryResult: SummarizeResult | undefined = summarizeCache[summaryKey];
  const detailResult: SummarizeResult | undefined = summarizeCache[detailKey];

  const runSummarize = async (detail: boolean) => {
    setBusy(detail ? "detail" : "summary");
    setError(null);
    try {
      const r = await api.summarize([info.name], detail);
      setSummarize(detail ? detailKey : summaryKey, r);
      appendCommand(r.command);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy("");
    }
  };

  const range = formatRange(hist, info);
  const command = `summarize ${info.name}`;

  return (
    <aside className="border-l border-border bg-bg flex flex-col overflow-y-auto">
      <div className="px-6 pt-6 pb-5 border-b border-border">
        <div className="eyebrow mb-[6px]">Inspecting</div>
        <div className="font-mono text-[18px] text-text mb-1 font-medium">{info.name}</div>
        <div className="font-serif italic text-[14px] text-text-muted">
          {info.label || labelFromKind(info)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-px bg-border border-b border-border">
        <Stat label="Type" value={<>{info.kind}<span className="ml-1 text-[11px] text-text-muted">{info.dtype}</span></>} />
        <Stat label="Observations" value={<>{info.n} <span className="text-[11px] text-text-muted">/ {info.n + info.n_missing}</span></>} />
        <Stat
          label="Missing"
          value={<span style={{ color: info.n_missing > 0 ? "var(--warn)" : undefined }}>{info.n_missing} <span className="text-[11px] text-text-muted">{info.missing_pct}%</span></span>}
        />
        <Stat label="Range" value={range} />
      </div>

      <div className="px-6 py-6 border-b border-border">
        <div className="eyebrow mb-3">Distribution</div>
        {hist ? <PanelHistogram data={hist} /> : <div className="h-[72px] flex items-center text-text-faint text-[12px]">loading…</div>}
        {hist && (
          <div className="flex justify-between font-mono text-[10px] text-text-faint mt-[6px]">
            <span>{formatNum(hist.min)}</span>
            <span>{hist.mean != null ? `${formatNum(hist.mean)} (mean)` : ""}</span>
            <span>{formatNum(hist.max)}</span>
          </div>
        )}
      </div>

      <div className="px-6 py-6 border-b border-border">
        <Tooltip
          what="Computes mean, standard deviation, min, and max for the selected variable."
          how="Click once. The result card appears below with N (non-missing observations) and the four summary statistics."
          example={<>For <code className="font-mono">plaque_index</code>: Mean ≈ 1.44, SD ≈ 0.58 — typical for a Silness–Löe score on a healthy-leaning population.</>}
        >
          <button
            type="button"
            onClick={() => runSummarize(false)}
            disabled={busy !== ""}
            className="run-btn-primary disabled:opacity-60"
          >
            {busy === "summary" ? "Running…" : "Run summarize"}
          </button>
        </Tooltip>

        {summaryResult && summaryResult.result.variables[0] && (
          <ResultsCard title="Summary statistics">
            <SummaryRows row={summaryResult.result.variables[0]} />
          </ResultsCard>
        )}

        <Tooltip
          what="Adds variance, skewness, kurtosis, and the 1/5/10/25/50/75/90/95/99 percentiles."
          how="Click after the basic summary if you need distribution shape — useful before deciding on a normal-vs-non-parametric test."
          example={<>Skewness near 0 and kurtosis near 3 ⇒ approximately normal. <code className="font-mono">plaque_index</code> typically skews right (more low-plaque patients than high).</>}
        >
          <button
            type="button"
            onClick={() => runSummarize(true)}
            disabled={busy !== ""}
            className="run-btn-secondary mt-[10px] disabled:opacity-60"
          >
            {busy === "detail" ? "Running…" : "Run summarize, detail"}
          </button>
        </Tooltip>

        {detailResult && detailResult.result.variables[0] && (
          <ResultsCard title="Summary statistics, detail">
            <SummaryRows row={detailResult.result.variables[0]} detail />
          </ResultsCard>
        )}

        {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
      </div>

      <CommandPreview command={command} />
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="px-6 py-[14px] bg-bg">
      <div className="font-mono text-[10px] text-text-faint uppercase tracking-[0.08em] mb-1">
        {label}
      </div>
      <div className="font-mono text-[15px] text-text font-medium">{value}</div>
    </div>
  );
}

function PanelHistogram({ data }: { data: HistogramResponse }) {
  const max = Math.max(1, ...data.bins);
  return (
    <div className="h-[72px] flex items-end gap-[2px]">
      {data.bins.map((v, i) => (
        <div
          key={i}
          className="flex-1 min-h-[3px] rounded-t-[2px]"
          style={{
            height: `${(v / max) * 100}%`,
            background: "linear-gradient(to top, var(--accent), rgba(212, 179, 106, 0.55))",
          }}
        />
      ))}
    </div>
  );
}

function SummaryRows({ row, detail = false }: { row: NonNullable<SummarizeResult["result"]["variables"][number]>; detail?: boolean }) {
  return (
    <>
      <ResultRow k="Obs" v={row.Obs ?? "—"} />
      <ResultRow k="Mean" v={fmt(row.Mean)} />
      <ResultRow k="Std. dev." v={fmt(row.SD)} />
      <ResultRow k="Min" v={fmt(row.Min)} />
      <ResultRow k="Max" v={fmt(row.Max)} />
      {detail && (
        <>
          <ResultRow k="Variance" v={fmt(row.Variance)} />
          <ResultRow k="Skewness" v={fmt(row.Skewness)} />
          <ResultRow k="Kurtosis" v={fmt(row.Kurtosis)} />
          <ResultRow k="p25" v={fmt(row.p25)} />
          <ResultRow k="p50" v={fmt(row.p50)} />
          <ResultRow k="p75" v={fmt(row.p75)} />
        </>
      )}
    </>
  );
}

function fmt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 10_000 || Math.abs(n) < 0.001) return n.toExponential(3);
  return Number(n.toFixed(6)).toString();
}

function formatNum(n: number | null | undefined): string {
  if (n == null) return "—";
  return Number(n.toFixed(2)).toString();
}

function formatRange(hist: HistogramResponse | null, info: ColumnInfo): React.ReactNode {
  if (info.kind === "binary" || info.kind === "categorical") {
    return `${info.n_unique} cats`;
  }
  if (!hist || hist.min == null || hist.max == null) return "—";
  return `${formatNum(hist.min)} → ${formatNum(hist.max)}`;
}

function labelFromKind(info: ColumnInfo): string {
  switch (info.kind) {
    case "id": return "Identifier";
    case "binary": return "Binary indicator";
    case "categorical": return `${info.n_unique} categories`;
    case "numeric": return "Numeric";
    case "string": return "String";
  }
}
