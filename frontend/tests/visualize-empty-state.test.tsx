/* Visualize empty-state — when the dataset has no numeric-kind
 * columns, histogram/box/bar must render an explanatory message
 * naming the kinds that ARE present, not an empty dropdown +
 * dead Run button. */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { NeedsContinuousEmptyState } from "../src/steps/VisualizeStep";
import type { ColumnInfo } from "../src/lib/types";

const HISTOGRAM_DEF = {
  id: "histogram" as const,
  label: "Histogram",
  icon: "▮▮▆▃▁",
  what: "",
  how: "",
  example: null,
};

function col(name: string, kind: ColumnInfo["kind"], dtype = "int64"): ColumnInfo {
  return {
    name,
    dtype,
    stata_type: dtype,
    label: "",
    kind,
    n: 100,
    n_missing: 0,
    missing_pct: 0,
    n_unique: 2,
    value_labels: {},
    sparkline: [],
    sparkline_kind: kind === "numeric" ? "numeric" : "categorical",
  };
}

describe("NeedsContinuousEmptyState", () => {
  it("names binary and categorical when both kinds are present", () => {
    const columns: ColumnInfo[] = [
      col("q1_correct", "binary"),
      col("q2_correct", "binary"),
      col("q3_correct", "binary"),
      col("treatment_arm", "categorical", "string"),
      col("clinic_site", "categorical", "string"),
    ];
    render(<NeedsContinuousEmptyState columns={columns} chart={HISTOGRAM_DEF} />);

    expect(
      screen.getByRole("heading", { name: /no .*continuous.* variables/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/3 binary and 2 categorical, no measurements/),
    ).toBeInTheDocument();
    // The Counts pointer is the strong tag inside the pointer sentence —
    // the eyebrow above ("Counts and proportions instead") also matches
    // /Counts/, so target the strong tag specifically.
    expect(
      screen.getByText("Counts", { selector: "strong" }),
    ).toBeInTheDocument();
  });

  it("names the single kind when only one is present", () => {
    const columns: ColumnInfo[] = [
      col("pass1", "binary"),
      col("pass2", "binary"),
      col("pass3", "binary"),
      col("pass4", "binary"),
    ];
    render(<NeedsContinuousEmptyState columns={columns} chart={HISTOGRAM_DEF} />);
    expect(screen.getByText(/4 binary, no measurements/)).toBeInTheDocument();
  });

  it("uses Oxford-comma form when three or more kinds are present", () => {
    const columns: ColumnInfo[] = [
      col("flag", "binary"),
      col("arm", "categorical"),
      col("patient_id", "id"),
      col("notes", "string", "object"),
    ];
    render(<NeedsContinuousEmptyState columns={columns} chart={HISTOGRAM_DEF} />);
    expect(
      screen.getByText(/1 binary, 1 categorical, 1 id, and 1 text/),
    ).toBeInTheDocument();
  });

  it("uses the chart label inside the explanation sentence", () => {
    const boxChart = { ...HISTOGRAM_DEF, id: "box" as const, label: "Box plot" };
    render(<NeedsContinuousEmptyState columns={[col("q", "binary")]} chart={boxChart} />);
    expect(screen.getByText(/Box plot plots a measurement/)).toBeInTheDocument();
  });
});
