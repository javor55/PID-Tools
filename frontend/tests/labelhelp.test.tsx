// LabelHelp: „?“ jako tlačítko s textem v aria-label i title, bublina po kliknutí, zavření Esc.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { LabelHelp, Seg } from "../src/components/Ui";

const wrap = (ui: ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe("LabelHelp", () => {
  it("is an accessible button; click opens the bubble, Esc closes it", () => {
    wrap(<LabelHelp text="Nápověda k poli" />);
    const b = screen.getByRole("button", { name: "Nápověda k poli" });
    expect(b.getAttribute("title")).toBe("Nápověda k poli");
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.click(b);
    expect(screen.getByRole("tooltip").textContent).toBe("Nápověda k poli");
    fireEvent.keyDown(b, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.click(b);
    fireEvent.blur(b);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("Seg with help shows the question mark next to the group", () => {
    wrap(<Seg value="a" options={["a", "b"] as const} onChange={() => {}} label="Volba" help="Vysvětlení volby" />);
    expect(screen.getByRole("group", { name: "Volba" }).getAttribute("title")).toBe("Vysvětlení volby");
    expect(screen.getByRole("button", { name: "Vysvětlení volby" })).toBeTruthy();
  });
});
