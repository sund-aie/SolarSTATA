/* Header row picker. Renders the 10 raw rows from the chosen sheet
 * and lets the user click which one holds the variable names.
 *
 * On mount, fires /api/data/preflight to ask the backend where the
 * header actually looks like it sits. While that's in flight we
 * keep the picker working — the row table renders immediately and
 * defaults to row 1 (the legacy behaviour). When the result lands:
 *
 *   - The auto-picked row updates to the detected header (unless
 *     the user has already clicked one — we honour their override).
 *   - A status strip above the table reads back what we detected:
 *     "Header detected on row 5 — rows 1 to 4 look like notes, we
 *     will skip them." for the canonical TIDY LONG FORMAT case, or
 *     "Ready to load — header on row 1, looks clean." for the
 *     happy path.
 *   - Merged-cell / hidden-row / hidden-column issues each get
 *     their own caution chip below the main strip.
 *
 * The user can still click any row to override the auto-pick.
 */

import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type {
  PreflightCellIssues,
  PreflightColumnKinds,
  PreflightResponse,
  StagedSheet,
} from "../lib/types";

interface Props {
  fileId: string;
  filename: string;
  sheet: StagedSheet;
  onConfirm: (headerRow: number) => void;
  onBack: () => void;
}

export function HeaderRowPicker({ fileId, filename, sheet, onConfirm, onBack }: Props) {
  const [picked, setPicked] = useState<number>(1);
  const [preflight, setPreflight] = useState<PreflightResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const userPickedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.preflight({ file_id: fileId, sheet: sheet.name })
      .then((result) => {
        if (cancelled) return;
        setPreflight(result);
        // Only auto-adjust if the user hasn't already clicked a row.
        if (!userPickedRef.current) setPicked(result.detected_header_row);
      })
      .catch(() => {
        /* preflight is best-effort — leave the row table working */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [fileId, sheet.name]);

  const handlePick = (rowNum: number) => {
    userPickedRef.current = true;
    setPicked(rowNum);
  };

  const rows = sheet.preview_rows;
  const cols = Math.max(0, ...rows.map((r) => r.length));

  return (
    <div className="bg-surface border border-border rounded-md p-6 max-w-[860px]">
      <div className="mb-5">
        <div className="eyebrow mb-2">Step 1b · pick the header row</div>
        <div className="font-serif italic text-[20px] text-text mb-1">
          Which row has your <em className="text-accent">variable names</em>?
        </div>
        <div className="text-text-muted text-[13px]">
          <span className="font-mono">{filename}</span> · sheet{" "}
          <span className="font-mono text-text">{sheet.name}</span>. Click the row
          that contains your column headers; rows above it are skipped.
        </div>
      </div>

      <PreflightStrip loading={loading} preflight={preflight} />

      <div className="overflow-auto bg-bg border border-border rounded-sm mt-4">
        <table className="w-full text-[12px] font-mono">
          <thead className="text-text-faint">
            <tr>
              <th className="text-right px-2 py-1 w-10 sticky left-0 bg-bg">#</th>
              {Array.from({ length: cols }).map((_, j) => (
                <th key={j} className="text-left px-2 py-1 whitespace-nowrap">col {j + 1}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const rowNum = i + 1;
              const active = picked === rowNum;
              return (
                <tr
                  key={i}
                  onClick={() => handlePick(rowNum)}
                  className={`cursor-pointer border-t border-border transition-colors ${
                    active ? "bg-accent-soft" : "hover:bg-surface"
                  }`}
                >
                  <td
                    className={`text-right px-2 py-[6px] sticky left-0 ${
                      active ? "text-accent bg-accent-soft" : "text-text-faint bg-bg"
                    }`}
                  >
                    {active ? `▶ ${rowNum}` : rowNum}
                  </td>
                  {Array.from({ length: cols }).map((_, j) => {
                    const cell = row[j] ?? "";
                    const isHeader = active;
                    return (
                      <td
                        key={j}
                        className={`px-2 py-[6px] whitespace-nowrap ${
                          isHeader ? "text-accent font-medium" : "text-text"
                        }`}
                      >
                        {cell || <span className="opacity-30">·</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={cols + 1} className="px-3 py-6 text-center text-text-faint italic">
                  this sheet has no data preview
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-5 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="text-[12px] text-text-muted hover:text-text"
        >
          ← Back to sheets
        </button>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-text-faint">
            Header row: <span className="text-accent">{picked}</span>
          </span>
          <button
            type="button"
            onClick={() => onConfirm(picked)}
            className="bg-accent text-bg px-4 py-2 rounded-sm font-medium text-[13px] hover:brightness-110"
          >
            Load with row {picked} as header
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pre-flight strip + supporting helpers
// ---------------------------------------------------------------------------

function PreflightStrip({
  loading,
  preflight,
}: {
  loading: boolean;
  preflight: PreflightResponse | null;
}) {
  if (!preflight) {
    if (loading) {
      return (
        <div className="text-[12px] text-text-faint italic px-1">
          Checking sheet structure…
        </div>
      );
    }
    return null;
  }

  const headlineGood = preflight.detected_header_row === 1;
  const toneClass = headlineGood
    ? "border-good bg-good-soft text-good"
    : "border-warn bg-warn-soft text-warn";

  const summary = afterHeaderSummary(preflight);
  const issues = issueChips(preflight.cell_issues);

  return (
    <div className="space-y-2" role="status" aria-live="polite">
      <div className={`flex items-start gap-2 border rounded-sm px-3 py-2 ${toneClass}`}>
        <span className="font-mono text-[11px] mt-[1px] shrink-0">
          {headlineGood ? "✓" : "⚠"}
        </span>
        <div className="text-[12px] leading-snug">
          {headlineGood
            ? "Ready to load — header on row 1, looks clean."
            : headerDetectedMessage(preflight.detected_header_row)}
        </div>
      </div>

      {summary && (
        <div className="font-mono text-[11px] text-text-muted px-1">
          {summary}
        </div>
      )}

      {issues.length > 0 && (
        <ul className="space-y-1">
          {issues.map((chip, i) => (
            <li
              key={i}
              className="flex items-start gap-2 border border-warn bg-warn-soft text-warn rounded-sm px-3 py-[6px] text-[11px] leading-snug"
            >
              <span className="font-mono shrink-0">⚠</span>
              <span>{chip}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function headerDetectedMessage(detected: number): string {
  // Canonical phrasing — the headline-on-row-5 case reads:
  //   "Header detected on row 5 — rows 1 to 4 look like notes, we will skip them."
  if (detected === 2) {
    return "Header detected on row 2 — row 1 looks like a note, we will skip it.";
  }
  return `Header detected on row ${detected} — rows 1 to ${detected - 1} look like notes, we will skip them.`;
}

function afterHeaderSummary(p: PreflightResponse): string | null {
  const kinds = kindsBreakdown(p.column_kinds);
  const rowsWord = p.n_rows_after_header === 1 ? "row" : "rows";
  const colsTotal =
    p.column_kinds.numeric +
    p.column_kinds.categorical +
    p.column_kinds.identifier +
    p.column_kinds.string;
  const colsWord = colsTotal === 1 ? "column" : "columns";
  const head = `After header: ${p.n_rows_after_header.toLocaleString()} ${rowsWord} · ${colsTotal} ${colsWord}`;
  return kinds ? `${head} (${kinds})` : head;
}

function kindsBreakdown(k: PreflightColumnKinds): string {
  const parts: string[] = [];
  if (k.numeric) parts.push(`${k.numeric} numeric`);
  if (k.categorical) parts.push(`${k.categorical} categorical`);
  if (k.identifier) parts.push(`${k.identifier} id`);
  if (k.string) parts.push(`${k.string} text`);
  return parts.join(" · ");
}

function issueChips(i: PreflightCellIssues): string[] {
  const chips: string[] = [];
  if (i.merged_cells > 0) {
    chips.push(
      `${i.merged_cells} merged cell${i.merged_cells === 1 ? "" : "s"} — only the top-left value is kept; the rest will read as blank.`,
    );
  }
  if (i.hidden_rows > 0) {
    chips.push(
      `${i.hidden_rows} hidden row${i.hidden_rows === 1 ? "" : "s"} — these will load as regular rows, not skipped.`,
    );
  }
  if (i.hidden_cols > 0) {
    chips.push(
      `${i.hidden_cols} hidden column${i.hidden_cols === 1 ? "" : "s"} — these will load as regular columns, not skipped.`,
    );
  }
  return chips;
}
