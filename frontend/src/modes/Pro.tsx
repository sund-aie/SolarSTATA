/* Pro mode: 4-pane grid skeleton (no real execution yet — that's Phase 3).
 *
 * Grid:
 *   ┌──────┬─────────────┬─────────┐
 *   │      │  Editor     │         │
 *   │ Vars ├─────────────┤  Graphs │
 *   │      │  Results    │         │
 *   └──────┴─────────────┴─────────┘
 *   240px       1fr         360px
 *   rows: [1fr, 240px]
 */

import { EditorMock } from "../components/EditorMock";
import { useApp } from "../state/store";

export function ProMode() {
  const columns = useApp((s) => s.columns);

  return (
    <div
      className="h-full grid bg-border"
      style={{
        gridTemplateColumns: "240px 1fr 360px",
        gridTemplateRows: "1fr 240px",
        gap: "1px",
      }}
    >
      <Pane className="row-span-2" titleLeft={`Variables · ${columns.length}`}>
        <div className="flex-1 overflow-y-auto py-2">
          {columns.length === 0 ? (
            <div className="px-4 text-[12px] text-text-faint">No dataset loaded</div>
          ) : (
            columns.map((c) => (
              <div
                key={c.name}
                className="flex items-center gap-[10px] px-4 py-[7px] text-[12px] cursor-pointer border-l-2 border-transparent hover:bg-surface hover:border-border-strong"
              >
                <span className="font-mono text-text flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
                  {c.name}
                </span>
                <span className="font-mono text-[10px] text-text-faint">{c.stata_type ?? c.dtype}</span>
              </div>
            ))
          )}
        </div>
      </Pane>

      <Pane titleLeft="Command · do-file" titleRight={<span className="text-accent">⌘ Enter to run</span>}>
        <EditorMock />
      </Pane>

      <Pane className="row-span-2" titleLeft="Graphs">
        <Empty
          phase={5}
          headline="Plotly graphs land in Phase 5"
          subline="histograms · scatter · residuals · KM curves"
        />
      </Pane>

      <Pane titleLeft="Results">
        <Empty
          phase={3}
          headline="Pro mode execution coming in Phase 3"
          subline="Stata-style ASCII tables stream here over WebSocket"
        />
      </Pane>
    </div>
  );
}

function Pane({
  children,
  className = "",
  titleLeft,
  titleRight,
}: {
  children: React.ReactNode;
  className?: string;
  titleLeft: React.ReactNode;
  titleRight?: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col bg-bg overflow-hidden relative ${className}`}>
      <div className="flex items-center justify-between px-4 py-[10px] border-b border-border flex-shrink-0">
        <span className="font-mono text-[10px] text-text-faint uppercase tracking-[0.12em]">
          {titleLeft}
        </span>
        {titleRight && (
          <span className="font-mono text-[10px] uppercase tracking-[0.12em]">{titleRight}</span>
        )}
      </div>
      {children}
    </div>
  );
}

function Empty({ phase, headline, subline }: { phase: number; headline: string; subline: string }) {
  return (
    <div className="flex-1 flex items-center justify-center flex-col gap-2 text-text-faint text-[12px] text-center px-5">
      <span className="inline-flex items-center gap-[6px] px-[10px] py-1 bg-surface border border-border rounded-full font-mono text-[10px] text-text-muted tracking-[0.04em]">
        <span className="w-[5px] h-[5px] rounded-full bg-accent" aria-hidden />
        Phase {phase}
      </span>
      <div className="mt-[6px]">{headline}</div>
      <div className="text-[11px] opacity-70">{subline}</div>
    </div>
  );
}
