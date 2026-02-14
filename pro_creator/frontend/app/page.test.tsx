import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage tabs", () => {
  it("renders all engine tabs", () => {
    render(<HomePage />);
    fireEvent.click(screen.getByRole("button", { name: /^Engines$/i }));
    const enginesSection = screen.getByText(/Engine actions/i).closest("section");
    expect(enginesSection).toBeTruthy();

    const engines = within(enginesSection as HTMLElement);
    ["Script", "Voice", "Image", "Video", "Media", "Lab"].forEach((label) => {
      expect(engines.getByRole("button", { name: label })).toBeInTheDocument();
    });
  });

  it("renders all automation tabs", () => {
    render(<HomePage />);
    fireEvent.click(screen.getByRole("button", { name: /^Automation$/i }));
    const automationSection = screen
      .getByText(/Automation studio/i)
      .closest("section");
    expect(automationSection).toBeTruthy();

    const automation = within(automationSection as HTMLElement);
    ["Captions", "Editor", "AI Lab", "Exports"].forEach((label) => {
      expect(automation.getByRole("button", { name: label })).toBeInTheDocument();
    });
  });
});
