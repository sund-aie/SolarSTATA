/* Inline sheet picker for multi-sheet xlsx uploads.
 *
 * Renders one card per sheet: name + dimensions + a 3-row preview teaser.
 * The user clicks a card to commit; single-sheet workbooks shouldn't
 * reach this UI but we still render gracefully.
 */

import type { StagedSheet } from "../lib/types";

interface Props {
  filename: string;
  sheets: StagedSheet[];
  onPick: (sheet: StagedSheet) => void;
  onCancel: () => void;
}

export function SheetPicker({ filename, sheets, onPick, onCancel }: Props) {
  return (
    <div className="bg-surface border border-border rounded-md p-6 max-w-[760px]">
      <div className="mb-5">
        <div className="eyebrow mb-2">Step 1a · pick a sheet</div>
        <div className="font-serif italic text-[20px] text-text mb-1">
          Which sheet has the <em className="text-accent">data</em>?
        </div>
        <div className="text-text-muted text-[13px]">
          <span className="font-mono">{filename}</span> contains{" "}
          <strong className="text-text">{sheets.length}</strong> sheets. Pick the one with
          the variables you want to analyze.
        </div>
      </div>

      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
        {sheets.map((s) => (
          <button
            key={s.name}
            type="button"
            onClick={() => onPick(s)}
            className="text-left bg-bg border border-border rounded-md p-4 hover:border-accent hover:bg-accent-soft transition-colors group"
          >
            <div className="flex items-baseline justify-between mb-2">
              <div className="font-mono text-[13px] text-text font-medium">{s.name}</div>
              <div className="font-mono text-[10px] text-text-faint">
                {s.n_rows.toLocaleString()}r × {s.n_cols}c
              </div>
            </div>
            <div className="space-y-[2px]">
              {s.preview_rows.slice(0, 3).map((row, i) => (
                <div
                  key={i}
                  className="font-mono text-[10px] text-text-faint truncate"
                  title={row.join(" | ")}
                >
                  {row.slice(0, 4).map((c, j) => (
                    <span key={j} className="mr-2">{c || <span className="opacity-40">·</span>}</span>
                  ))}
                </div>
              ))}
              {s.preview_rows.length === 0 && (
                <div className="font-mono text-[10px] text-text-faint italic">empty</div>
              )}
            </div>
          </button>
        ))}
      </div>

      <div className="mt-5 flex justify-between items-center">
        <button
          type="button"
          onClick={onCancel}
          className="text-[12px] text-text-muted hover:text-text"
        >
          Cancel and choose a different file
        </button>
      </div>
    </div>
  );
}
