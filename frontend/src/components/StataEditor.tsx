/* Monaco editor wired with the custom Stata language.
 *
 * Behaviour:
 *   - Cmd/Ctrl+Enter executes the current line OR the selected range.
 *   - ArrowUp on a blank/topmost line cycles through command history.
 *   - Editor tracks dataset variable list for autocomplete.
 */

import { useEffect, useRef } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import * as monacoNs from "monaco-editor";
import { registerStataLanguage, setVariableProvider } from "../lib/stataLang";
import { useApp } from "../state/store";

interface Props {
  onRun: (command: string) => void;
}

export function StataEditor({ onRun }: Props) {
  const editorRef = useRef<monacoNs.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof monacoNs | null>(null);
  const historyRef = useRef<string[]>([]);
  const historyIndexRef = useRef<number>(-1);

  const columns = useApp((s) => s.columns);
  const history = useApp((s) => s.commandHistory);

  // Keep the variable provider fresh for autocomplete.
  useEffect(() => {
    setVariableProvider(() => columns.map((c) => c.name));
  }, [columns]);

  // Sync ref so the keybinding handler sees the latest history.
  useEffect(() => {
    historyRef.current = history;
    historyIndexRef.current = history.length;
  }, [history]);

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    registerStataLanguage(monaco);

    const model = editor.getModel();
    if (model) monaco.editor.setModelLanguage(model, "stata");

    // Cmd/Ctrl+Enter → run current line or selection
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      runFromEditor();
    });

    // Arrow-up on the first line OR on an empty line cycles history.
    editor.addCommand(monaco.KeyCode.UpArrow, () => {
      const sel = editor.getSelection();
      if (!sel) return;
      const m = editor.getModel();
      if (!m) return;

      const isEmptyLine = m.getLineContent(sel.startLineNumber).trim() === "";
      const onFirstLine = sel.startLineNumber === 1;

      if (!(isEmptyLine || onFirstLine)) {
        // Default behaviour: move cursor up
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
    if (cmd) onRun(cmd);
  };

  return (
    <Editor
      defaultLanguage="stata"
      defaultValue={`// SolarSTATA Pro mode
// Cmd/Ctrl+Enter runs current line. ArrowUp on a blank line recalls history.

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
}
