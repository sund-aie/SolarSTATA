/* Import step: drag-and-drop a dataset. Posts to /api/data/upload.
 *
 * For multi-sheet xlsx files the backend stages the file and returns a
 * `requires_choice` payload; we then walk the user through a sheet picker
 * + header row picker before calling /api/data/upload/finalize. CSV / dta /
 * parquet / single-sheet xlsx still complete in one round trip.
 */

import { useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useApp } from "../state/store";
import type { StagedSheet, StagedUploadResponse, UploadResponse } from "../lib/types";
import { isStagedResponse } from "../lib/types";
import { FormatGuide } from "../components/FormatGuide";
import { SheetPicker } from "../components/SheetPicker";
import { HeaderRowPicker } from "../components/HeaderRowPicker";

const ACCEPT = ".csv,.tsv,.txt,.xlsx,.xls,.dta,.parquet,.pq";

type Phase =
  | { kind: "drop" }
  | { kind: "picking_sheet"; staged: StagedUploadResponse }
  | { kind: "picking_header"; staged: StagedUploadResponse; sheet: StagedSheet }
  | { kind: "finalizing" };

export function ImportStep() {
  const setDataset = useApp((s) => s.setDataset);
  const appendCommand = useApp((s) => s.appendCommand);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "drop" });

  const commitDataset = async (upload: UploadResponse) => {
    const columns = await api.columns(upload.frame);
    setDataset(
      {
        filename: upload.filename,
        n_obs: upload.n_obs,
        n_vars: upload.n_vars,
        columns: upload.columns,
      },
      columns.columns,
    );
    appendCommand(`use "${upload.filename}", clear`);
  };

  const handleFile = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.upload(file);
      if (isStagedResponse(result)) {
        // Skip the sheet picker for single-sheet workbooks but always show
        // the header picker — that's where the "TIDY LONG FORMAT" gotcha is.
        if (result.sheets.length === 1) {
          setPhase({ kind: "picking_header", staged: result, sheet: result.sheets[0]! });
        } else {
          setPhase({ kind: "picking_sheet", staged: result });
        }
        return;
      }
      await commitDataset(result);
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onPickSheet = (sheet: StagedSheet) => {
    if (phase.kind !== "picking_sheet") return;
    setPhase({ kind: "picking_header", staged: phase.staged, sheet });
  };

  const onConfirmHeader = async (headerRow: number) => {
    if (phase.kind !== "picking_header") return;
    setBusy(true);
    setError(null);
    try {
      const upload = await api.finalizeUpload({
        file_id: phase.staged.file_id,
        sheet: phase.sheet.name,
        header_row: headerRow,
      });
      await commitDataset(upload);
      setPhase({ kind: "drop" });
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onCancelPicker = () => {
    // Reset every piece of state the picker touched: phase back to drop,
    // any error cleared, the busy flag cleared (in case the user hits
    // Cancel while we're still racing the upload), and the file-input ref
    // value blanked so re-selecting the same file fires a fresh change
    // event. Without that last bit the dropzone looked "stuck" on the
    // second attempt because <input type=file> dedupes identical paths.
    setPhase({ kind: "drop" });
    setError(null);
    setBusy(false);
    setDragOver(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="step-pane overflow-y-auto px-10 py-8 pb-20">
      <div className="mb-8">
        <div className="eyebrow mb-2">Step 1 of 6</div>
        <h1 className="font-serif text-[32px] leading-[1.15] text-text tracking-[-0.01em] mb-1">
          Bring in your <em className="text-accent italic">dataset</em>
        </h1>
        <p className="text-text-muted text-[14px] max-w-[520px]">
          Drop a CSV, Excel, Stata <code className="font-mono">.dta</code>, or Parquet file.
          Variables and types are detected automatically.
        </p>
      </div>

      {phase.kind === "drop" && (
        <>
          <FormatGuide />
          <div
            role="button"
            tabIndex={0}
            aria-label="Drop dataset file here or click to choose"
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files[0];
              if (f) handleFile(f);
            }}
            className={`flex flex-col items-center justify-center text-center p-16 rounded-md border-2 border-dashed transition-colors cursor-pointer ${
              dragOver ? "border-accent bg-accent-soft" : "border-border bg-surface"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
                e.target.value = "";
              }}
            />
            <div className="font-serif italic text-[20px] text-text mb-1">
              {busy ? "Loading…" : "Drop your file here"}
            </div>
            <div className="text-text-muted text-[13px] mb-4">
              or click to browse — CSV, Excel, .dta, Parquet, up to 50&nbsp;MB
            </div>
            <span className="font-mono text-[10px] text-text-faint uppercase tracking-[0.12em]">
              {ACCEPT.split(",").join(" · ")}
            </span>
          </div>

          <WorkspaceRestore onError={setError} onLoaded={commitDataset} />
        </>
      )}

      {phase.kind === "picking_sheet" && (
        <SheetPicker
          filename={phase.staged.original_filename}
          sheets={phase.staged.sheets}
          onPick={onPickSheet}
          onCancel={onCancelPicker}
        />
      )}

      {phase.kind === "picking_header" && (
        <HeaderRowPicker
          fileId={phase.staged.file_id}
          filename={phase.staged.original_filename}
          sheet={phase.sheet}
          onConfirm={onConfirmHeader}
          onBack={() =>
            phase.staged.sheets.length > 1
              ? setPhase({ kind: "picking_sheet", staged: phase.staged })
              : onCancelPicker()
          }
        />
      )}

      {phase.kind === "finalizing" && (
        <div className="text-text-muted text-[13px]">Loading…</div>
      )}

      {error && (
        <div className="mt-4 p-3 bg-warn-soft border border-warn rounded-sm text-warn text-[13px]">
          {error}
        </div>
      )}
    </div>
  );
}

// Workspace-restore zone shown alongside the regular dropzone.
function WorkspaceRestore({
  onError,
  onLoaded,
}: {
  onError: (msg: string) => void;
  onLoaded: (resp: UploadResponse) => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const handleFile = async (file: File) => {
    setBusy(true);
    onError("");
    try {
      const resp = await api.uploadWorkspace(file);
      await onLoaded(resp);
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 flex items-center gap-3 bg-surface border border-border rounded-sm p-3 text-[12px] text-text-muted">
      <input
        ref={inputRef}
        type="file"
        accept=".json"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
          e.target.value = "";
        }}
      />
      <span className="font-serif italic">Have a workspace JSON?</span>
      <span className="flex-1">Restore your dataset + e() + command history from a previous session.</span>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="run-btn-secondary !w-auto disabled:opacity-60"
      >
        {busy ? "Restoring…" : "Upload workspace"}
      </button>
    </div>
  );
}
