/* Counts chart — command-preview wording (v3.3 Part B).
 *
 * The preview reads like Stata's `graph bar (count) y` / `graph bar
 * (percent) y, over(x)`. The `normalize(...)` suffix is omitted only
 * when the chosen scope matches Stata's default for the current
 * state. These six cases pin the exact strings so the wording can't
 * drift quietly later. */

import { describe, expect, it } from "vitest";
import { countsCommand } from "../src/steps/VisualizeStep";

describe("countsCommand", () => {
  it("count mode, ungrouped — no options, no suffix", () => {
    expect(
      countsCommand({ x: "q1_correct", group: null, mode: "count", normalize: "total" }),
    ).toBe("graph bar (count) q1_correct");
  });

  it("count mode, grouped — over(...) but no normalize suffix", () => {
    expect(
      countsCommand({ x: "q1_correct", group: "treatment", mode: "count", normalize: "total" }),
    ).toBe("graph bar (count) q1_correct, over(treatment)");
  });

  it("percent + grouped + within_group — matches Stata default, no suffix", () => {
    expect(
      countsCommand({ x: "q1_correct", group: "treatment", mode: "percent", normalize: "within_group" }),
    ).toBe("graph bar (percent) q1_correct, over(treatment)");
  });

  it("percent + grouped + total — diverges from Stata default, suffix appears", () => {
    expect(
      countsCommand({ x: "q1_correct", group: "treatment", mode: "percent", normalize: "total" }),
    ).toBe("graph bar (percent) q1_correct, over(treatment) normalize(total)");
  });

  it("percent + grouped + within_x — diverges from Stata default, suffix appears", () => {
    expect(
      countsCommand({ x: "q1_correct", group: "treatment", mode: "percent", normalize: "within_x" }),
    ).toBe("graph bar (percent) q1_correct, over(treatment) normalize(within_x)");
  });

  it("percent + ungrouped — all normalize scopes collapse to total, no suffix", () => {
    for (const n of ["total", "within_group", "within_x"] as const) {
      expect(
        countsCommand({ x: "q1_correct", group: null, mode: "percent", normalize: n }),
      ).toBe("graph bar (percent) q1_correct");
    }
  });
});
