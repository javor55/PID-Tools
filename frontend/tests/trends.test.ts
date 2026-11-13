// Trendy: čisté pomocné funkce (signály podle smyček a veličin, skupiny seznamu, rozvržení panelů).
import { describe, expect, it } from "vitest";
import { describeSignals, layoutPanels, quantityOf, treeGroups, unitFromName, type LoopLite } from "../src/tabs/data/trends/model";

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
});
