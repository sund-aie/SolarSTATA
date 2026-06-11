/* Guided mode: 3-column layout (wizard rail · step pane · inspect rail).
 * Step content is swapped based on store.step. Inspect rail only renders
 * during the Inspect step and only when a variable is selected. */

import { useApp } from "../state/store";
import { WizardRail } from "../components/WizardRail";
import { ImportStep } from "../steps/ImportStep";
import { InspectStep } from "../steps/InspectStep";
import { AnalyzeStep } from "../steps/AnalyzeStep";
import { VisualizeStep } from "../steps/VisualizeStep";
import { ExportStep } from "../steps/ExportStep";
import { InspectPanel } from "../components/InspectPanel";
import { ResultsCard } from "../components/ResultsCard";

export function GuidedMode() {
  const step = useApp((s) => s.step);
  const dataset = useApp((s) => s.dataset);
  const columns = useApp((s) => s.columns);
  const selectedVar = useApp((s) => s.selectedVar);
  const selectedInfo = columns.find((c) => c.name === selectedVar) ?? null;

  // Inspect rail is only meaningful during the Inspect step. For Phase 2,
  // other steps show a stubbed empty rail to preserve the 380px column width.
  const showInspect = step === "inspect";

  return (
    <div
      className="h-full grid overflow-hidden"
      style={{ gridTemplateColumns: dataset ? "240px 1fr 380px" : "240px 1fr" }}
    >
      <WizardRail />
      <main className="overflow-y-auto min-h-0">
        {!dataset && step === "import" && <ImportStep />}
        {dataset && step === "import" && <ImportStep />}
        {dataset && step === "inspect" && <InspectStep />}
        {dataset && step === "analyze" && <AnalyzeStep />}
        {dataset && step === "visualize" && <VisualizeStep />}
        {dataset && step === "export" && <ExportStep />}
      </main>
      {dataset && (showInspect ? (
        selectedInfo ? (
          <InspectPanel info={selectedInfo} />
        ) : (
          <aside className="border-l border-border bg-bg flex flex-col">
            <div className="px-6 py-16 text-center text-text-muted text-[13px]">
              <div className="font-serif italic text-[16px] mb-2">No variable selected</div>
              Click a card to inspect it.
            </div>
          </aside>
        )
      ) : (
        <aside className="border-l border-border bg-bg flex flex-col">
          <div className="px-6 py-8">
            <div className="eyebrow mb-3">Notes</div>
            <ResultsCard title="What's loaded">
              <div className="font-mono text-[12px] text-text-muted space-y-1">
                <div>{dataset.filename}</div>
                <div>{dataset.n_obs.toLocaleString()} obs × {dataset.n_vars} vars</div>
              </div>
            </ResultsCard>
          </div>
        </aside>
      ))}
    </div>
  );
}
