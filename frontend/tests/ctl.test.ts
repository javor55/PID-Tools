// Knihovna a editor regulátorů: čisté pomocné funkce (seskupení, značky chyb, skládání částí, rovnice, schéma).
import { describe, expect, it } from "vitest";
import type { Part, Profile, Summary } from "../src/settings/ctlApi";
import {
  blockChain, countChecks, equationText, groupControllers, markersByLine, offsetOf, problemText, selectedPart, setPart, specials,
  syncParams, tagsOf,
} from "../src/settings/ctlHelpers";

const L: Summary[] = [
  { id: "isa_ideal", vendor: "Obecný", name: "ISA ideální PID", tag: "preset", verified: true },
  { id: "pcs7", vendor: "Siemens", name: "PIDConL", tag: "preset", verified: false },
  { id: "my1", vendor: "Obecný", name: "Kotelna K2", tag: "custom", verified: false },
];

const base = (): Profile => ({
  format: "pidctrl", version: 1, id: "x", name: "x",
  structure: { form: "ideal", d: { source: "error", filter: "td_over_n" }, antiwindup: "none", output: {} },
  params: [{ key: "Kc", role: "Kc" }, { key: "N", role: "N", default: 5 }],
});

const parts: Part[] = [
  { kind: "deadbands", id: "gap", description: "", params: [{ role: "deadband", unit: "%", default: 0 }, { role: "gap_gain", unit: "-", default: 0.3, range: [0, 1] }] },
  { kind: "deadbands", id: "step", description: "", params: [{ role: "deadband", unit: "%", default: 0 }] },
  { kind: "d_filters", id: "td_over_n", description: "", params: [{ role: "N", unit: "-", default: 5 }] },
  { kind: "d_filters", id: "none", description: "", params: [] },
];

describe("groupControllers", () => {
  it("groups into Siemens / other / mine and drops empty groups", () => {
    expect(groupControllers(L).map((g) => [g.id, g.items.map((i) => i.id)])).toEqual([
      ["siemens", ["pcs7"]], ["other", ["isa_ideal"]], ["mine", ["my1"]]]);
    expect(groupControllers(L, "kotel").map((g) => g.id)).toEqual(["mine"]);
    expect(groupControllers(L, "zzz")).toEqual([]);
  });
  it("tags: verified / unverified plus custom", () => {
    expect(tagsOf(L[0])).toEqual(["verified"]);
    expect(tagsOf(L[2])).toEqual(["unverified", "custom"]);
  });
});

describe("markersByLine", () => {
  const issue = (line: number, col: number, message = "m") => ({ line, col, code: "c", message });
  it("maps errors to lines, error beats warning, line is clamped", () => {
    const m = markersByLine("a\nb\nc", { errors: [issue(2, 3, "bad"), issue(99, 1, "late")], warnings: [issue(2, 1, "warn"), issue(1, 1, "w1")] });
    expect(m.get(2)).toMatchObject({ kind: "error", message: "bad", col: 3 });
    expect(m.get(1)).toMatchObject({ kind: "warning" });
    expect(m.get(3)).toMatchObject({ kind: "error", message: "late" });
    expect(markersByLine("x", null).size).toBe(0);
  });
  it("offsetOf converts line:col to a character offset", () => {
    expect(offsetOf("ab\ncd\nef", 2, 2)).toBe(4);
    expect(offsetOf("ab", 9, 9)).toBe(2);
  });
});

describe("composition", () => {
  it("reads and sets parts in structure", () => {
    const p = setPart(setPart(base(), "deadbands", "gap"), "forms", "series");
    expect(selectedPart(p, "deadbands")).toBe("gap");
    expect(selectedPart(p, "forms")).toBe("series");
    expect(selectedPart(setPart(p, "deadbands", "none"), "deadbands")).toBe("none");
    expect(specials(p)).toContain("deadbands/gap");
    expect(selectedPart(base(), "antiwindups")).toBe("none");
  });
  it("syncParams adds parameters of the selected parts and drops those of dropped parts", () => {
    const p = syncParams(setPart(base(), "deadbands", "gap"), parts);
    expect(p.params.map((x) => x.role)).toEqual(["Kc", "N", "deadband", "gap_gain"]);
    const q = syncParams(setPart(p, "d_filters", "none"), parts);
    expect(q.params.map((x) => x.role)).toEqual(["Kc", "deadband", "gap_gain"]);
    const r = syncParams(setPart(q, "deadbands", "none"), parts);
    expect(r.params.map((x) => x.role)).toEqual(["Kc"]);
  });
  it("equation and block chain follow the structure", () => {
    expect(equationText(base())).toContain("Ti·s");
    expect(equationText(setPart(base(), "algorithms", "velocity")).startsWith("Δu")).toBe(true);
    expect(blockChain(base())).toEqual(["rg_ui_blk_sp", "rg_ui_blk_error", "rg_ui_blk_pid", "rg_ui_blk_limits", "rg_ui_blk_mv"]);
    expect(blockChain({ ...base(), kind: "program" })).toContain("rg_ui_blk_program");
  });
});

describe("misc", () => {
  it("problemText unpacks 422 details", () => {
    expect(problemText(JSON.stringify({ message: "m", problems: [{ path: "params[0]", message: "bad" }] }))).toBe("params[0]: bad");
    expect(problemText("plain")).toBe("plain");
  });
  it("countChecks counts by status", () => {
    expect(countChecks([{ status: "ok" }, { status: "ok" }, { status: "warn" }])).toEqual({ ok: 2, warn: 1, fail: 0 });
  });
});
