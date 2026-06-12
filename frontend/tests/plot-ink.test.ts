/* Dark-theme ink mapping for figure overlays — the backend draws
 * bracket lines, star annotations, and compact letters in light-mode
 * ink (rgba(0,0,0,…)); the Plot wrapper must remap those to warm
 * cream on the dark theme or they are invisible against the dark
 * surface. Other colors (the warm CAVEAT note) must pass through. */

import { describe, expect, it } from "vitest";
import { themeOverlayInk } from "../src/components/Plot";

const LETTER_FONT = "rgba(0,0,0,0.75)";
const BRACKET_LINE = "rgba(0,0,0,0.55)";
const CAVEAT = "#D89B7E";

const layout = {
  annotations: [
    { text: "a", font: { family: "Geist Mono, monospace", size: 13, color: LETTER_FONT } },
    { text: "caveat…", font: { family: "Geist, sans-serif", size: 11, color: CAVEAT } },
  ],
  shapes: [
    { type: "line", line: { color: BRACKET_LINE, width: 1 } },
  ],
};

describe("themeOverlayInk", () => {
  it("remaps letter/star ink and bracket lines for the dark theme", () => {
    const out = themeOverlayInk(layout, false) as {
      annotations: { font: { color: string; size: number } }[];
      shapes: { line: { color: string } }[];
    };
    expect(out.annotations[0].font.color).toBe("rgba(236,231,218,0.85)");
    expect(out.annotations[0].font.size).toBe(13); // rest of the font untouched
    expect(out.shapes[0].line.color).toBe("rgba(236,231,218,0.60)");
  });

  it("leaves the warm caveat color untouched on dark", () => {
    const out = themeOverlayInk(layout, false) as {
      annotations: { font: { color: string } }[];
    };
    expect(out.annotations[1].font.color).toBe(CAVEAT);
  });

  it("passes everything through unchanged on the light theme", () => {
    expect(themeOverlayInk(layout, true)).toEqual({});
  });

  it("is a no-op for figures without overlays", () => {
    expect(themeOverlayInk({}, false)).toEqual({});
  });
});
