// FEATURE-004: nástroje grafu LineChart – čisté funkce (nejbližší vzorek, sjednocení dat, TSV / CSV) a odečet v DOM.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { LineChart, type Series } from "../src/components/LineChart";
import { nearestIndex, numText, showNum, toCsv, toTsv, unionRows, xRange } from "../src/components/chartTools";
import { queryClient } from "../src/queryClient";
import { useUi } from "../src/store";

afterEach(cleanup);

describe("nearestIndex", () => {
  const x = [0, 1, 2, 4, 8];
  it("najde nejbližší vzorek půlením", () => {
    expect(nearestIndex(x, 0)).toBe(0);
    expect(nearestIndex(x, 1.4)).toBe(1);
    expect(nearestIndex(x, 1.6)).toBe(2);
    expect(nearestIndex(x, 3.1)).toBe(3);
    expect(nearestIndex(x, 100)).toBe(4);
    expect(nearestIndex(x, -5)).toBe(0);
  });
  it("při shodě vzdáleností bere dřívější vzorek", () => {
    expect(nearestIndex([0, 2], 1)).toBe(0);
  });
  it("u logX porovnává v logaritmu (geometrický střed)", () => {
    const f = [1, 10, 100, 1000];
    expect(nearestIndex(f, 4)).toBe(0);                // lineárně: |4−1| = 3 < |10−4| = 6
    expect(nearestIndex(f, 4, true)).toBe(1);          // v logaritmu: |0,60−0| > |1−0,60|
  });
  it("zvládne velké řady (tisíce bodů) a neseřazená / NaN data", () => {
    const big = Float64Array.from({ length: 200000 }, (_, i) => i * 0.5);
    expect(nearestIndex(big, 12345.2)).toBe(24690);
    expect(nearestIndex([3, 1, 2, NaN, 10], 9)).toBe(4);       // lineární záloha
    expect(nearestIndex([NaN, NaN], 1)).toBe(-1);
    expect(nearestIndex([], 1)).toBe(-1);
  });
  it("xRange řazené i neseřazené řady", () => {
    expect(xRange([1, 2, 5])).toEqual([1, 5]);
    expect(xRange([5, NaN, 1])).toEqual([1, 5]);
    expect(xRange([])).toBeNull();
  });
});

describe("unionRows / TSV / CSV", () => {
  const a = { name: "A", x: [0, 1, 2], y: [10, 11, 12] };
  const b = { name: "B", x: [1, 2, 3], y: [0.5, NaN, 0.25] };
  it("sjednotí x přes všechny řady, chybějící hodnotu nechá prázdnou", () => {
    const t = unionRows([a, b], "t");
    expect(t.mode).toBe("union");
    expect(t.header).toEqual(["t", "A", "B"]);
    expect(t.rows).toEqual([[0, 10, null], [1, 11, 0.5], [2, 12, null], [3, null, 0.25]]);
  });
  it("nad limitem řádků použije osu první řady a nejbližší vzorek (prázdno mimo rozsah i tam, kde je nejbližší vzorek NaN)", () => {
    const t = unionRows([a, b], "t", 3);
    expect(t.mode).toBe("first");
    expect(t.rows).toEqual([[0, 10, null], [1, 11, 0.5], [2, 12, null]]);
  });
  it("TSV má desetinnou čárku podle jazyka, CSV vždy tečku a čárku jako oddělovač", () => {
    const t = unionRows([a, b], "t");
    expect(toTsv(t, ",")).toBe("t\tA\tB\n0\t10\t\n1\t11\t0,5\n2\t12\t\n3\t\t0,25");
    expect(toCsv(t)).toBe("t,A,B\r\n0,10,\r\n1,11,0.5\r\n2,12,\r\n3,,0.25\r\n");
  });
  it("CSV uvozuje názvy s čárkou a uvozovkou; TSV nahradí tabulátor", () => {
    const t = { header: ["x", 'a,"b"', "c\td"], rows: [[1, 2, 3]], mode: "union" as const };
    expect(toCsv(t).split("\r\n")[0]).toBe('x,"a,""b""",c\td');
    expect(toTsv(t, ".").split("\n")[0]).toBe("x\ta,\"b\"\tc d");
  });
  it("formát čísel", () => {
    expect(numText(0.1 + 0.2, ",")).toBe("0,3");
    expect(numText(null)).toBe("");
    expect(showNum(3.14159265, ",")).toBe("3,142");
    expect(showNum(NaN, ".")).toBe("–");
  });
});

describe("LineChart – odečet, legenda, Esc", () => {
  const W = 720, H = 220;                                   // výchozí šířka grafu (jsdom nemá rozměry) a chartH
  const sx = (x: number) => 52 + (x / 4) * (W - 52 - 10);     // x ∈ [0, 4] bez xDomain
  const series: Series[] = [
    { name: "Alpha", x: [0, 1, 2, 3, 4], y: [0, 10, 20, 30, 40], color: "#111" },
    { name: "Beta", x: [0, 1, 2, 3, 4], y: [5, 6, 7, 8, 9], color: "#222" },
    { name: "Ref", x: [0, 4], y: [1, 1], color: "#333", legend: false },
  ];
  beforeAll(() => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
  });
  beforeEach(() => {
    queryClient.setQueryData(["i18n", "en"], { _decimal: "." });
    queryClient.setQueryData(["i18n", "cs"], { _decimal: "," });
    useUi.setState({ lang: "en" });
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(() => ({
      left: 0, top: 0, right: W, bottom: H, width: W, height: H, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect);
  });
  afterEach(() => vi.restoreAllMocks());

  const setup = () => {
    render(<LineChart series={series} testid="t" xLabel="time" />);
    return { svg: screen.getByTestId("t").querySelector("svg") as SVGSVGElement, fig: screen.getByTestId("t") };
  };
  const move = async (svg: Element, x: number) => {
    fireEvent.pointerMove(svg, { clientX: sx(x), clientY: 100 });
    await waitFor(() => expect(screen.getByTestId("lc-x-0").textContent).toBe(String(x)));
  };
  const val = (k: number, i = 0) => screen.getByTestId(`lc-val-${k}-${i}`).textContent;

  it("graf je fokusovatelný a rozměr SVG zůstává", () => {
    const { fig, svg } = setup();
    expect(fig.getAttribute("tabindex")).toBe("0");
    expect(svg.getAttribute("height")).toBe(String(H));
  });

  it("pohyb ukazatele zobrazí hodnoty nejbližšího vzorku každé řady s legendou", async () => {
    const { svg } = setup();
    expect(screen.queryByTestId("lc-readout")).toBeNull();
    await move(svg, 2);
    expect(val(0)).toBe("20");
    expect(val(1)).toBe("7");
    expect(screen.queryByTestId("lc-row-2")).toBeNull();              // řada s legend: false v tabulce není
    fireEvent.pointerMove(svg, { clientX: sx(2.9), clientY: 100 });
    await waitFor(() => expect(screen.getByTestId("lc-x-0").textContent).toBe("3"));
    expect(val(0)).toBe("30");
    fireEvent.pointerLeave(screen.getByTestId("t"));
    expect(screen.queryByTestId("lc-readout")).toBeNull();
  });

  it("pohyb nepřekreslí cesty řad", async () => {
    const { svg } = setup();
    const paths = Array.from(svg.querySelectorAll("path"));
    await move(svg, 1);
    await move(svg, 3);
    Array.from(svg.querySelectorAll("path")).forEach((p, i) => expect(p).toBe(paths[i]));   // stejné uzly DOM
  });

  it("dva kliky dají hodnoty v A, B a rozdíly; třetí klik začne znovu; Esc smaže", async () => {
    const { svg, fig } = setup();
    await move(svg, 1);
    fireEvent.click(svg, { clientX: sx(1), clientY: 100 });
    fireEvent.pointerMove(svg, { clientX: sx(3), clientY: 100 });
    await waitFor(() => expect(screen.getByTestId("lc-x-1").textContent).toBe("3"));
    expect(val(0, 0)).toBe("10");                                     // A zůstává, druhý sloupec je živý odečet
    fireEvent.click(svg, { clientX: sx(3), clientY: 100 });
    expect(screen.getByTestId("lc-x-0").textContent).toBe("1");
    expect(screen.getByTestId("lc-x-1").textContent).toBe("3");
    expect(screen.getByTestId("lc-dx").textContent).toBe("2");
    expect(val(0, 0)).toBe("10");
    expect(val(0, 1)).toBe("30");
    expect(screen.getByTestId("lc-dy-0").textContent).toBe("20");
    expect(screen.getByTestId("lc-dy-1").textContent).toBe("2");
    expect(screen.getByTestId("lc-pin-1")).toBeTruthy();
    fireEvent.click(svg, { clientX: sx(4), clientY: 100 });           // třetí klik: nová čára A
    expect(screen.getByTestId("lc-x-0").textContent).toBe("4");
    fireEvent.pointerLeave(fig);                                      // bez ukazatele zůstává jen A
    expect(screen.queryByTestId("lc-dx")).toBeNull();
    fireEvent.keyDown(fig, { key: "Escape" });
    expect(screen.queryByTestId("lc-readout")).toBeNull();
    expect(screen.queryByTestId("lc-pin-0")).toBeNull();
  });

  it("šipky posouvají připíchnutou čáru o vzorek", async () => {
    const { svg, fig } = setup();
    await move(svg, 2);
    fireEvent.click(svg, { clientX: sx(2), clientY: 100 });
    fireEvent.pointerLeave(fig);
    fireEvent.keyDown(fig, { key: "ArrowRight" });
    expect(screen.getByTestId("lc-x-0").textContent).toBe("3");
    fireEvent.keyDown(fig, { key: "ArrowLeft" });
    fireEvent.keyDown(fig, { key: "ArrowLeft" });
    expect(screen.getByTestId("lc-x-0").textContent).toBe("1");
    expect(val(0)).toBe("10");
    for (let i = 0; i < 6; i++) fireEvent.keyDown(fig, { key: "ArrowLeft" });
    expect(screen.getByTestId("lc-x-0").textContent).toBe("0");        // na kraji se zastaví
  });

  it("desetinný oddělovač podle jazyka", async () => {
    useUi.setState({ lang: "cs" });
    render(<LineChart series={[{ name: "N", x: [0, 1], y: [0.5, 1.25], color: "#000" }]} testid="d" />);
    const s2 = screen.getByTestId("d").querySelector("svg") as SVGSVGElement;
    fireEvent.pointerMove(s2, { clientX: 52 + 658, clientY: 100 });
    await waitFor(() => expect(within(screen.getByTestId("lc-readout")).getByTestId("lc-val-0-0").textContent).toBe("1,25"));
  });

  it("klik na legendu řadu skryje z tabulky i z grafu a znovu zobrazí", async () => {
    const { svg } = setup();
    const btn = screen.getByTestId("t-leg-0");
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(svg.querySelectorAll("path").length).toBe(3);
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    expect(svg.querySelectorAll("path").length).toBe(2);
    fireEvent.pointerMove(svg, { clientX: sx(2), clientY: 100 });
    await waitFor(() => expect(screen.getByTestId("lc-readout")).toBeTruthy());
    expect(screen.queryByTestId("lc-row-1")).toBeNull();                 // zbývá jediná řada (Beta)
    expect(within(screen.getByTestId("lc-readout")).queryByText("Alpha")).toBeNull();
    expect(within(screen.getByTestId("lc-readout")).getByText("Beta")).toBeTruthy();
    fireEvent.click(btn);
    expect(svg.querySelectorAll("path").length).toBe(3);
  });

  it("tools={false} nástroje vypne", () => {
    render(<LineChart series={series} testid="n" tools={false} />);
    expect(screen.queryByTestId("lc-menu")).toBeNull();
    expect(screen.getByTestId("n").getAttribute("tabindex")).toBeNull();
  });

  it("nabídka: role, zavření Esc a klikem mimo", () => {
    setup();
    const b = screen.getByTestId("lc-menu");
    expect(b.getAttribute("aria-haspopup")).toBe("menu");
    fireEvent.click(b);
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(screen.getAllByRole("menuitem").length).toBe(3);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(b);
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
