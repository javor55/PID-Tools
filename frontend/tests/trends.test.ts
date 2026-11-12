// Trendy: čisté pomocné funkce (rozvržení panelů podle smyčky / veličiny, strom, zředění, vzorce, CSV, osa času).
import { describe, expect, it } from "vitest";
import {
  computeCalc, defaultSelection, describeSignals, formulaNames, layoutPanels, minmaxDecimate, niceTicks, panelAxes, quantityOf,
  statsOf, toCsv, treeGroups, unitFromName, valueAt, type LoopLite, type Series,
} from "../src/tabs/data/trends/model";
import { panView, timeStep, timeTicks, zoomView } from "../src/tabs/data/trends/TrendChart";

const sources = [
  { id: "s1", name: "a.csv", columns: ["TIC102.PV", "TIC102.SP", "TIC102.MV", "TI110", "FIC205.PV [t/h]", "FIC205.MV"] },
  { id: "s2", name: "b.csv", columns: ["PI201", "X"] },
];
const loops: LoopLite[] = [
  { index: 0, tag: "TIC102", roles: { pv: { source: "s1", column: "TIC102.PV" }, sp: { source: "s1", column: "TIC102.SP" },
    mv: { source: "s1", column: "TIC102.MV" }, dv: [{ source: "s1", column: "TI110" }, { source: "s2", column: "PI201" }] } },
  { index: 1, tag: "FIC205", roles: { pv: { source: "s1", column: "FIC205.PV [t/h]" }, mv: { source: "s1", column: "FIC205.MV" } } },
];
const titles = { one: "ALL", none: "OTHER" };

describe("signály a veličiny", () => {
  const sigs = describeSignals(sources, loops);
  const by = Object.fromEntries(sigs.map((s) => [s.ref, s]));

  it("role, smyčka a barva podle role", () => {
    expect(by["s1:TIC102.PV"]).toMatchObject({ loop: "TIC102", role: "PV", label: "PV", color: "#1f5fa8", dash: null });
    expect(by["s1:TIC102.SP"]).toMatchObject({ role: "SP", dash: "6 4" });
    expect(by["s1:TI110"]).toMatchObject({ loop: "TIC102", role: "DV", label: "TI110" });
    expect(by["s2:X"]).toMatchObject({ loop: null, role: "" });
  });

  it("veličina: jednotka v názvu, MV = %, jinak ISA písmeno", () => {
    expect(unitFromName("FIC205.PV [t/h]")).toBe("t/h");
    expect(quantityOf("a", "MV", "TIC1").key).toBe("u:%");
    expect(by["s1:TIC102.PV"].quantity).toBe(by["s1:TI110"].quantity);          // teploty spolu
    expect(by["s1:TIC102.PV"].quantity).toBe("q:T");
    expect(by["s1:FIC205.PV [t/h]"].quantity).toBe("u:t/h");
    expect(by["s2:PI201"].quantity).toBe("q:P");
    expect(by["s1:TIC102.MV"].quantity).toBe(by["s1:FIC205.MV"].quantity);      // MV obou smyček = %
  });

  it("výchozí výběr = PV / SP / MV", () => {
    expect(defaultSelection(sigs)).toEqual(["s1:TIC102.PV", "s1:TIC102.SP", "s1:TIC102.MV", "s1:FIC205.PV [t/h]", "s1:FIC205.MV"]);
  });

  it("strom: podle smyček i zdrojů, hledání, jen aktivní smyčka", () => {
    const g = treeGroups(sigs, "loop", "", null, "none");
    expect(g.map((x) => x.title)).toEqual(["TIC102", "FIC205", "none"]);          // „bez smyčky“ až na konec
    expect(treeGroups(sigs, "source", "", null).map((x) => [x.title, x.items.length])).toEqual([["a.csv", 6], ["b.csv", 2]]);
    expect(treeGroups(sigs, "loop", "pi2", null, "none").flatMap((x) => x.items.map((i) => i.ref))).toEqual(["s2:PI201"]);
    expect(treeGroups(sigs, "loop", "", "FIC205", "none")).toHaveLength(1);
  });

  it("rozvržení panelů: 1 panel / na smyčku / na veličinu", () => {
    const pick = sigs.filter((s) => ["s1:TIC102.PV", "s1:TIC102.SP", "s1:TIC102.MV", "s1:FIC205.MV", "s2:PI201", "s2:X"].includes(s.ref));
    expect(layoutPanels([], "loop", titles)).toEqual([]);
    expect(layoutPanels(pick, "one", titles)).toEqual([{ id: "all", title: "ALL", refs: pick.map((s) => s.ref) }]);
    const loop = layoutPanels(pick, "loop", titles);
    expect(loop.map((p) => [p.title, p.refs.length])).toEqual([["TIC102", 4], ["FIC205", 1], ["b.csv", 1]]);
    const unit = layoutPanels(pick, "unit", titles);
    expect(unit.map((p) => [p.title, p.refs])).toEqual([
      ["T", ["s1:TIC102.PV", "s1:TIC102.SP"]], ["[%]", ["s1:TIC102.MV", "s1:FIC205.MV"]], ["P", ["s2:PI201"]], ["OTHER", ["s2:X"]]]);
  });

  it("osy panelu: sdílená osa = jedna pro vše, jinak osa na veličinu", () => {
    const info = new Map(sigs.map((s) => [s.ref, s]));
    const mk = (ref: string, lo: number, hi: number): Series => ({ ref, t: [0, 1, 2], v: [lo, (lo + hi) / 2, hi] });
    const data = [mk("s1:TIC102.PV", 10, 20), mk("s1:TIC102.SP", 12, 30), mk("s1:TIC102.MV", 0, 100)];
    const own = panelAxes(data, info, false, 0, 2);
    expect(own.map((a) => a.refs.length)).toEqual([2, 1]);                       // PV + SP (°C) spolu, MV (%) zvlášť
    expect(own[0].lo).toBeLessThan(10); expect(own[0].hi).toBeGreaterThan(30);
    expect(panelAxes(data, info, true, 0, 2)).toHaveLength(1);
    expect(panelAxes(data, info, true, 5, 6)).toEqual([]);                        // okno bez dat
  });
});

describe("zředění, hodnoty a statistika", () => {
  it("min / max po skupinách zachová špičky a zkrátí řadu", () => {
    const n = 100000;
    const t = Array.from({ length: n }, (_, i) => i), v = t.map((i) => (i === 54321 ? 1000 : Math.sin(i / 50)));
    const [tt, vv] = minmaxDecimate(t, v, 0, n, 500) as number[][];
    expect(tt.length).toBeLessThanOrEqual(1000);
    expect(Math.max(...vv)).toBe(1000);
    expect([...tt].sort((a, b) => a - b)).toEqual(tt);
    const [t2] = minmaxDecimate(t, v, 10, 20, 500) as number[][];                // krátký úsek beze změny
    expect(t2).toHaveLength(11);
  });

  it("hodnota v čase kurzoru: interpolace, mimo záznam a v mezeře null", () => {
    const s: Series = { ref: "x", t: [0, 10, 100], v: [0, 10, 100] };
    expect(valueAt(s, 5)).toBe(5);
    expect(valueAt(s, 10)).toBe(10);
    expect(valueAt(s, -1)).toBeNull();
    expect(valueAt(s, 101)).toBeNull();
    expect(valueAt(s, 50, 20)).toBeNull();
  });

  it("statistika úseku", () => {
    const s: Series = { ref: "x", t: [0, 1, 2, 3], v: [1, 2, 3, 100] };
    const st = statsOf(s, 0, 2);
    expect(st).toMatchObject({ min: 1, max: 3, mean: 2 });
    expect(st.std).toBeCloseTo(Math.sqrt(2 / 3));
    expect(statsOf(s, 10, 20).mean).toBeNull();
  });
});

describe("vypočtené signály (vzorce viewer_an.js)", () => {
  const sigs = describeSignals(sources, loops);
  const names = formulaNames(sigs);
  const pv: Series = { ref: "s1:TIC102.PV", t: [0, 1, 2, 3], v: [10, 11, 12, 13] };
  const sp: Series = { ref: "s1:TIC102.SP", t: [0, 2], v: [15, 15] };         // jiné časy → poslední známá hodnota

  it("odchylka SP − PV s odkazem celým i názvem sloupce", () => {
    const m = new Map([[pv.ref, pv], [sp.ref, sp]]);
    const r = computeCalc({ id: "1", name: "e", expr: "[s1:TIC102.SP] - TIC102.PV", unit: "" }, names, m);
    expect(r.error).toBeNull();
    expect(Array.from(r.series!.v)).toEqual([5, 4, 3, 2]);
    expect(Array.from(r.series!.t)).toEqual([0, 1, 2, 3]);
  });

  it("chyby: neznámý signál, zlá syntaxe, chybějící data", () => {
    const m = new Map([[pv.ref, pv]]);
    expect(computeCalc({ id: "1", name: "e", expr: "[nope] + 1", unit: "" }, names, m).error).toBeTruthy();
    expect(computeCalc({ id: "1", name: "e", expr: "TIC102.PV +", unit: "" }, names, m).error).toBeTruthy();
    const none = computeCalc({ id: "1", name: "e", expr: "TIC102.SP * 2", unit: "" }, names, m);
    expect(none.series).toBeNull();
    expect(none.error).toBeNull();
  });

  it("filtry v čase: průměr a derivace", () => {
    const m = new Map([[pv.ref, pv]]);
    expect(computeCalc({ id: "1", name: "d", expr: "der(TIC102.PV)", unit: "" }, names, m).series!.v.length).toBeGreaterThan(0);
  });
});

describe("CSV a osa času", () => {
  it("CSV: sjednocení časů, prázdné buňky, čas hodin, uvozovky v názvu", () => {
    const csv = toCsv([{ name: "s1:A", t: [0, 1, 2], v: [1, 2, 3] }, { name: 's2:B;"x"', t: [1, 2.5], v: [10, 20] }], "2026-03-01T08:00:00", 0, 2);
    const lines = csv.split("\n");
    expect(lines[0]).toBe('t [s];clock;s1:A;"s2:B;""x"""');
    expect(lines).toHaveLength(4);                                                // časy 0, 1, 2 (2,5 mimo okno)
    expect(lines[1]).toBe("0;2026-03-01 08:00:00.000;1;");
    expect(lines[2]).toBe("1;2026-03-01 08:00:01.000;2;10");
    expect(toCsv([{ name: "A", t: [0], v: [NaN] }], null, 0, 1).split("\n")[1]).toBe("0;");
  });

  it("značky času a okno zoomu", () => {
    expect(timeStep(3600, 8)).toBe(600);
    expect(timeTicks(0, 100, null, 5)).toEqual([0, 30, 60, 90]);
    const ticks = timeTicks(30, 7230, "2026-03-01T08:00:00", 6);                 // značky na celých hodinách / půlhodinách hodin
    expect(ticks.every((t) => ((Date.parse("2026-03-01T08:00:00Z") / 1000 + t) % 1800) === 0)).toBe(true);
    const full: [number, number] = [0, 1000];
    expect(zoomView([0, 1000], full, 0.5, 500)).toEqual([250, 750]);
    expect(zoomView([250, 750], full, 4, 500)).toBeNull();                       // zpět na celý rozsah
    expect(panView([100, 200], full, -500)).toEqual([0, 100]);
    expect(panView([100, 200], full, 5000)).toEqual([900, 1000]);
    expect(niceTicks(0, 100, 4)).toEqual([0, 25, 50, 75, 100]);
  });
});
