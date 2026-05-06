/* Custom Stata language for Monaco.
 *
 * Phase 3 scope:
 *   - Highlight commands (gold), factor-variable notation (info blue),
 *     options after `,` (good green), if/in qualifiers (gold), comments
 *     (faint italic), strings (warm).
 *   - Completion: variable names (from the loaded dataset), command names,
 *     common per-command option names.
 *
 * The language id is `stata`. Editors register the lang once and call
 * `setVariableProvider` whenever the dataset changes.
 */

import type * as MonacoNS from "monaco-editor";

const COMMANDS = [
  "summarize", "summarize,", "tabulate", "tab",
  "regress", "logit", "logistic", "predict", "margins",
  "test", "lincom", "estat", "by", "bysort",
  "if", "in", "use", "save", "clear",
];

const COMMAND_KEYWORDS = [
  "summarize", "summary", "sum", "tabulate", "tab",
  "regress", "reg", "logit", "logistic", "predict", "margins",
  "test", "lincom", "estat", "by", "bysort", "if", "in",
  "use", "save", "clear",
];

const OPTION_HINTS: Record<string, string[]> = {
  regress: ["vce(robust)", "vce(hc3)", "vce(cluster )", "noheader", "level(95)", "noconstant"],
  logit:    ["or", "vce(robust)", "vce(cluster )", "level(95)", "nolog"],
  logistic: ["vce(robust)", "vce(cluster )", "level(95)", "nolog"],
  summarize: ["detail", "format"],
  tabulate:  ["chi2", "row", "column", "missing"],
  predict:   ["xb", "resid", "pr", "stdp"],
  margins:   ["atmeans", "dydx(*)"],
  estat:     ["ic", "vif"],
};

let variableProvider: () => string[] = () => [];

export function setVariableProvider(fn: () => string[]) {
  variableProvider = fn;
}

let registered = false;

export function registerStataLanguage(monaco: typeof MonacoNS) {
  if (registered) return;
  registered = true;

  monaco.languages.register({ id: "stata" });

  monaco.languages.setMonarchTokensProvider("stata", {
    defaultToken: "",
    tokenPostfix: ".stata",

    keywords: COMMAND_KEYWORDS,

    operators: ["==", "!=", "<=", ">=", "&&", "||", "&", "|", "+", "-", "*", "/", "<", ">", "=", "!"],

    tokenizer: {
      root: [
        // Comments
        [/^\s*\*.*$/, "comment.line"],
        [/\/\/.*$/, "comment.line"],
        [/\/\*/, "comment.block", "@comment"],

        // Strings
        [/"([^"\\]|\\.)*$/, "string.invalid"],
        [/"/, { token: "string.quote", bracket: "@open", next: "@string" }],

        // Factor-variable notation (i.var, c.var, ##, #)
        [/\b(i|c)\./, "type.factor"],
        [/##|#/, "operator.factor"],

        // Options block: anything after a `,` until end of line (rough)
        [/,/, { token: "delimiter.options", next: "@options" }],

        // Numbers
        [/\b\d+\.?\d*\b/, "number"],

        // Identifiers (must come BEFORE keyword check via cases below)
        [/[a-zA-Z_][\w_]*/, {
          cases: {
            "@keywords": "keyword",
            "@default": "identifier",
          },
        }],
      ],

      options: [
        [/[a-zA-Z_][\w_]*/, "variable.option"],
        [/\(/, "delimiter.parens", "@option_args"],
        [/[ \t]+/, "white"],
        [/$/, "", "@pop"],
      ],

      option_args: [
        [/[^()]+/, "string"],
        [/\(/, "delimiter.parens", "@push"],
        [/\)/, "delimiter.parens", "@pop"],
      ],

      string: [
        [/[^\\"]+/, "string"],
        [/\\./, "string.escape"],
        [/"/, { token: "string.quote", bracket: "@close", next: "@pop" }],
      ],

      comment: [
        [/[^\/*]+/, "comment.block"],
        [/\*\//, "comment.block", "@pop"],
        [/[\/*]/, "comment.block"],
      ],
    },
  } as any);

  // Theme tokens — wired into a custom theme below.
  monaco.editor.defineTheme("solarstata", {
    base: "vs-dark",
    inherit: true,
    colors: {
      "editor.background":       "#16140F",
      "editor.foreground":       "#ECE7DA",
      "editorLineNumber.foreground":       "#5C5648",
      "editorLineNumber.activeForeground": "#968E7D",
      "editor.lineHighlightBackground":    "#1E1B16",
      "editorCursor.foreground": "#D4B36A",
      "editor.selectionBackground": "#2F2A22",
    },
    rules: [
      { token: "keyword",            foreground: "D4B36A", fontStyle: "bold" },
      { token: "type.factor",        foreground: "8FA8C4" },
      { token: "operator.factor",    foreground: "8FA8C4" },
      { token: "variable.option",    foreground: "8FAA88" },
      { token: "delimiter.options",  foreground: "8FAA88" },
      { token: "comment.line",       foreground: "5C5648", fontStyle: "italic" },
      { token: "comment.block",      foreground: "5C5648", fontStyle: "italic" },
      { token: "string",             foreground: "D89B7E" },
      { token: "string.quote",       foreground: "D89B7E" },
      { token: "number",             foreground: "8FA8C4" },
      { token: "identifier",         foreground: "ECE7DA" },
    ],
  });

  monaco.languages.registerCompletionItemProvider("stata", {
    triggerCharacters: [".", " ", "(", ","],
    provideCompletionItems: (model, position) => {
      const text = model.getLineContent(position.lineNumber);
      const upToCursor = text.substring(0, position.column - 1);

      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };

      const inOptions = upToCursor.includes(",");
      const firstToken = upToCursor.trim().split(/\s+/)[0]?.toLowerCase() ?? "";

      const suggestions: MonacoNS.languages.CompletionItem[] = [];

      // Variable names (after the command keyword)
      if (!inOptions && firstToken && COMMAND_KEYWORDS.includes(firstToken)) {
        for (const v of variableProvider()) {
          suggestions.push({
            label: v,
            kind: monaco.languages.CompletionItemKind.Variable,
            insertText: v,
            range,
          });
          // Also offer i. / c. variants for shortcut users
          suggestions.push({
            label: `i.${v}`,
            kind: monaco.languages.CompletionItemKind.Property,
            insertText: `i.${v}`,
            detail: "categorical",
            range,
          });
          suggestions.push({
            label: `c.${v}`,
            kind: monaco.languages.CompletionItemKind.Property,
            insertText: `c.${v}`,
            detail: "continuous",
            range,
          });
        }
      } else if (!firstToken || !COMMAND_KEYWORDS.includes(firstToken)) {
        // First token of line — suggest commands
        for (const cmd of COMMANDS) {
          suggestions.push({
            label: cmd,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: cmd,
            range,
          });
        }
      }

      // Options after `,`
      if (inOptions) {
        const opts = OPTION_HINTS[firstToken] ?? [];
        for (const o of opts) {
          suggestions.push({
            label: o,
            kind: monaco.languages.CompletionItemKind.Property,
            insertText: o,
            range,
          });
        }
      }

      return { suggestions };
    },
  });
}
