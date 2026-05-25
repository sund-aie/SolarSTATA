/* HeaderRowPicker — preflight wiring + status-strip wording.
 *
 * The canonical case is header on row 5 (the TIDY LONG FORMAT
 * pattern). The strip must read exactly:
 *
 *   "Header detected on row 5 — rows 1 to 4 look like notes, we
 *    will skip them."
 *
 * and the confirm-button must update to "Load with row 5 as
 * header" — without the user clicking anything.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HeaderRowPicker } from "../src/components/HeaderRowPicker";
import type { PreflightResponse, StagedSheet } from "../src/lib/types";

vi.mock("../src/lib/api", () => ({
  api: {
    preflight: vi.fn(),
  },
}));

import { api } from "../src/lib/api";

const tidyLongSheet: StagedSheet = {
  name: "Tidy",
  n_rows: 8,
  n_cols: 3,
  preview_rows: [
    ["TIDY LONG FORMAT", "", ""],
    ["Anonymized clinical extract", "", ""],
    ["", "", ""],
    ["", "", ""],
    ["patient_id", "age", "sex"],
    ["1001", "23", "F"],
    ["1002", "45", "M"],
    ["1003", "31", "F"],
  ],
};

const happySheet: StagedSheet = {
  name: "Data",
  n_rows: 4,
  n_cols: 3,
  preview_rows: [
    ["age", "sex", "weight"],
    ["23", "F", "70.5"],
    ["45", "M", "82.0"],
    ["31", "F", "65.0"],
  ],
};

function preflightFor(detected: number, opts: Partial<PreflightResponse> = {}): PreflightResponse {
  return {
    sheet: "Tidy",
    detected_header_row: detected,
    notes_rows: Array.from({ length: detected - 1 }, (_, i) => i + 1),
    header_cells: ["patient_id", "age", "sex"],
    column_kinds: { numeric: 1, categorical: 1, identifier: 1, string: 0 },
    cell_issues: { merged_cells: 0, hidden_rows: 0, hidden_cols: 0 },
    n_rows_after_header: 380,
    ...opts,
  };
}

describe("HeaderRowPicker — preflight wiring", () => {
  beforeEach(() => {
    vi.mocked(api.preflight).mockReset();
  });

  it("canonical: header on row 5 — strip uses the exact 'rows 1 to 4 look like notes' wording", async () => {
    vi.mocked(api.preflight).mockResolvedValue(preflightFor(5));

    render(
      <HeaderRowPicker
        fileId="abc123"
        filename="research.xlsx"
        sheet={tidyLongSheet}
        onConfirm={() => undefined}
        onBack={() => undefined}
      />,
    );

    // Exact phrasing the user signed off on
    await waitFor(() =>
      expect(
        screen.getByText(
          /Header detected on row 5 — rows 1 to 4 look like notes, we will skip them\./,
        ),
      ).toBeInTheDocument(),
    );

    // Auto-pick flowed into the confirm button label without any clicks
    expect(
      screen.getByRole("button", { name: /Load with row 5 as header/ }),
    ).toBeInTheDocument();

    // Backend received the right args
    expect(api.preflight).toHaveBeenCalledWith({ file_id: "abc123", sheet: "Tidy" });
  });

  it("happy path: header on row 1 reads 'looks clean', confirm stays at row 1", async () => {
    vi.mocked(api.preflight).mockResolvedValue({
      ...preflightFor(1),
      sheet: "Data",
      notes_rows: [],
      header_cells: ["age", "sex", "weight"],
      column_kinds: { numeric: 2, categorical: 1, identifier: 0, string: 0 },
    });

    render(
      <HeaderRowPicker
        fileId="abc"
        filename="study.xlsx"
        sheet={happySheet}
        onConfirm={() => undefined}
        onBack={() => undefined}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByText(/Ready to load — header on row 1, looks clean\./),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByRole("button", { name: /Load with row 1 as header/ }),
    ).toBeInTheDocument();
  });

  it("user clicks override the auto-pick even after preflight returns", async () => {
    // Make preflight a slow-resolving promise so we can race the user click in front of it
    let resolvePreflight!: (r: PreflightResponse) => void;
    vi.mocked(api.preflight).mockReturnValue(
      new Promise<PreflightResponse>((resolve) => { resolvePreflight = resolve; }),
    );

    const user = userEvent.setup();
    render(
      <HeaderRowPicker
        fileId="abc123"
        filename="research.xlsx"
        sheet={tidyLongSheet}
        onConfirm={() => undefined}
        onBack={() => undefined}
      />,
    );

    // User clicks the "1002" data row BEFORE preflight resolves. That
    // value sits on row 7 of the preview (rows 1-2 are notes, 3-4 blank,
    // 5 is the header, 6 = 1001, 7 = 1002).
    await user.click(screen.getByText("1002"));
    expect(
      screen.getByRole("button", { name: /Load with row 7 as header/ }),
    ).toBeInTheDocument();

    // Preflight now lands with detected=5 — must NOT override the user's choice
    resolvePreflight(preflightFor(5));
    await waitFor(() =>
      expect(
        screen.getByText(/Header detected on row 5/),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /Load with row 7 as header/ }),
    ).toBeInTheDocument();
  });

  it("merged-cell chip renders when cell_issues.merged_cells > 0", async () => {
    vi.mocked(api.preflight).mockResolvedValue(
      preflightFor(5, { cell_issues: { merged_cells: 2, hidden_rows: 0, hidden_cols: 0 } }),
    );

    render(
      <HeaderRowPicker
        fileId="abc"
        filename="research.xlsx"
        sheet={tidyLongSheet}
        onConfirm={() => undefined}
        onBack={() => undefined}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByText(/2 merged cells — only the top-left value is kept/),
      ).toBeInTheDocument(),
    );
  });
});
