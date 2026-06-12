/* Mode toggle pill: gold indicator slides between Guided and Pro.
 *
 * The indicator is positioned by MEASURING the active button
 * (offsetLeft/offsetWidth against the container's padding box) rather
 * than assuming each tab is exactly 50% wide — calc-percentage pills
 * drift a pixel or two off the label under fractional widths and
 * browser zoom. Measuring keeps the pill exactly centered on the word
 * at any size. The 250ms cubic-bezier slide matches the mockup's feel;
 * buttons sit on top (z-index: 2) so the pill animates underneath. */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useApp } from "../state/store";
import type { Mode } from "../lib/types";
import { Tooltip } from "./Tooltip";

const MODES: { value: Mode; label: string; tip: { what: string; how: string; example: string } }[] = [
  {
    value: "guided",
    label: "Guided",
    tip: {
      what: "Wizard mode. Click through Import → Inspect → Analyze → Visualize → Export with no command typing.",
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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null);

  const measure = useCallback(() => {
    const container = containerRef.current;
    const active = container?.querySelector<HTMLButtonElement>(`[data-mode="${mode}"]`);
    if (!container || !active) return;
    // offsetLeft/offsetWidth are relative to the container's padding
    // box — the same coordinate space the absolute pill positions in.
    setPill({ left: active.offsetLeft, width: active.offsetWidth });
  }, [mode]);

  // Measure before paint on mount and whenever the mode flips.
  useLayoutEffect(() => {
    measure();
  }, [measure]);

  // Re-measure when the buttons change size (font swap-in, zoom,
  // window resize). jsdom has no ResizeObserver — guard for tests.
  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    const container = containerRef.current;
    if (container) {
      ro.observe(container);
      container.querySelectorAll("button").forEach((b) => ro.observe(b));
    }
    return () => ro.disconnect();
  }, [measure]);

  return (
    <div
      ref={containerRef}
      role="tablist"
      aria-label="Mode toggle"
      className="relative flex bg-surface border border-border rounded-full p-[3px]"
    >
      {pill && (
        <span
          aria-hidden
          className="absolute top-[3px] bottom-[3px] bg-accent rounded-full transition-[left,width] duration-[250ms] ease-toggle"
          style={{ left: pill.left, width: pill.width }}
        />
      )}
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
              className={`flex-1 relative z-[2] py-[5px] px-4 font-sans text-[12px] font-medium rounded-full tracking-[0.01em] cursor-pointer transition-colors text-center ${
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
