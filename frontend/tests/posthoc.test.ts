/* lastOnewayPosthoc — finds the most-recent matching oneway with
 * posthoc enabled, returns null when nothing fits. Drives the bar
 * form's significance-bracket toggle. */

import { describe, expect, it } from "vitest";
import { lastOnewayPosthoc } from "../src/lib/posthoc";
import type { AnalyzeRecord, OnewayResponse } from "../src/lib/types";

function onewayRecord(opts: {
  depvar: string;
  groupvar: string;
  posthoc?: "none" | "bonferroni" | "scheffe" | "sidak";
  timestamp?: number;
  method?: string;
}): AnalyzeRecord {
  const result: OnewayResponse["result"] = {
    kind: "oneway",
    depvar: opts.depvar,
    groupvar: opts.groupvar,
    n: 30,
    k: 3,
    F: 10.0,
    p: 0.001,
    group_stats: [],
    anova_table: { Source: [], SS: [], df: [], MS: [], F: [], Prob_F: [] },
    bartlett: { chi2: 1, df: 2, p: 0.5 },
    posthoc: opts.posthoc ?? "bonferroni",
    posthoc_block: opts.posthoc === "none" ? null : {
      method: opts.method ?? "bonferroni",
      n_pairs: 3,
      comparisons: [
        { a: "A", b: "B", mean_diff: 1, se: 0.5, t: 2, p_raw: 0.01, p_adj: 0.03 },
      ],
      matrix: {},
    },
  };
  return {
    command: `oneway ${opts.depvar} ${opts.groupvar}`,
    kind: "oneway",
    payload: { command: "oneway", result, text: "", r_set: {}, e_set: null } as OnewayResponse,
    text: "",
    timestamp: opts.timestamp ?? 100,
  };
}

describe("lastOnewayPosthoc", () => {
  it("returns the posthoc block when a matching oneway with posthoc exists", () => {
    const records = [onewayRecord({ depvar: "vhn", groupvar: "g" })];
    const block = lastOnewayPosthoc(records, "vhn", "g");
    expect(block).not.toBeNull();
    expect(block!.method).toBe("bonferroni");
    expect(block!.n_pairs).toBe(3);
  });

  it("returns null when no oneway record matches the depvar/groupvar pair", () => {
    const records = [onewayRecord({ depvar: "other", groupvar: "g" })];
    expect(lastOnewayPosthoc(records, "vhn", "g")).toBeNull();
  });

  it("returns null when the matching oneway was run without a posthoc correction", () => {
    const records = [onewayRecord({ depvar: "vhn", groupvar: "g", posthoc: "none" })];
    expect(lastOnewayPosthoc(records, "vhn", "g")).toBeNull();
  });

  it("returns the most recent matching record when multiple exist", () => {
    const records = [
      onewayRecord({ depvar: "vhn", groupvar: "g", timestamp: 100, method: "bonferroni" }),
      onewayRecord({ depvar: "vhn", groupvar: "g", timestamp: 200, method: "scheffe" }),
      onewayRecord({ depvar: "other", groupvar: "g", timestamp: 300 }),
    ];
    const block = lastOnewayPosthoc(records, "vhn", "g");
    expect(block!.method).toBe("scheffe");
  });

  it("returns null when the analyze history is empty", () => {
    expect(lastOnewayPosthoc([], "vhn", "g")).toBeNull();
  });

  it("ignores non-oneway records", () => {
    const records: AnalyzeRecord[] = [
      { command: "regress vhn g", kind: "regress", payload: {}, text: "", timestamp: 100 },
      { command: "tabstat vhn", kind: "tabstat", payload: {}, text: "", timestamp: 200 },
    ];
    expect(lastOnewayPosthoc(records, "vhn", "g")).toBeNull();
  });
});
