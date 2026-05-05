/* Mode toggle pill: gold indicator slides between Guided and Pro.
 *
 * The pill is positioned absolutely and translated via CSS transform; the
 * 250ms cubic-bezier matches the mockup's feel exactly. Buttons sit on top
 * (z-index: 2) so the pill animates underneath them. */

import { useApp } from "../state/store";
import type { Mode } from "../lib/types";

const MODES: { value: Mode; label: string }[] = [
  { value: "guided", label: "Guided" },
  { value: "pro", label: "Pro" },
];

export function ModeToggle() {
  const mode = useApp((s) => s.mode);
  const setMode = useApp((s) => s.setMode);

  return (
    <div
      role="tablist"
      aria-label="Mode toggle"
      className="relative flex bg-surface border border-border rounded-full p-[3px]"
    >
      <span
        aria-hidden
        className="absolute top-[3px] bottom-[3px] left-[3px] w-[calc(50%-3px)] bg-accent rounded-full transition-transform duration-[250ms] ease-toggle"
        style={{ transform: mode === "pro" ? "translateX(100%)" : "translateX(0)" }}
      />
      {MODES.map((m) => {
        const active = mode === m.value;
        return (
          <button
            key={m.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => setMode(m.value)}
            data-mode={m.value}
            className={`relative z-[2] py-[5px] px-4 font-sans text-[12px] font-medium rounded-full tracking-[0.01em] cursor-pointer transition-colors ${
              active ? "text-bg" : "text-text-muted hover:text-text"
            }`}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
