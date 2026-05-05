/* "Pro command equivalent" footer. Shows the Stata syntax the current
 * Guided action maps to, with a copy button. Phase 2: just plain text +
 * a manual keyword/var coloring hack. */

import { useState } from "react";

interface Props {
  command: string;
}

export function CommandPreview({ command }: Props) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // Clipboard blocked (e.g. test env) — silent
    }
  };

  return (
    <div className="mt-auto px-6 py-4 bg-surface border-t border-border">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[10px] text-text-faint uppercase tracking-[0.12em]">
          Pro command equivalent
        </span>
        <button
          type="button"
          onClick={onCopy}
          className="font-mono text-[10px] text-text-muted hover:text-accent hover:bg-accent-soft px-[6px] py-[2px] rounded"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className="font-mono text-[12px] text-text px-3 py-[10px] bg-bg border border-border rounded-sm leading-[1.5]">
        {renderHighlighted(command)}
      </div>
    </div>
  );
}

/** Manual keyword/varname highlighting — not a real lexer. Phase 3 swaps this
 * for the Monaco Stata language. The first whitespace-delimited token is the
 * keyword (gold); everything else is a variable name (blue) until we hit a
 * comma, after which everything is options (green). */
function renderHighlighted(cmd: string) {
  const trimmed = cmd.trim();
  const [head, ...rest] = trimmed.split(/\s+/);
  const remainder = rest.join(" ");
  const [varsPart, optsPart] = remainder.includes(",")
    ? remainder.split(/,(.*)/).map((s) => s.trim())
    : [remainder, ""];

  return (
    <>
      <span style={{ color: "var(--accent)" }}>{head}</span>
      {varsPart && (
        <>
          {" "}
          <span style={{ color: "var(--info)" }}>{varsPart}</span>
        </>
      )}
      {optsPart && (
        <>
          <span>, </span>
          <span style={{ color: "var(--good)" }}>{optsPart}</span>
        </>
      )}
    </>
  );
}
