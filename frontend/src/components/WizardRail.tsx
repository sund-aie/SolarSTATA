/* Left rail: 6 wizard steps + contextual help card.
 *
 * - Active step: 2px gold left bar + filled gold step-num circle.
 * - Done steps: green-tinted check in step-num.
 * - Steps before the current one (in order) are auto-marked done. */

import { useApp } from "../state/store";
import type { Step } from "../lib/types";

const STEPS: { id: Step; name: string }[] = [
  { id: "import",    name: "Import" },
  { id: "inspect",   name: "Inspect" },
  { id: "clean",     name: "Clean" },
  { id: "analyze",   name: "Analyze" },
  { id: "visualize", name: "Visualize" },
  { id: "export",    name: "Export" },
];

const HELP_BY_STEP: Record<Step, { title: string; body: React.ReactNode }> = {
  import: {
    title: "Get your data in",
    body: (
      <>
        Drop a CSV, Excel, Stata <code className="font-mono">.dta</code>, or Parquet
        file. Up to 50&nbsp;MB.
      </>
    ),
  },
  inspect: {
    title: "Inspect your data",
    body: (
      <>
        Click any variable card to see its distribution, missing values, and run quick
        descriptives. Watch for the <span className="text-warn">missing</span> badges.
      </>
    ),
  },
  clean: {
    title: "Clean and recode",
    body: <>Drop test rows, recode categories, generate new variables. Phase 3.</>,
  },
  analyze: {
    title: "Run analyses",
    body: <>Descriptives, t-tests, ANOVA, regression. Phase 3.</>,
  },
  visualize: {
    title: "Plot it",
    body: <>Histograms, scatterplots, residuals. Phase 5.</>,
  },
  export: {
    title: "Export results",
    body: <>PDF, HTML, Word, or save the dataset back out. Phase 5.</>,
  },
};

export function WizardRail() {
  const step = useApp((s) => s.step);
  const setStep = useApp((s) => s.setStep);
  const dataset = useApp((s) => s.dataset);

  const activeIndex = STEPS.findIndex((s) => s.id === step);
  const help = HELP_BY_STEP[step];

  return (
    <aside className="border-r border-border bg-bg overflow-y-auto" style={{ padding: "24px 16px" }}>
      <div className="eyebrow px-2 pb-3">Workflow</div>

      {STEPS.map((s, i) => {
        const isActive = step === s.id;
        // A step is done if it's earlier than the active step AND a dataset is loaded
        // (until upload, "Import" is the only done-ish step once successful).
        const isDone = i < activeIndex && dataset != null;
        const isImportDone = s.id === "import" && dataset != null && step !== "import";
        const done = isDone || isImportDone;

        return (
          <button
            key={s.id}
            type="button"
            onClick={() => setStep(s.id)}
            aria-current={isActive ? "step" : undefined}
            className={`relative w-full flex items-center gap-3 px-3 py-[10px] rounded-sm mb-[2px] transition-colors text-left ${
              isActive
                ? "bg-surface text-text"
                : "text-text-muted hover:bg-surface hover:text-text"
            }`}
          >
            {isActive && (
              <span
                aria-hidden
                className="absolute left-0 top-2 bottom-2 w-[2px] bg-accent rounded-sm"
              />
            )}
            <span
              className={`flex-shrink-0 w-[22px] h-[22px] rounded-full border flex items-center justify-center font-mono text-[10px] font-semibold ${
                isActive
                  ? "bg-accent text-bg border-accent"
                  : done
                  ? "bg-good-soft text-good border-good"
                  : "border-border-strong text-text-muted"
              }`}
            >
              {done ? "✓" : i + 1}
            </span>
            <span className="text-[13px] font-medium tracking-[-0.005em]">{s.name}</span>
          </button>
        );
      })}

      <div className="h-px bg-border mx-2 my-4" />

      <div className="p-3 bg-surface border border-border rounded-md text-[12px] text-text-muted leading-[1.55] mt-2">
        <strong className="block mb-1 text-text font-medium font-serif italic text-[14px]">
          {help.title}
        </strong>
        {help.body}
      </div>
    </aside>
  );
}
