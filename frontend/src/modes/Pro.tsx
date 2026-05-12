/* Pro mode: real Monaco editor + WebSocket-streamed Results.
 *
 * Layout:
 *   ┌──────┬─────────────┬─────────┐
 *   │      │  Editor     │         │
 *   │ Vars ├─────────────┤  Graphs │
 *   │      │  Results    │         │
 *   └──────┴─────────────┴─────────┘
 *   240px       1fr         360px
 *   rows: [1fr, 240px]
 *
 * Cmd/Ctrl+Enter executes; the visible Run ▶ button does the same. Results
 * stream back as discrete blocks and accumulate in a single scrolling
 * pre-block for that Stata feel.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { StataEditor, type StataEditorHandle } from "../components/StataEditor";
import { Plot, type PlotlyFigure } from "../components/Plot";
import { ProWsClient } from "../lib/wsClient";
import { useApp } from "../state/store";

interface Block {
  command: string;
  text: string;
  kind: string;
  ok: boolean;
}

interface GraphFrame {
  command: string;
  figure: PlotlyFigure;
  timestamp: number;
}

export function ProMode() {
  const columns = useApp((s) => s.columns);
  const appendCommand = useApp((s) => s.appendCommand);

  const [blocks, setBlocks] = useState<Block[]>([]);
  const [graphs, setGraphs] = useState<GraphFrame[]>([]);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<ProWsClient | null>(null);
  const connectedRef = useRef(false);
  const editorRef = useRef<StataEditorHandle | null>(null);
  const resultsEndRef = useRef<HTMLDivElement | null>(null);

  // Mirror the connected flag into a ref so any callback passed through to
  // Monaco can branch on the latest value without a stale-closure trap.
  connectedRef.current = connected;

  useEffect(() => {
    const ws = new ProWsClient();
    wsRef.current = ws;
    const off = ws.on((event) => {
      if (event.type === "open") setConnected(true);
      if (event.type === "close") setConnected(false);
      if (event.type === "started") {
        setBusy(true);
        setBlocks((prev) => [...prev, { command: event.command, text: `. ${event.command}\n`, kind: "command", ok: true }]);
      }
      if (event.type === "block") {
        setBlocks((prev) => [...prev, { command: event.command, text: event.text, kind: event.kind, ok: true }]);
      }
      if (event.type === "graph") {
        setGraphs((prev) => [{ command: event.command, figure: event.figure as PlotlyFigure, timestamp: Date.now() }, ...prev].slice(0, 8));
      }
      if (event.type === "history_appended") {
        appendCommand(event.command);
      }
      if (event.type === "complete") {
        setBusy(false);
      }
      if (event.type === "error") {
        setBusy(false);
        setBlocks((prev) => [...prev, {
          command: "",
          text: `error: ${event.detail}`,
          kind: "error",
          ok: false,
        }]);
      }
    });
    ws.open();
    return () => {
      off();
      ws.close();
    };
  }, [appendCommand]);

  useEffect(() => {
    resultsEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [blocks]);

  // Stable identity — Monaco binds this exact function at mount and our
  // StataEditor calls it via a ref so we never lose updates. Branches off
  // connectedRef so we surface a friendly error when the WS isn't ready.
  const onRun = useCallback((command: string) => {
    if (!wsRef.current) return;
    if (!connectedRef.current) {
      setBlocks((prev) => [...prev, {
        command,
        text: `error: WebSocket not connected yet — try again in a moment.`,
        kind: "error",
        ok: false,
      }]);
      return;
    }
    wsRef.current.send(command);
  }, []);

  const triggerRun = () => editorRef.current?.run();

  return (
    <div
      className="h-full grid bg-border"
      style={{ gridTemplateColumns: "240px 1fr 360px", gridTemplateRows: "1fr 240px", gap: "1px" }}
    >
      {/* Variables column */}
      <Pane className="row-span-2" titleLeft={`Variables · ${columns.length}`}>
        <div className="flex-1 overflow-y-auto py-2">
          {columns.length === 0 ? (
            <div className="px-4 text-[12px] text-text-faint">No dataset loaded</div>
          ) : (
            columns.map((c) => (
              <div
                key={c.name}
                className="flex items-center gap-[10px] px-4 py-[7px] text-[12px] cursor-pointer border-l-2 border-transparent hover:bg-surface hover:border-border-strong"
                title={c.label || c.name}
              >
                <span className="font-mono text-text flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{c.name}</span>
                <span className="font-mono text-[10px] text-text-faint">{c.stata_type ?? c.dtype}</span>
              </div>
            ))
          )}
        </div>
      </Pane>

      {/* Editor */}
      <Pane
        titleLeft="Command · do-file"
        titleRight={
          <div className="flex items-center gap-3">
            <span className={`font-mono text-[10px] uppercase tracking-[0.12em] ${connected ? "text-good" : "text-text-faint"}`}>
              {connected ? "● connected" : "○ disconnected"}
            </span>
            <button
              type="button"
              onClick={triggerRun}
              disabled={!connected || busy}
              aria-label="Run current line (Cmd/Ctrl+Enter)"
              title="Run current line · Cmd/Ctrl+Enter"
              className="inline-flex items-center gap-[6px] bg-accent text-bg px-3 py-[4px] rounded-sm font-mono text-[10px] uppercase tracking-[0.08em] font-semibold hover:brightness-110 active:translate-y-px disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg width="9" height="9" viewBox="0 0 10 10" aria-hidden>
                <path d="M2 1 L8 5 L2 9 Z" fill="currentColor" />
              </svg>
              {busy ? "Running" : "Run"}
              <span className="text-[9px] opacity-70 font-normal normal-case tracking-normal ml-1">⌘⏎</span>
            </button>
          </div>
        }
      >
        <StataEditor ref={editorRef} onRun={onRun} />
      </Pane>

      {/* Graphs — latest on top */}
      <Pane className="row-span-2" titleLeft={`Graphs · ${graphs.length}`}>
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {graphs.length === 0 && (
            <div className="text-text-faint text-[12px] text-center mt-10 px-4">
              <div className="font-serif italic text-[14px] mb-2">No plots yet</div>
              Run a graph command like <code className="font-mono">histogram plaque_index</code>
              {" "}or <code className="font-mono">scatter age plaque_index</code> to see it here.
            </div>
          )}
          {graphs.map((g) => (
            <div key={g.timestamp} className="bg-surface border border-border rounded-sm p-2">
              <div className="font-mono text-[10px] text-text-faint mb-1 truncate">{g.command}</div>
              <Plot figure={g.figure} height={220} />
            </div>
          ))}
        </div>
      </Pane>

      {/* Results */}
      <Pane titleLeft="Results" titleRight={busy ? <span className="text-accent">running…</span> : null}>
        <div className="flex-1 overflow-auto px-5 py-4 font-mono text-[12px] leading-[1.5] text-text">
          {blocks.length === 0 && (
            <Empty
              phase={3}
              headline="Run a command to stream results here"
              subline="Cmd/Ctrl+Enter on a line in the editor, or click ▶ Run above"
            />
          )}
          {blocks.map((b, i) => (
            <div key={i} className={`whitespace-pre-wrap ${b.ok ? "" : "text-warn"}`}>
              {b.text}
            </div>
          ))}
          <div ref={resultsEndRef} />
        </div>
      </Pane>
    </div>
  );
}

function Pane({
  children,
  className = "",
  titleLeft,
  titleRight,
}: {
  children: React.ReactNode;
  className?: string;
  titleLeft: React.ReactNode;
  titleRight?: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col bg-bg overflow-hidden relative ${className}`}>
      <div className="flex items-center justify-between px-4 py-[10px] border-b border-border flex-shrink-0">
        <span className="font-mono text-[10px] text-text-faint uppercase tracking-[0.12em]">
          {titleLeft}
        </span>
        {titleRight && <div>{titleRight}</div>}
      </div>
      {children}
    </div>
  );
}

function Empty({ phase, headline, subline }: { phase: number; headline: string; subline: string }) {
  return (
    <div className="flex-1 flex items-center justify-center flex-col gap-2 text-text-faint text-[12px] text-center px-5">
      <span className="inline-flex items-center gap-[6px] px-[10px] py-1 bg-surface border border-border rounded-full font-mono text-[10px] text-text-muted tracking-[0.04em]">
        <span className="w-[5px] h-[5px] rounded-full bg-accent" aria-hidden />
        Phase {phase}
      </span>
      <div className="mt-[6px]">{headline}</div>
      <div className="text-[11px] opacity-70">{subline}</div>
    </div>
  );
}
