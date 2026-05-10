/* Mode toggle pill: gold indicator slides between Guided and Pro.
 *
 * The pill is positioned absolutely and translated via CSS transform; the
 * 250ms cubic-bezier matches the mockup's feel exactly. Buttons sit on top
 * (z-index: 2) so the pill animates underneath them. */

import { useApp } from "../state/store";
import type { Mode } from "../lib/types";
import { Tooltip } from "./Tooltip";

const MODES: { value: Mode; label: string; tip: { what: string; how: string; example: string } }[] = [
  {
    value: "guided",
    label: "Guided",
    tip: {
      what: "Wizard mode. Click through Import → Inspect → Clean → Analyze → Visualize → Export with no command typing.",
      how: "Pick a step on the left rail and use the forms in the centre. Every action shows the equivalent Stata syntax so you can pick it up over time.",
      example: "Drop clinic_patients.csv, click a variable card, hit Run summarize.",
    },
  },
  {
    value: "pro",
    label: "Pro",
    tip: {
      what: "Stata-style command editor with syntax highlighting and autocomplete.",
      how: "Type a command in the editor and press Cmd/Ctrl+Enter to run. Results stream into the right pane block by block.",
      example: "regress plaque_index age i.sex brushing_freq, vce(robust)",
    },
  },
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
          <Tooltip key={m.value} what={m.tip.what} how={m.tip.how} example={m.tip.example}>
            <button
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
          </Tooltip>
        );
      })}
    </div>
  );
}
