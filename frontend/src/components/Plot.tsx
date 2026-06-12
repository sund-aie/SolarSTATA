/* Plotly figure renderer wired to the SolarSTATA theme.
 *
 * Backend produces minimal-styled figures (gold series, transparent
 * paper, dark axis grid). We overlay theme-specific layout colours
 * here so the same figure looks right in either light or dark mode.
 *
 * react-plotly.js is loaded lazily so the ~3 MB plotly chunk only
 * enters the bundle once a user actually opens the Visualize step or
 * runs a graph command in Pro mode.
 */

import { Suspense, lazy, useMemo } from "react";
import { useTheme } from "../state/theme";

const ReactPlot = lazy(() => import("react-plotly.js"));

export interface PlotlyFigure {
  data: unknown[];
  layout: Record<string, unknown>;
}

/* Backend figures draw their overlay ink — significance-bracket lines,
 * star annotations, compact-letter labels (engine/graphs.py
 * _emit_brackets/_emit_letters) — in light-mode ink. Theming is this
 * wrapper's job, so the known ink colors are remapped to warm cream
 * for dark mode here. Any other annotation/shape color (e.g. the warm
 * CAVEAT tone under a letters chart) passes through untouched.
 * Exported for tests. */
const DARK_INK: Record<string, string> = {
  "rgba(0,0,0,0.75)": "rgba(236,231,218,0.85)",  // letter/star annotation font
  "rgba(0,0,0,0.55)": "rgba(236,231,218,0.60)",  // bracket line shapes
};

export function themeOverlayInk(
  layout: Record<string, unknown>,
  isLight: boolean,
): Record<string, unknown> {
  if (isLight) return {};
  const out: Record<string, unknown> = {};
  const annotations = layout.annotations as
    | { font?: { color?: string } }[]
    | undefined;
  if (Array.isArray(annotations)) {
    out.annotations = annotations.map((a) => {
      const mapped = a?.font?.color ? DARK_INK[a.font.color] : undefined;
      return mapped ? { ...a, font: { ...a.font, color: mapped } } : a;
    });
  }
  const shapes = layout.shapes as { line?: { color?: string } }[] | undefined;
  if (Array.isArray(shapes)) {
    out.shapes = shapes.map((s) => {
      const mapped = s?.line?.color ? DARK_INK[s.line.color] : undefined;
      return mapped ? { ...s, line: { ...s.line, color: mapped } } : s;
    });
  }
  return out;
}

interface Props {
  figure: PlotlyFigure;
  height?: number;
  className?: string;
}

export function Plot({ figure, height = 360, className = "" }: Props) {
  const theme = useTheme((s) => s.theme);

  const overlay = useMemo(() => {
    const isLight = theme === "light";
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {
        ...(figure.layout.font as object),
        color: isLight ? "#1F1B14" : "#ECE7DA",
        family: "Geist, sans-serif",
      },
      xaxis: {
        ...(figure.layout.xaxis as object),
        gridcolor: isLight ? "#D6CFC0" : "#3A3529",
        linecolor: isLight ? "#6B6450" : "#5C5648",
        zerolinecolor: isLight ? "#D6CFC0" : "#3A3529",
        tickfont: { color: isLight ? "#4A4537" : "#968E7D" },
      },
      yaxis: {
        ...(figure.layout.yaxis as object),
        gridcolor: isLight ? "#D6CFC0" : "#3A3529",
        linecolor: isLight ? "#6B6450" : "#5C5648",
        zerolinecolor: isLight ? "#D6CFC0" : "#3A3529",
        tickfont: { color: isLight ? "#4A4537" : "#968E7D" },
      },
      legend: { bgcolor: "rgba(0,0,0,0)", font: { color: isLight ? "#1F1B14" : "#ECE7DA" } },
      ...themeOverlayInk(figure.layout, isLight),
    };
  }, [theme, figure.layout]);

  const mergedLayout = useMemo(
    () => ({
      ...figure.layout,
      ...overlay,
      autosize: true,
    }),
    [figure.layout, overlay],
  );

  return (
    <div className={`w-full ${className}`}>
      <Suspense fallback={<div style={{ height }} className="text-text-faint text-[12px] flex items-center justify-center font-mono">loading chart…</div>}>
        <ReactPlot
          data={figure.data as Plotly.Data[]}
          layout={mergedLayout as Plotly.Layout}
          style={{ width: "100%", height }}
          useResizeHandler
          config={{ displayModeBar: false, responsive: true }}
        />
      </Suspense>
    </div>
  );
}
