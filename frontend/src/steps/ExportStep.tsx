/* Export step.
 *
 * Three cards:
 *   - Dataset export (.csv / .xlsx / .dta / .parquet)
 *   - Do-file export (every command run this session)
 *   - Research report (PDF or HTML rendered from history)
 */

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useApp } from "../state/store";
import { Tooltip } from "../components/Tooltip";

type DataFmt = "csv" | "xlsx" | "dta" | "parquet";
type ReportFmt = "pdf" | "html";

interface Capabilities {
  pdf: boolean;
  pdf_unavailable_reason: string | null;
}

export function ExportStep() {
  const dataset = useApp((s) => s.dataset);
  const history = useApp((s) => s.commandHistory);
  const [capabilities, setCapabilities] = useState<Capabilities>({
    pdf: true, pdf_unavailable_reason: null,
  });

  useEffect(() => {
    api.exportCapabilities()
      .then((c) => setCapabilities({ pdf: c.pdf, pdf_unavailable_reason: c.pdf_unavailable_reason }))
      .catch(() => {
        // Fall back to optimistic UI — server will return 503 if PDF really
        // isn't available and the report card surfaces that error.
      });
  }, []);

  if (!dataset) return null;

  return (
    <div className="overflow-y-auto px-10 py-8 pb-20">
      <div className="mb-8">
        <div className="eyebrow mb-2">Step 6 of 6</div>
        <h1 className="font-serif text-[32px] leading-[1.15] text-text tracking-[-0.01em] mb-1">
          Get your <em className="text-accent italic">work out</em>
        </h1>
        <p className="text-text-muted text-[14px] max-w-[520px]">
          Save the dataset for collaborators, export your session as a Stata do-file so
          everything is reproducible, or generate a research report PDF.
        </p>
      </div>

      <div className="grid gap-5 max-w-[820px]" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        <DatasetCard filename={dataset.filename} />
        <DoFileCard nCommands={history.length} />
        <ReportCard nCommands={history.length} capabilities={capabilities} />
      </div>
    </div>
  );
}

// =====================================================================
// Dataset card
// =====================================================================

function DatasetCard({ filename }: { filename: string }) {
  const [busy, setBusy] = useState<DataFmt | "">("");
  const [error, setError] = useState<string | null>(null);

  const onDownload = async (fmt: DataFmt) => {
    setBusy(fmt); setError(null);
    try {
      const blob = await api.downloadDataset(fmt);
      const stem = filename.replace(/\.[^.]+$/, "");
      triggerDownload(blob, `${stem}.${fmt}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="bg-surface border border-border rounded-md p-5">
      <div className="font-serif italic text-[16px] text-text mb-2">Dataset</div>
      <div className="text-[12px] text-text-muted mb-4">
        Snapshot the current frame, including any variables you've generated this session
        (predicted values, residuals, etc.).
      </div>
      <div className="grid grid-cols-2 gap-2">
        {(["csv", "xlsx", "dta", "parquet"] as DataFmt[]).map((fmt) => (
          <Tooltip
            key={fmt}
            what={fmtTip(fmt).what}
            how="Click to download. Saves to your browser's default folder."
            example={fmtTip(fmt).example}
          >
            <button
              type="button"
              onClick={() => onDownload(fmt)}
              disabled={busy !== ""}
              className="run-btn-secondary !w-full disabled:opacity-60"
            >
              {busy === fmt ? "Saving…" : `.${fmt}`}
            </button>
          </Tooltip>
        ))}
      </div>
      {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
    </div>
  );
}

function fmtTip(fmt: DataFmt) {
  switch (fmt) {
    case "csv": return { what: "Plain CSV. Universal, but loses labels and storage types.", example: "Best for sharing with non-Stata users." };
    case "xlsx": return { what: "Excel workbook. Loses Stata-specific metadata but opens anywhere.", example: "For collaborators who live in Excel." };
    case "dta": return { what: "Stata native .dta. Keeps variable labels, value labels, and storage types.", example: "Best for round-tripping into Stata 19 itself." };
    case "parquet": return { what: "Columnar binary. Fast, compact, ideal for big datasets and Python/DuckDB workflows.", example: "Best for analytical pipelines downstream." };
  }
}

// =====================================================================
// Do-file card
// =====================================================================

function DoFileCard({ nCommands }: { nCommands: number }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onDownload = async () => {
    setBusy(true); setError(null);
    try {
      const blob = await api.downloadDoFile();
      triggerDownload(blob, "session.do");
    } catch (e) { setError(e instanceof ApiError ? e.detail : String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="bg-surface border border-border rounded-md p-5">
      <div className="font-serif italic text-[16px] text-text mb-2">Do-file</div>
      <div className="text-[12px] text-text-muted mb-4">
        Every action you've taken — Guided clicks and Pro commands alike — as a
        replayable Stata script. {nCommands} command{nCommands === 1 ? "" : "s"} recorded.
      </div>
      <Tooltip
        what="Saves the session's command history as a Stata .do file."
        how="Click to download. Re-run it in real Stata or SolarSTATA Pro mode to reproduce your work."
        example="Use this when submitting analyses for review or pairing with a manuscript."
      >
        <button
          type="button"
          onClick={onDownload}
          disabled={busy || nCommands === 0}
          className="run-btn-primary disabled:opacity-60"
        >
          {busy ? "Saving…" : "Download session.do"}
        </button>
      </Tooltip>
      {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
    </div>
  );
}

// =====================================================================
// Report card
// =====================================================================

function ReportCard({
  nCommands,
  capabilities,
}: { nCommands: number; capabilities: Capabilities }) {
  const [busy, setBusy] = useState<ReportFmt | "">("");
  const [error, setError] = useState<string | null>(null);

  const onDownload = async (fmt: ReportFmt) => {
    setBusy(fmt); setError(null);
    try {
      const blob = await api.downloadReport(fmt);
      triggerDownload(blob, `solarstata_report.${fmt}`);
    } catch (e) { setError(e instanceof ApiError ? e.detail : String(e)); }
    finally { setBusy(""); }
  };

  const pdfDisabled = !capabilities.pdf;
  const pdfWhat = capabilities.pdf
    ? "PDF rendered via WeasyPrint. Instrument Serif headings, IBM Plex Sans body."
    : "PDF export requires GTK system libraries (not installed on this machine). "
      + "Use HTML — it works in any browser and you can print to PDF from there.";
  const pdfHow = capabilities.pdf
    ? "Click to download. A4 pages, page numbers, command + output blocks."
    : "Click HTML instead, open the file in any browser, and press Cmd/Ctrl+P to "
      + "save it as PDF. To enable PDF export here, install the GTK 3 runtime "
      + "(https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer "
      + "on Windows) and restart SolarSTATA.";
  const pdfExample = capabilities.pdf
    ? "Drop into a paper as a Methods appendix."
    : <>HTML works everywhere &mdash; <code className="font-mono">Cmd/Ctrl+P</code> in your browser will save it as PDF.</>;

  return (
    <div className="bg-surface border border-border rounded-md p-5">
      <div className="font-serif italic text-[16px] text-text mb-2">Research report</div>
      <div className="text-[12px] text-text-muted mb-4">
        Clean PDF or HTML write-up of every command you ran, formatted for sharing.
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Tooltip what={pdfWhat} how={pdfHow} example={pdfExample}>
          <button
            type="button"
            onClick={() => onDownload("pdf")}
            disabled={pdfDisabled || busy !== "" || nCommands === 0}
            className="run-btn-primary disabled:opacity-60 !w-full"
            aria-label={pdfDisabled ? "PDF export unavailable" : "Download PDF report"}
          >
            {busy === "pdf" ? "Saving…" : pdfDisabled ? "PDF unavailable" : "PDF"}
          </button>
        </Tooltip>
        <Tooltip
          what="Same content as the PDF, but as a single self-contained HTML file."
          how="Click to download. Open in any browser, print to PDF, or paste into a doc."
          example="Useful when you want to edit the report before publishing."
        >
          <button
            type="button"
            onClick={() => onDownload("html")}
            disabled={busy !== "" || nCommands === 0}
            className={`disabled:opacity-60 !w-full ${pdfDisabled ? "run-btn-primary" : "run-btn-secondary"}`}
          >
            {busy === "html" ? "Saving…" : "HTML"}
          </button>
        </Tooltip>
      </div>
      {pdfDisabled && (
        <div className="mt-3 text-[11px] text-text-faint leading-snug">
          PDF export isn't available on this server. HTML works everywhere; use{" "}
          <span className="font-mono">Cmd/Ctrl+P</span> in your browser to save it as PDF.
        </div>
      )}
      {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
    </div>
  );
}

// =====================================================================
// Helper
// =====================================================================

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
