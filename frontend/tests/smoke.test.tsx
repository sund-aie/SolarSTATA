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

    // Wordmark — sun mark + "solar" sans + "stata" italic gold
    expect(screen.getByRole("img", { name: /SolarSTATA/i })).toBeInTheDocument();
    expect(screen.getByText("stata")).toBeInTheDocument();
    expect(screen.getByText(/^solar$/)).toBeInTheDocument();

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

    const proTab = screen.getByRole("tab", { name: "Pro" });
    await user.click(proTab);
    expect(useApp.getState().mode).toBe("pro");
    expect(proTab).toHaveAttribute("aria-selected", "true");

    // Suspense fallback renders while Monaco lazy-loads in real browsers; in
    // jsdom the chunk never resolves, but the mode state has already flipped.

    const guidedTab = screen.getByRole("tab", { name: "Guided" });
    await user.click(guidedTab);
    expect(useApp.getState().mode).toBe("guided");
    expect(guidedTab).toHaveAttribute("aria-selected", "true");
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
