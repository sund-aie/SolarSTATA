/* Interpretation block — the v3.3 plain-English rendering of the
 * engine's interpretation field. Sentences present → a styled
 * "Interpretation" section beneath the card body. Empty or absent →
 * nothing at all (no orphaned header). */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { InterpretationBlock, ResultsCard } from "../src/components/ResultsCard";

const SENTENCES = [
  "Mean plaque_index differed significantly across the 5 education_level groups (F(4, 401) = 11.84, p < .001).",
  "Pairwise comparisons were adjusted with the Bonferroni correction.",
];

describe("InterpretationBlock", () => {
  it("renders every sentence under an Interpretation heading", () => {
    render(<InterpretationBlock sentences={SENTENCES} />);
    expect(screen.getByText("Interpretation")).toBeInTheDocument();
    for (const s of SENTENCES) {
      expect(screen.getByText(s)).toBeInTheDocument();
    }
  });

  it("renders nothing for an empty sentence list", () => {
    const { container } = render(<InterpretationBlock sentences={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Interpretation")).not.toBeInTheDocument();
  });

  it("renders nothing when the field is absent", () => {
    const { container } = render(<InterpretationBlock sentences={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("appears inside a ResultsCard beneath the existing body", () => {
    render(
      <ResultsCard title="One-way ANOVA" interpretation={SENTENCES}>
        <div>table body</div>
      </ResultsCard>,
    );
    const block = screen.getByTestId("interpretation");
    expect(block).toHaveTextContent("Interpretation");
    // Beneath the body: the card body precedes the block in DOM order.
    const body = screen.getByText("table body");
    expect(body.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
  });

  it("ResultsCard without interpretation renders no block", () => {
    render(
      <ResultsCard title="Predict">
        <div>body only</div>
      </ResultsCard>,
    );
    expect(screen.queryByTestId("interpretation")).not.toBeInTheDocument();
  });
});
