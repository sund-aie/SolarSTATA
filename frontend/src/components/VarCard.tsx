/* Single variable card: name + type chip + n/missing + sparkline.
 * Click to select (single-selection model). */

import { Sparkline } from "./Sparkline";
import { useApp } from "../state/store";
import type { ColumnInfo, VarKind } from "../lib/types";

const CHIP_CLASS: Record<VarKind, string> = {
  numeric:     "bg-info-soft text-info",
  binary:      "bg-good-soft text-good",
  categorical: "bg-warn-soft text-warn",
  string:      "bg-[rgba(180,160,210,0.14)] text-[#B4A0D2]",
  id:          "bg-[rgba(160,160,160,0.10)] text-text-muted",
};

interface Props {
  info: ColumnInfo;
}

export function VarCard({ info }: Props) {
  const selected = useApp((s) => s.selectedVar) === info.name;
  const select = useApp((s) => s.selectVar);

  const missText = info.n_missing === 0 ? "0 missing" : `${info.n_missing} miss`;

  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      onClick={() => select(info.name)}
      className={`relative text-left bg-surface border rounded-md p-[14px] cursor-pointer transition-all hover:-translate-y-px hover:bg-surface-2 hover:border-border-strong ${
        selected ? "border-accent bg-accent-soft" : "border-border"
      }`}
    >
      {selected && (
        <span
          aria-hidden
          className="absolute pointer-events-none rounded-md"
          style={{ inset: -1, boxShadow: "0 0 0 3px var(--accent-glow)" }}
        />
      )}
      <div className="flex items-start justify-between mb-2 gap-2">
        <div className="font-mono text-[13px] font-medium text-text overflow-hidden text-ellipsis whitespace-nowrap">
          {info.name}
        </div>
        <span
          className={`flex-shrink-0 font-mono text-[9px] tracking-[0.04em] font-medium px-[6px] py-[2px] rounded lowercase ${CHIP_CLASS[info.kind]}`}
        >
          {info.kind}
        </span>
      </div>
      <div className="flex items-center justify-between font-mono text-[10px] text-text-muted mb-[10px]">
        <span>n = {info.n}</span>
        <span className={info.n_missing === 0 ? "text-text-faint" : "text-warn"}>{missText}</span>
      </div>
      <Sparkline data={info.sparkline} variant={selected ? "panel" : "card"} />
    </button>
  );
}
