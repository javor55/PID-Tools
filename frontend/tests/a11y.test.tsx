// Přístupnost: rowPick (výběr řádku klávesnicí) a popisek SVG grafů.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { LineChart } from "../src/components/LineChart";
import { rowPick } from "../src/lib/a11y";

afterEach(cleanup);

function Tbl({ onPick, selected }: { onPick: () => void; selected?: boolean }) {
  return (<table><tbody><tr data-testid="r" className="pick" {...rowPick(onPick, selected)}>
    <td><button data-testid="b">x</button></td></tr></tbody></table>);
}

describe("rowPick", () => {
  it("Enter a mezerník vyberou řádek, jiná klávesa ne", () => {
    const f = vi.fn();
    render(<Tbl onPick={f} selected />);
    const r = screen.getByTestId("r");
    expect(r.getAttribute("tabindex")).toBe("0");
    expect(r.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(r, { key: "Enter" });
    fireEvent.keyDown(r, { key: " " });
    expect(f).toHaveBeenCalledTimes(2);
    fireEvent.keyDown(r, { key: "a" });
    fireEvent.keyDown(r, { key: "Tab" });
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("klávesa z vnořeného tlačítka řádek nevybere; klik ano", () => {
    const f = vi.fn();
    render(<Tbl onPick={f} />);
    fireEvent.keyDown(screen.getByTestId("b"), { key: "Enter" });
    expect(f).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("r"));
    expect(f).toHaveBeenCalledTimes(1);
  });
});

describe("LineChart", () => {
  beforeAll(() => {      // jsdom nemá ResizeObserver
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
  });
  const s = [{ name: "Odezva", x: [0, 1, 2], y: [0, 1, 2], color: "#000" }, { name: "Žádaná", x: [0, 2], y: [1, 1], color: "#111" }];
  it("má role img a aria-label z názvů řad a os", () => {
    const { container } = render(<LineChart series={s} yLabel="PV" xLabel="t [s]" />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("role")).toBe("img");
    expect(svg?.getAttribute("aria-label")).toBe("Odezva, Žádaná, PV, t [s]");
  });
  it("title má přednost", () => {
    const { container } = render(<LineChart series={s} title="Moje" />);
    expect(container.querySelector("svg")?.getAttribute("aria-label")).toBe("Moje");
  });
});
