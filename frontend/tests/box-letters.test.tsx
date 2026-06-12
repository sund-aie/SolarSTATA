/* Box form posthoc letters — the box chart shows the compact-letter
 * row when (and only when) a matching oneway posthoc exists for its
 * variable/group pair, and never offers brackets (box is
 * letters-only). Drives the same lastOnewayPosthoc selector as the
 * bar form. */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SingleYForm } from "../src/steps/VisualizeStep";
import { useApp } from "../src/state/store";
import type { AnalyzeRecord, ColumnInfo, OnewayResponse } from "../src/lib/types";

function col(name: string, kind: ColumnInfo["kind"], dtype = "float64"): ColumnInfo {
  return {
    name,
    dtype,
    stata_type: dtype,
    label: "",
    kind,
    n: 100,
    n_missing: 0,
    missing_pct: 0,
    n_unique: kind === "numeric" ? 80 : 3,
    value_labels: {},
    sparkline: [],
    sparkline_kind: kind === "numeric" ? "numeric" : "categorical",
  };
}

function onewayRecord(depvar: string, groupvar: string): AnalyzeRecord {
  const result: OnewayResponse["result"] = {
    kind: "oneway",
    depvar,
    groupvar,
    n: 30,
    k: 3,
    F: 10.0,
    p: 0.001,
    group_stats: [],
    anova_table: { Source: [], SS: [], df: [], MS: [], F: [], Prob_F: [] },
    bartlett: { chi2: 1, df: 2, p: 0.5 },
    posthoc: "bonferroni",
    posthoc_block: {
      method: "bonferroni",
      n_pairs: 3,
      comparisons: [
        { a: "A", b: "B", mean_diff: 1, se: 0.5, t: 2, p_raw: 0.01, p_adj: 0.03 },
      ],
      matrix: {},
    },
  };
  return {
    command: `oneway ${depvar} ${groupvar}, bonferroni`,
    kind: "oneway",
    payload: { command: "oneway", result, text: "", r_set: {}, e_set: null } as OnewayResponse,
    text: "",
    timestamp: 100,
  };
}

const NUMERICS = [col("plaque_index", "numeric")];
const CATEGORICALS = [col("education_level", "categorical", "object")];

afterEach(() => {
  cleanup();
  useApp.setState({ analyzeRecords: [] });
});

describe("box form compact letters", () => {
  it("shows the letters row when a matching oneway posthoc exists", () => {
    useApp.setState({
      analyzeRecords: [onewayRecord("plaque_index", "education_level")],
    });
    render(
      <SingleYForm chart="box" numerics={NUMERICS} categoricals={CATEGORICALS}
                   onRendered={() => {}} />,
    );
    expect(screen.getByText("Compact letters")).toBeInTheDocument();
    expect(screen.getByText(/Show bonferroni letters/)).toBeInTheDocument();
    // Box is letters-only — the brackets row must never appear.
    expect(screen.queryByText("Significance brackets")).not.toBeInTheDocument();
  });

  it("hides the letters row when no posthoc matches the variable/group pair", () => {
    useApp.setState({
      analyzeRecords: [onewayRecord("other_var", "education_level")],
    });
    render(
      <SingleYForm chart="box" numerics={NUMERICS} categoricals={CATEGORICALS}
                   onRendered={() => {}} />,
    );
    expect(screen.queryByText("Compact letters")).not.toBeInTheDocument();
  });

  it("hides the letters row when the analyze history is empty", () => {
    render(
      <SingleYForm chart="box" numerics={NUMERICS} categoricals={CATEGORICALS}
                   onRendered={() => {}} />,
    );
    expect(screen.queryByText("Compact letters")).not.toBeInTheDocument();
  });

  it("bar form still offers both brackets and letters", () => {
    useApp.setState({
      analyzeRecords: [onewayRecord("plaque_index", "education_level")],
    });
    render(
      <SingleYForm chart="bar" numerics={NUMERICS} categoricals={CATEGORICALS}
                   onRendered={() => {}} />,
    );
    expect(screen.getByText("Significance brackets")).toBeInTheDocument();
    expect(screen.getByText("Compact letters")).toBeInTheDocument();
  });
});
