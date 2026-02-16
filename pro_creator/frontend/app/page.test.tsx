import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

async function loadHomePage() {
  // The page reads NEXT_PUBLIC_EXPERIMENTAL_FEATURES at module load time.
  vi.resetModules();
  return (await import("./page")).default;
}

describe("HomePage tabs", () => {
  it("renders core engine tabs by default (no experimental placeholders)", async () => {
    delete process.env.NEXT_PUBLIC_EXPERIMENTAL_FEATURES;
    const HomePage = await loadHomePage();

    render(<HomePage />);
    fireEvent.click(screen.getByRole("button", { name: /^Engines$/i }));
    const enginesSection = screen.getByText(/Engine actions/i).closest("section");
    expect(enginesSection).toBeTruthy();

    const engines = within(enginesSection as HTMLElement);
    ["Script", "Voice", "Image", "Video"].forEach((label) => {
      expect(engines.getByRole("button", { name: label })).toBeInTheDocument();
    });

    // Hidden unless NEXT_PUBLIC_EXPERIMENTAL_FEATURES=true
    expect(engines.queryByRole("button", { name: "Media" })).toBeNull();
    expect(engines.queryByRole("button", { name: "Lab" })).toBeNull();
  });

  it("renders core automation tabs by default (no experimental placeholders)", async () => {
    delete process.env.NEXT_PUBLIC_EXPERIMENTAL_FEATURES;
    const HomePage = await loadHomePage();

    render(<HomePage />);
    fireEvent.click(screen.getByRole("button", { name: /^Automation$/i }));
    const automationSection = screen
      .getByText(/Automation studio/i)
      .closest("section");
    expect(automationSection).toBeTruthy();

    const automation = within(automationSection as HTMLElement);
    ["Captions", "Editor", "Exports"].forEach((label) => {
      expect(automation.getByRole("button", { name: label })).toBeInTheDocument();
    });

    expect(automation.queryByRole("button", { name: "AI Lab" })).toBeNull();
  });

  it("renders experimental tabs when NEXT_PUBLIC_EXPERIMENTAL_FEATURES=true", async () => {
    process.env.NEXT_PUBLIC_EXPERIMENTAL_FEATURES = "true";
    const HomePage = await loadHomePage();

    render(<HomePage />);

    fireEvent.click(screen.getByRole("button", { name: /^Engines$/i }));
    const enginesSection = screen.getByText(/Engine actions/i).closest("section");
    expect(enginesSection).toBeTruthy();
    const engines = within(enginesSection as HTMLElement);
    ["Media", "Lab"].forEach((label) => {
      expect(engines.getByRole("button", { name: label })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /^Automation$/i }));
    const automationSection = screen
      .getByText(/Automation studio/i)
      .closest("section");
    expect(automationSection).toBeTruthy();
    const automation = within(automationSection as HTMLElement);
    expect(automation.getByRole("button", { name: "AI Lab" })).toBeInTheDocument();
  });
});
