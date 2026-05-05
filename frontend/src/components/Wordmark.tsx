/* SolarSTATA wordmark — italic-serif "S" in gold, rest in sans. */

export function Wordmark() {
  return (
    <div className="flex items-baseline select-none">
      <span className="font-serif italic text-[26px] leading-none text-accent mr-px">S</span>
      <span className="font-sans text-[15px] font-medium tracking-[0.04em] text-text">
        olarSTATA
      </span>
      <span className="font-mono text-[10px] text-text-faint ml-2 px-[6px] py-[2px] border border-border rounded">
        v3.0.0a
      </span>
    </div>
  );
}
