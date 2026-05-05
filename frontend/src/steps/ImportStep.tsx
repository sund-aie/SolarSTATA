/* Import step: drag-and-drop a dataset. Posts to /api/data/upload, then
 * fetches /api/data/columns and pushes both into the store. */

import { useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useApp } from "../state/store";

const ACCEPT = ".csv,.tsv,.txt,.xlsx,.xls,.dta,.parquet,.pq";

export function ImportStep() {
  const setDataset = useApp((s) => s.setDataset);
  const appendCommand = useApp((s) => s.appendCommand);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const upload = await api.upload(file);
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
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else setError(String(err));
    } finally {
      setBusy(false);
    }
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
          {busy ? "Loading..." : "Drop your file here"}
        </div>
        <div className="text-text-muted text-[13px] mb-4">
          or click to browse — CSV, Excel, .dta, Parquet, up to 50&nbsp;MB
        </div>
        <span className="font-mono text-[10px] text-text-faint uppercase tracking-[0.12em]">
          {ACCEPT.split(",").join(" · ")}
        </span>
      </div>

      {error && (
        <div className="mt-4 p-3 bg-warn-soft border border-warn rounded-sm text-warn text-[13px]">
          {error}
        </div>
      )}
    </div>
  );
}
