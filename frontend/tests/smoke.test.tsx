/* Phase 2 smoke test (acceptance gate): the shell renders, the wordmark
 * is visible, and the mode toggle is wired to the zustand store. */

import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";
import { useApp } from "../src/state/store";

const resetStore = () => {
  useApp.setState({
    mode: "guided",
    step: "import",
    dataset: null,
    columns: [],
    selectedVar: null,
    summarizeCache: {},
    commandHistory: [],
  });
};

describe("App shell smoke", () => {
  it("renders the wordmark and mode toggle", () => {
    resetStore();
    render(<App />);

    // Wordmark — italic-serif "S" then sans "olarSTATA"
    expect(screen.getByText("olarSTATA")).toBeInTheDocument();
    expect(screen.getByText("S")).toBeInTheDocument();

    // Mode toggle accessible name
    const toggle = screen.getByRole("tablist", { name: /mode toggle/i });
    expect(toggle).toBeInTheDocument();
    expect(within(toggle).getByRole("tab", { name: "Guided" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(toggle).getByRole("tab", { name: "Pro" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("flips to Pro mode when the Pro tab is clicked and back again", async () => {
    resetStore();
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("tab", { name: "Pro" }));
    expect(useApp.getState().mode).toBe("pro");

    // Pro mode shows the editor placeholder region
    expect(screen.getByRole("region", { name: /command editor placeholder/i })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Guided" }));
    expect(useApp.getState().mode).toBe("guided");
  });

  it("starts on the Import step in Guided mode", () => {
    resetStore();
    render(<App />);
    expect(screen.getByText(/Bring in your/)).toBeInTheDocument();
    // Wizard rail labels
    expect(screen.getByText("Import")).toBeInTheDocument();
    expect(screen.getByText("Inspect")).toBeInTheDocument();
    expect(screen.getByText("Analyze")).toBeInTheDocument();
  });
});
