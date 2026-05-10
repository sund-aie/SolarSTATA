/* App shell: 56px topbar + mode-switched body.
 * Mode is preserved in the zustand store; switching never loses dataset
 * or selected-var state. Pro mode is lazy-loaded so Monaco only enters
 * the bundle (and the test runtime) when the user actually opens it. */

import { Suspense, lazy, useEffect } from "react";
import { Topbar } from "./components/Topbar";
import { GuidedMode } from "./modes/Guided";
import { HelpPanel } from "./components/HelpPanel";
import { useApp } from "./state/store";

const ProMode = lazy(() => import("./modes/Pro").then((m) => ({ default: m.ProMode })));

function App() {
  const mode = useApp((s) => s.mode);
  const helpOpen = useApp((s) => s.helpOpen);
  const toggleHelp = useApp((s) => s.toggleHelp);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // `?` opens help; Escape closes it. Skip when typing in inputs / Monaco.
      const target = e.target as HTMLElement | null;
      const inEditable = !!target && (
        target.isContentEditable
        || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
      );
      if (e.key === "?" && !inEditable) {
        e.preventDefault();
        toggleHelp(true);
      }
      if (e.key === "Escape" && helpOpen) {
        toggleHelp(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [helpOpen, toggleHelp]);

  return (
    <div className="grid h-screen relative" style={{ gridTemplateRows: "56px 1fr", zIndex: 2 }}>
      <Topbar />
      {mode === "guided" ? (
        <GuidedMode />
      ) : (
        <Suspense fallback={<ProFallback />}>
          <ProMode />
        </Suspense>
      )}
      {helpOpen && <HelpPanel onClose={() => toggleHelp(false)} />}
    </div>
  );
}

function ProFallback() {
  return (
    <div className="flex items-center justify-center text-text-muted text-[13px] font-mono">
      Loading Pro mode…
    </div>
  );
}

export default App;
