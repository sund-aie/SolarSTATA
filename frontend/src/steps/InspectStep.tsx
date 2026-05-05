/* Inspect step: dataset bar + variable card grid. Selecting a card
 * populates the right-rail InspectPanel (rendered by Guided.tsx). */

import { useApp } from "../state/store";
import { VarCard } from "../components/VarCard";

export function InspectStep() {
  const dataset = useApp((s) => s.dataset);
  const columns = useApp((s) => s.columns);

  if (!dataset) return null;

  const totalCells = dataset.n_obs * dataset.n_vars;
  const totalMissing = columns.reduce((acc, c) => acc + c.n_missing, 0);
  const missingPct = totalCells > 0 ? (totalMissing / totalCells) * 100 : 0;

  return (
    <div className="overflow-y-auto px-10 py-8 pb-20">
      <div className="mb-8">
        <div className="eyebrow mb-2">Step 2 of 6</div>
        <h1 className="font-serif text-[32px] leading-[1.15] text-text tracking-[-0.01em] mb-1">
          Inspect your <em className="text-accent italic">variables</em>
        </h1>
        <p className="text-text-muted text-[14px] max-w-[520px]">
          Click any card to see its distribution and run summarize. Watch for
          unusual values, missingness, and types that look wrong.
        </p>
      </div>

      <div className="flex items-center gap-6 px-[18px] py-[14px] bg-surface border border-border rounded-md mb-6">
        <div className="font-mono text-[12px] text-accent mr-auto">{dataset.filename}</div>
        <DatasetItem n={dataset.n_obs.toLocaleString()} label="observations" />
        <DatasetItem n={String(dataset.n_vars)} label="variables" />
        <DatasetItem
          n={`${missingPct.toFixed(1)}%`}
          label="missing overall"
          warn={missingPct > 0}
        />
      </div>

      <div className="flex items-center gap-3 mb-3 text-text-muted text-[12px]">
        <span>{columns.length} variables</span>
        <span className="flex-1 h-px bg-border" />
      </div>

      <div className="grid gap-[10px]" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }} role="listbox">
        {columns.map((col) => (
          <VarCard key={col.name} info={col} />
        ))}
      </div>
    </div>
  );
}

function DatasetItem({ n, label, warn = false }: { n: string; label: string; warn?: boolean }) {
  return (
    <div className="flex items-baseline gap-[6px]">
      <span className={`font-mono text-[14px] font-medium ${warn ? "text-warn" : "text-text"}`}>{n}</span>
      <span className="text-[12px] text-text-muted">{label}</span>
    </div>
  );
}
