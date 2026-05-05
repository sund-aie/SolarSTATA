/* Pro-mode Monaco placeholder. Renders a realistic-looking Stata snippet
 * with manual syntax-highlighting classes (line numbers, keywords in gold,
 * variables in blue, options in green, comments in faint italic).
 *
 * The real Monaco + Stata language definition lands in Phase 3. */

interface Line {
  text: React.ReactNode;
  highlight?: boolean;
}

const LINES: Line[] = [
  { text: <span className="text-text-faint italic">// Phase 3: Stata syntax + autocomplete + live execution</span> },
  { text: <span className="text-text-faint italic">// For now this is a layout placeholder</span> },
  { text: " " },
  {
    highlight: true,
    text: (
      <>
        <span style={{ color: "var(--accent)" }}>summarize</span>{" "}
        <span style={{ color: "var(--info)" }}>plaque_index gingival_index periodontal_pocket_depth_mm</span>
        <span style={{ color: "var(--good)" }}>, detail</span>
      </>
    ),
  },
  { text: " " },
  {
    text: (
      <>
        <span style={{ color: "var(--accent)" }}>tabulate</span>{" "}
        <span style={{ color: "var(--info)" }}>education_level smoking</span>
        <span style={{ color: "var(--good)" }}>, row chi2</span>
      </>
    ),
  },
  { text: " " },
  {
    text: (
      <>
        <span style={{ color: "var(--accent)" }}>regress</span>{" "}
        <span style={{ color: "var(--info)" }}>plaque_index age sex brushing_freq</span>
        <span style={{ color: "var(--good)" }}>, vce(robust)</span>
      </>
    ),
  },
];

export function EditorMock() {
  return (
    <div
      className="flex-1 px-5 py-4 font-mono text-[13px] leading-[1.7] overflow-auto bg-bg"
      role="region"
      aria-label="Command editor placeholder"
    >
      {LINES.map((line, i) => (
        <div
          key={i}
          className={
            line.highlight
              ? "-ml-5 pl-[18px] border-l-2 border-accent"
              : ""
          }
          style={line.highlight ? { background: "rgba(212, 179, 106, 0.06)" } : undefined}
        >
          <span className="text-text-faint mr-4 inline-block w-[22px] text-right select-none">
            {i + 1}
          </span>
          {line.text}
        </div>
      ))}
    </div>
  );
}
