/* Header row picker. Renders the 10 raw rows from the chosen sheet and
 * lets the user click which one holds the variable names. Default is
 * row 1; the picker is what saves you when row 5 is the real header
 * (the "TIDY LONG FORMAT" pattern). */

import { useState } from "react";
import type { StagedSheet } from "../lib/types";

interface Props {
  filename: string;
  sheet: StagedSheet;
  onConfirm: (headerRow: number) => void;
  onBack: () => void;
}

export function HeaderRowPicker({ filename, sheet, onConfirm, onBack }: Props) {
  const [picked, setPicked] = useState<number>(1);
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
          <span className="font-mono text-text">{sheet.name}</span>. Click the row that contains
          your column headers; rows above it are skipped.
        </div>
      </div>

      <div className="overflow-auto bg-bg border border-border rounded-sm">
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
                  onClick={() => setPicked(rowNum)}
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
