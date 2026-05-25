/* FormatGuide — renders all rules, toggles collapsed, persists to localStorage. */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormatGuide } from "../src/components/FormatGuide";

const STORAGE_KEY = "solarstata.format_guide_collapsed";

describe("FormatGuide", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("renders the headline and all five rule labels by default", () => {
    render(<FormatGuide />);

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(/Prepare your sheet/i);

    // Five rule labels — exact prefixes from the component
    expect(screen.getByText(/Row 1 holds your column names/i)).toBeInTheDocument();
    expect(screen.getByText(/One row per observation/i)).toBeInTheDocument();
    expect(screen.getByText(/No merged cells/i)).toBeInTheDocument();
    expect(screen.getByText(/No title or blank rows above the headers/i)).toBeInTheDocument();
    expect(screen.getByText(/Numbers as numbers/i)).toBeInTheDocument();

    // Good and bad tile labels
    expect(screen.getByText("good")).toBeInTheDocument();
    expect(screen.getByText("bad")).toBeInTheDocument();
  });

  it("collapses on click and writes the localStorage flag", async () => {
    const user = userEvent.setup();
    render(<FormatGuide />);

    const toggle = screen.getByRole("button", { expanded: true });
    expect(toggle).toBeInTheDocument();

    await user.click(toggle);

    expect(screen.getByRole("button", { expanded: false })).toBeInTheDocument();
    expect(screen.queryByText(/Row 1 holds your column names/i)).not.toBeInTheDocument();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("1");
  });

  it("starts collapsed when the persisted flag is set", () => {
    window.localStorage.setItem(STORAGE_KEY, "1");
    render(<FormatGuide />);

    expect(screen.getByRole("button", { expanded: false })).toBeInTheDocument();
    expect(screen.queryByText(/Row 1 holds your column names/i)).not.toBeInTheDocument();
  });

  it("reopens from the collapsed state and clears the flag", async () => {
    window.localStorage.setItem(STORAGE_KEY, "1");
    const user = userEvent.setup();
    render(<FormatGuide />);

    const toggle = screen.getByRole("button", { expanded: false });
    await user.click(toggle);

    expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
    expect(screen.getByText(/Row 1 holds your column names/i)).toBeInTheDocument();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("0");
  });
});
