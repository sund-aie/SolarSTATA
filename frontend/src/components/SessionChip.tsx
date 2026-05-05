/* Right-side session chip: filename + n_obs × n_vars + glowing green dot. */

import { useApp } from "../state/store";

export function SessionChip() {
  const dataset = useApp((s) => s.dataset);

  if (!dataset) {
    return (
      <div className="flex items-center gap-2 px-3 py-[6px] bg-surface border border-border rounded-md font-mono text-[11px] text-text-muted">
        <span className="w-[6px] h-[6px] rounded-full bg-text-faint" aria-hidden />
        <span>No dataset</span>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-2 px-3 py-[6px] bg-surface border border-border rounded-md font-mono text-[11px] text-text-muted"
      aria-label="Active dataset"
    >
      <span
        className="w-[6px] h-[6px] rounded-full bg-good"
        style={{ boxShadow: "0 0 8px rgba(143, 170, 136, 0.6)" }}
        aria-hidden
      />
      <span className="text-text">{dataset.filename}</span>
      <span aria-hidden>·</span>
      <span>
        {dataset.n_obs.toLocaleString()} obs × {dataset.n_vars} vars
      </span>
    </div>
  );
}
