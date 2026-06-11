/* Result card pattern — header strip + body. Reused for every Guided result.
 *
 * `interpretation` (v3.3) renders the engine's plain-English sentences
 * as a first-class block beneath the table/text. Empty or absent →
 * nothing renders, not even the header. */

import type { ReactNode } from "react";

interface Props {
  title: string;
  time?: string;
  interpretation?: string[] | null;
  children: ReactNode;
}

export function ResultsCard({ title, time = "just now", interpretation, children }: Props) {
  return (
    <div className="mt-4 bg-surface border border-border rounded-md overflow-hidden">
      <div className="flex items-center justify-between px-[14px] py-[10px] bg-surface-2 border-b border-border">
        <div className="font-serif italic text-[13px] text-text">{title}</div>
        <div className="font-mono text-[10px] text-text-faint">{time}</div>
      </div>
      <div className="p-[14px]">
        {children}
        <InterpretationBlock sentences={interpretation} />
      </div>
    </div>
  );
}

/* The sentences come straight from the engine's interpretation field —
 * a rendering of numbers that already exist in the result payload.
 * Exported for tests. */
export function InterpretationBlock({ sentences }: { sentences?: string[] | null }) {
  if (!sentences || sentences.length === 0) return null;
  return (
    <div className="mt-4 pt-3 border-t border-border" data-testid="interpretation">
      <div className="eyebrow mb-2 text-accent">Interpretation</div>
      <div className="space-y-[6px]">
        {sentences.map((s, i) => (
          <p key={i} className="text-[13px] leading-relaxed text-text">{s}</p>
        ))}
      </div>
    </div>
  );
}

interface RowProps {
  k: string;
  v: ReactNode;
}

export function ResultRow({ k, v }: RowProps) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-3 py-[6px] font-mono text-[12px] border-b border-border last:border-b-0">
      <span className="text-text-muted">{k}</span>
      <span className="text-text text-right">{v}</span>
    </div>
  );
}
