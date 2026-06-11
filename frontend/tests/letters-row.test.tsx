/* LettersRow — the compact-letter toggle shown next to BracketsRow on
 * bar forms (and alone on the box form). Pins the self-explaining
 * copy: the method name appears, and the meaning of a shared letter
 * is stated as NOT significantly different — never "equal". */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { LettersRow } from "../src/steps/VisualizeStep";

describe("LettersRow", () => {
  it("names the correction method and the shared-letter meaning", () => {
    render(
      <LettersRow method="bonferroni" checked={false} onChange={() => {}} disabled={false} />,
    );
    expect(screen.getByText(/Show bonferroni letters/)).toBeInTheDocument();
    expect(screen.getByText(/significantly different/)).toBeInTheDocument();
    // The label must read "not significantly different" — letters group
    // the NSD pairs; phrasing it as equality would overclaim.
    expect(screen.getByText("not")).toBeInTheDocument();
  });

  it("invokes onChange with the checkbox state", () => {
    const onChange = vi.fn();
    render(
      <LettersRow method="scheffe" checked={false} onChange={onChange} disabled={false} />,
    );
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("renders unchecked and disabled with the explanation when grouping disables it", () => {
    render(
      <LettersRow
        method="bonferroni"
        checked={true}
        onChange={() => {}}
        disabled={true}
        disabledReason="Letters apply to single-group comparisons."
      />,
    );
    const checkbox = screen.getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);
    expect(checkbox.checked).toBe(false); // checked && !disabled
    expect(
      screen.getByText("Letters apply to single-group comparisons."),
    ).toBeInTheDocument();
  });

  it("stays checked when enabled", () => {
    render(
      <LettersRow method="sidak" checked={true} onChange={() => {}} disabled={false} />,
    );
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
  });
});
