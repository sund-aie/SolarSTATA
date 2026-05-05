/* App shell: 56px topbar + mode-switched body.
 * Mode is preserved in the zustand store; switching never loses dataset
 * or selected-var state. */

import { Topbar } from "./components/Topbar";
import { GuidedMode } from "./modes/Guided";
import { ProMode } from "./modes/Pro";
import { useApp } from "./state/store";

function App() {
  const mode = useApp((s) => s.mode);

  return (
    <div className="grid h-screen relative" style={{ gridTemplateRows: "56px 1fr", zIndex: 2 }}>
      <Topbar />
      {mode === "guided" ? <GuidedMode /> : <ProMode />}
    </div>
  );
}

export default App;
