/* FormatGuide — "prepare your sheet" panel.
 *
 * Sits above the dropzone on the Import step. Five product-voice
 * rules (each one explains WHY) plus a tiny good-vs-bad mini-sheet
 * visual so users can match their file against the canonical layout
 * before they upload.
 *
 * Always expanded on first visit. Once the user collapses it the
 * preference is remembered in localStorage and the panel sits
 * collapsed on subsequent visits — same persistence idiom as the
 * theme switcher (see state/theme.ts).
 *
 * Typography per brand: Instrument Serif for the headline and the
 * lead "what this means" sentence; Geist for the rule list; Geist
 * Mono for the mini-sheet visual. No serif inside the body copy.
 */

import { useEffect, useState } from "react";

const STORAGE_KEY = "solarstata.format_guide_collapsed";

export function FormatGuide() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      /* noop */
    }
  }, [collapsed]);

  const toggle = () => setCollapsed((c) => !c);

  return (
    <section
      className="mb-6 bg-surface border border-border rounded-md"
      aria-label="Prepare your sheet — formatting guide"
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={!collapsed}
        className="flex items-baseline justify-between w-full text-left px-5 py-3"
      >
        <div>
          <div className="eyebrow mb-1">Before you import</div>
          <h2 className="font-serif text-[20px] leading-tight text-text">
            Prepare your <em className="text-accent italic">sheet</em>
          </h2>
        </div>
        <span className="font-mono text-[11px] text-text-muted shrink-0 ml-4">
          {collapsed ? "Show ▾" : "Hide ▴"}
        </span>
      </button>

      {!collapsed && (
        <div className="px-5 pb-5">
          <p className="font-serif italic text-[14px] text-text-muted mb-4 max-w-[640px]">
            A few minutes of cleanup before upload saves an hour of debugging
            later. These five rules cover almost every "but my file looked
            fine" surprise.
          </p>

          <ol className="space-y-3 mb-5">
            <Rule
              n={1}
              label="Row 1 holds your column names."
              why="Everything below row 1 is data. If row 1 is a title or instructions, your variable names will be wrong."
            />
            <Rule
              n={2}
              label="One row per observation."
              why="Each row is a single subject, sample, or measurement. Repeated measurements get extra rows, not extra columns."
            />
            <Rule
              n={3}
              label="No merged cells — we read cells, not their borders."
              why="A merged cell only carries a value in its top-left position; everything else in the merge reads as blank and rows go out of alignment."
            />
            <Rule
              n={4}
              label="No title or blank rows above the headers."
              why="The auto-detector handles a few lines of preamble, but plain row-1 headers always parse exactly as you expect."
            />
            <Rule
              n={5}
              label="Numbers as numbers — units go in the column name."
              why={
                <>
                  "312 VHN" forces the whole column to read as text and you
                  lose statistics. Try <code className="font-mono">vhn_mean</code>{" "}
                  for the column and <code className="font-mono">312</code> for
                  the value.
                </>
              }
            />
          </ol>

          <GoodVsBadVisual />
        </div>
      )}
    </section>
  );
}

function Rule({
  n,
  label,
  why,
}: {
  n: number;
  label: string;
  why: React.ReactNode;
}) {
  return (
    <li className="flex gap-3">
      <span className="font-mono text-[11px] text-accent flex-none w-5 pt-[2px]">
        {String(n).padStart(2, "0")}
      </span>
      <div>
        <div className="text-[13px] text-text font-medium">{label}</div>
        <div className="text-[12px] text-text-muted leading-relaxed mt-[2px]">
          {why}
        </div>
      </div>
    </li>
  );
}

/* Two mini-sheets side by side. Cells use Geist Mono tabular,
 * column letters / row numbers in faint mono. The "good" tile uses
 * --good for its tone strip; "bad" uses --warn. */
function GoodVsBadVisual() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <MiniSheet
        tone="good"
        caption="header on row 1, clean cells"
        rows={[
          ["patient_id", "age", "vhn_mean"],
          ["1001", "23", "312"],
          ["1002", "45", "289"],
          ["1003", "31", "305"],
        ]}
        headerRow={1}
      />
      <MiniSheet
        tone="bad"
        caption="merged title + units inside cells"
        rows={[
          ["VHN study group · 2024", "", ""],
          ["", "", ""],
          ["patient", "age", "VHN"],
          ["1001", "23", "312 VHN"],
          ["1002", "45", "289 VHN"],
        ]}
        headerRow={3}
        mergedTopRow
      />
    </div>
  );
}

function MiniSheet({
  tone,
  caption,
  rows,
  headerRow,
  mergedTopRow = false,
}: {
  tone: "good" | "bad";
  caption: string;
  rows: string[][];
  headerRow: number;
  mergedTopRow?: boolean;
}) {
  const toneClass =
    tone === "good"
      ? "border-good bg-good-soft text-good"
      : "border-warn bg-warn-soft text-warn";
  const nCols = Math.max(...rows.map((r) => r.length));

  return (
    <div className="bg-bg border border-border rounded-sm overflow-hidden">
      <div
        className={`flex items-center justify-between px-3 py-1 border-b ${toneClass}`}
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.08em]">
          {tone}
        </span>
        <span className="font-mono text-[10px] opacity-80">{caption}</span>
      </div>
      <table className="w-full font-mono text-[11px]">
        <thead>
          <tr className="bg-surface text-text-faint">
            <th className="text-right px-2 py-1 w-7" />
            {Array.from({ length: nCols }).map((_, j) => (
              <th key={j} className="text-left px-2 py-1 font-normal">
                {String.fromCharCode(65 + j)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const rowNum = i + 1;
            const isHeader = rowNum === headerRow;
            const isMerged = mergedTopRow && rowNum === 1;
            return (
              <tr
                key={i}
                className={`border-t border-border ${isHeader ? "bg-accent-soft" : ""}`}
              >
                <td className="text-right px-2 py-1 text-text-faint w-7">
                  {rowNum}
                </td>
                {isMerged ? (
                  <td
                    colSpan={nCols}
                    className="px-2 py-1 italic text-warn"
                    title="merged cell — only the top-left value is read"
                  >
                    {row[0]}
                  </td>
                ) : (
                  Array.from({ length: nCols }).map((_, j) => {
                    const cell = row[j] ?? "";
                    return (
                      <td
                        key={j}
                        className={`px-2 py-1 ${isHeader ? "text-accent" : "text-text"} ${cell === "" ? "opacity-30" : ""}`}
                      >
                        {cell || "·"}
                      </td>
                    );
                  })
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
