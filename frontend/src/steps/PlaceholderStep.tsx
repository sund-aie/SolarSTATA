/* Generic step stub for Clean / Analyze / Visualize / Export — full content lands later phases. */

interface Props {
  step: string;
  number: number;
  phaseLandsIn: number;
  blurb: string;
}

export function PlaceholderStep({ step, number, phaseLandsIn, blurb }: Props) {
  return (
    <div className="overflow-y-auto px-10 py-8 pb-20">
      <div className="mb-8">
        <div className="eyebrow mb-2">Step {number} of 6</div>
        <h1 className="font-serif text-[32px] leading-[1.15] text-text tracking-[-0.01em] mb-1">
          {step}
        </h1>
        <p className="text-text-muted text-[14px] max-w-[520px]">{blurb}</p>
      </div>
      <div className="flex items-center gap-3 px-5 py-4 bg-surface border border-border rounded-md max-w-[420px]">
        <span className="inline-flex items-center gap-[6px] px-[10px] py-1 bg-bg border border-border rounded-full font-mono text-[10px] text-text-muted tracking-[0.04em]">
          <span className="w-[5px] h-[5px] rounded-full bg-accent" aria-hidden />
          Phase {phaseLandsIn}
        </span>
        <span className="text-text-muted text-[13px]">Lands in Phase {phaseLandsIn}</span>
      </div>
    </div>
  );
}
