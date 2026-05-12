/* Settings flyout, anchored under the topbar settings icon.
 *
 * Phase 5 content:
 *   - Theme toggle (dark / light), persisted to localStorage.
 *   - Workspace download — exports the active dataset + e() + command
 *     history as a single JSON the user can later re-upload from the
 *     Import step.
 */

import { useEffect, useRef, useState } from "react";
import { useTheme } from "../state/theme";
import { useApp } from "../state/store";
import { api, ApiError } from "../lib/api";

interface Props {
  onClose: () => void;
}

export function SettingsMenu({ onClose }: Props) {
  const theme = useTheme((s) => s.theme);
  const setTheme = useTheme((s) => s.setTheme);
  const dataset = useApp((s) => s.dataset);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const onDownloadWorkspace = async () => {
    setBusy(true); setError(null);
    try {
      const blob = await api.downloadWorkspace();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "solarstata.workspace.json";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      ref={panelRef}
      className="fixed top-[56px] right-4 mt-1 w-[280px] bg-surface border border-border rounded-md shadow-elevated z-50 p-4"
      role="menu"
    >
      <div className="eyebrow mb-3">Theme</div>
      <div className="flex items-center gap-2 mb-5">
        <ThemeButton active={theme === "dark"} onClick={() => setTheme("dark")} label="Dark" />
        <ThemeButton active={theme === "light"} onClick={() => setTheme("light")} label="Light" />
      </div>

      <div className="eyebrow mb-3">Workspace</div>
      <button
        type="button"
        onClick={onDownloadWorkspace}
        disabled={busy || !dataset}
        className="run-btn-secondary disabled:opacity-60"
      >
        {busy ? "Saving…" : "Download workspace"}
      </button>
      <div className="text-[11px] text-text-faint mt-2 leading-snug">
        Saves the current dataset + e() + command history as a single JSON file.
        Restore it from the Import step on any machine.
      </div>
      {error && <div className="mt-3 text-[12px] text-warn">{error}</div>}
    </div>
  );
}

function ThemeButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 px-3 py-[6px] rounded-sm text-[12px] font-medium border transition-colors ${
        active
          ? "bg-accent text-bg border-accent"
          : "bg-bg text-text-muted border-border hover:text-text hover:border-border-strong"
      }`}
    >
      {label}
    </button>
  );
}
