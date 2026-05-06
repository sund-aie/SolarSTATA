/* App shell: 56px topbar + mode-switched body.
 * Mode is preserved in the zustand store; switching never loses dataset
 * or selected-var state. Pro mode is lazy-loaded so Monaco only enters
 * the bundle (and the test runtime) when the user actually opens it. */

import { Suspense, lazy } from "react";
import { Topbar } from "./components/Topbar";
import { GuidedMode } from "./modes/Guided";
import { useApp } from "./state/store";

const ProMode = lazy(() => import("./modes/Pro").then((m) => ({ default: m.ProMode })));

function App() {
  const mode = useApp((s) => s.mode);

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
