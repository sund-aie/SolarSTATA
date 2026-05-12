/* Monaco editor wired with the custom Stata language.
 *
 * Behaviour:
 *   - Cmd/Ctrl+Enter executes the current line OR the selected range.
 *   - The parent can also call .run() via the forwarded ref (Run button).
 *   - ArrowUp on a blank/topmost line cycles through command history.
 *   - Editor tracks dataset variable list for autocomplete.
 *
 * Two key correctness rules so the keybinding survives prop changes:
 *   1. `onRun` is mirrored into a ref every render. Monaco's command
 *      callback reads `onRunRef.current` so it always sees the latest
 *      handler. Without this we get the famous stale-closure bug:
 *      Pro.tsx's first onRun captures `connected === false`, Monaco
 *      binds *that* closure at mount, and Cmd+Enter silently no-ops
 *      forever even after the WebSocket connects.
 *   2. The actual `runFromEditor` closure body uses the ref too — it's
 *      idempotent across re-renders, so the keybinding never goes
 *      stale.
 */

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import * as monacoNs from "monaco-editor";
import { registerStataLanguage, setVariableProvider } from "../lib/stataLang";
import { useApp } from "../state/store";

export interface StataEditorHandle {
  /** Run the current line (or selection). Used by the visible Run button. */
  run: () => void;
}

interface Props {
  onRun: (command: string) => void;
}

export const StataEditor = forwardRef<StataEditorHandle, Props>(function StataEditor(
  { onRun },
  ref,
) {
  const editorRef = useRef<monacoNs.editor.IStandaloneCodeEditor | null>(null);
  const historyRef = useRef<string[]>([]);
  const historyIndexRef = useRef<number>(-1);
  const onRunRef = useRef(onRun);

  // Keep ref pointing at the latest onRun every render so the keybinding
  // (registered once at mount) always invokes the current handler.
  onRunRef.current = onRun;

  const columns = useApp((s) => s.columns);
  const history = useApp((s) => s.commandHistory);

  useEffect(() => {
    setVariableProvider(() => columns.map((c) => c.name));
  }, [columns]);

  useEffect(() => {
    historyRef.current = history;
    historyIndexRef.current = history.length;
  }, [history]);

  const runFromEditor = () => {
    const editor = editorRef.current;
    if (!editor) return;
    const sel = editor.getSelection();
    const model = editor.getModel();
    if (!sel || !model) return;

    let cmd: string;
    if (!sel.isEmpty()) {
      cmd = model.getValueInRange(sel).trim();
    } else {
      cmd = model.getLineContent(sel.startLineNumber).trim();
    }
    if (cmd) onRunRef.current(cmd);
  };

  useImperativeHandle(ref, () => ({ run: runFromEditor }), []);

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    registerStataLanguage(monaco);

    const model = editor.getModel();
    if (model) monaco.editor.setModelLanguage(model, "stata");

    // Cmd/Ctrl+Enter → run current line or selection. Important: the callback
    // is bound exactly once and reads onRunRef.current at call time so it
    // never goes stale.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      runFromEditor();
    });

    // Arrow-up on first or empty line cycles backwards through history.
    editor.addCommand(monaco.KeyCode.UpArrow, () => {
      const sel = editor.getSelection();
      if (!sel) return;
      const m = editor.getModel();
      if (!m) return;

      const isEmptyLine = m.getLineContent(sel.startLineNumber).trim() === "";
      const onFirstLine = sel.startLineNumber === 1;

      if (!(isEmptyLine || onFirstLine)) {
        editor.trigger("history-up", "cursorUp", null);
        return;
      }
      const h = historyRef.current;
      if (h.length === 0) return;
      historyIndexRef.current = Math.max(0, historyIndexRef.current - 1);
      const cmd = h[historyIndexRef.current] ?? "";
      const lineNumber = sel.startLineNumber;
      const lineLength = m.getLineMaxColumn(lineNumber);
      editor.executeEdits("history-up", [{
        range: new monaco.Range(lineNumber, 1, lineNumber, lineLength),
        text: cmd,
        forceMoveMarkers: true,
      }]);
      editor.setPosition({ lineNumber, column: cmd.length + 1 });
    });

    editor.addCommand(monaco.KeyCode.DownArrow, () => {
      const sel = editor.getSelection();
      const m = editor.getModel();
      if (!sel || !m) return;

      const isEmptyLine = m.getLineContent(sel.startLineNumber).trim() === "";
      const lastLine = m.getLineCount();
      const onLastLine = sel.startLineNumber === lastLine;

      if (!(isEmptyLine || onLastLine)) {
        editor.trigger("history-down", "cursorDown", null);
        return;
      }
      const h = historyRef.current;
      if (h.length === 0) return;
      historyIndexRef.current = Math.min(h.length, historyIndexRef.current + 1);
      const cmd = h[historyIndexRef.current] ?? "";
      const lineNumber = sel.startLineNumber;
      const lineLength = m.getLineMaxColumn(lineNumber);
      editor.executeEdits("history-down", [{
        range: new monaco.Range(lineNumber, 1, lineNumber, lineLength),
        text: cmd,
        forceMoveMarkers: true,
      }]);
      editor.setPosition({ lineNumber, column: cmd.length + 1 });
    });
  };

  return (
    <Editor
      defaultLanguage="stata"
      defaultValue={`// SolarSTATA Pro mode
// Cmd/Ctrl+Enter runs current line. Click ▶ Run for the same thing.

summarize plaque_index gingival_index periodontal_pocket_depth_mm
`}
      theme="solarstata"
      onMount={handleMount}
      options={{
        fontFamily: "Geist Mono, SF Mono, monospace",
        fontSize: 13,
        lineHeight: 22,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        renderLineHighlight: "line",
        padding: { top: 12, bottom: 12 },
        scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
      }}
    />
  );
});
