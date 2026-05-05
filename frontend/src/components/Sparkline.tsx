/* Mini bar histogram. Bars stretch to fill width; height encodes count.
 *
 * Used both inside variable cards (height ~26px) and any other
 * place we need a compact distribution at a glance. */

interface Props {
  data: number[];
  height?: number;
  variant?: "card" | "panel";
  className?: string;
}

export function Sparkline({ data, height = 26, variant = "card", className = "" }: Props) {
  const max = Math.max(1, ...data);
  return (
    <div
      className={`flex items-end ${variant === "panel" ? "gap-[2px]" : "gap-[1.5px]"} ${className}`}
      style={{ height }}
      role="img"
      aria-label="Distribution"
    >
      {data.map((v, i) => (
        <div
          key={i}
          className={`flex-1 min-h-[2px] ${variant === "panel" ? "spark-panel" : "spark-card"}`}
          style={{ height: `${(v / max) * 100}%` }}
        />
      ))}
    </div>
  );
}
