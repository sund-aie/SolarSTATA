/* Result card pattern — header strip + body. Reused for every Guided result. */

import type { ReactNode } from "react";

interface Props {
  title: string;
  time?: string;
  children: ReactNode;
}

export function ResultsCard({ title, time = "just now", children }: Props) {
  return (
    <div className="mt-4 bg-surface border border-border rounded-md overflow-hidden">
      <div className="flex items-center justify-between px-[14px] py-[10px] bg-surface-2 border-b border-border">
        <div className="font-serif italic text-[13px] text-text">{title}</div>
        <div className="font-mono text-[10px] text-text-faint">{time}</div>
      </div>
      <div className="p-[14px]">{children}</div>
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
