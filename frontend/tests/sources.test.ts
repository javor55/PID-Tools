// Čisté funkce obrazovky Zdroje a smyčky: geometrie časových pruhů, stav mapování, změny rolí, minigraf, formáty.
import { describe, expect, it } from "vitest";
import {
  fmtClock, fmtDur, fmtPeriod, fmtRange, hoursToSec, type LoopMapping, mappingBody, mappingStatus, niceStep, parseKey, refKey,
  refLabel, secToHours, sparkPath, ticks, timeline, usageOf, withoutDv, withRole,
} from "../src/tabs/data/sources/geometry";

const ref = (source: string, column: string) => ({ source, column });
const loop = (over: Partial<LoopMapping["roles"]> = {}, rest: Partial<LoopMapping> = {}): LoopMapping => ({
  tag: "TIC101", description: "", roles: { dv: [], ...over }, has_data: true, sources: [], ...rest });

describe("timeline", () => {
  const spans = [{ start: 0, end: 480 }, { start: 120, end: 480 }, { start: 180, end: 420 }];
  it("pruhy v procentech osy od nejdřívějšího začátku po nejpozdější konec", () => {
    const t = timeline(spans, "overlap", { start: 180, end: 420 })!;
    expect([t.lo, t.hi]).toEqual([0, 480]);
    expect(t.bars[0]).toEqual({ left: 0, width: 100 });
    expect(t.bars[1]!.left).toBeCloseTo(25);
    expect(t.bars[1]!.width).toBeCloseTo(75);
    expect(t.common!.left).toBeCloseTo(37.5);
    expect(t.common!.width).toBeCloseTo(50);
  });
  it("sjednocení zvýrazní celou osu, bez společného úseku v překryvu žádné zvýraznění", () => {
    expect(timeline(spans, "union", null)!.common).toEqual({ left: 0, width: 100 });
    expect(timeline(spans, "overlap", null)!.common).toBeNull();
  });
  it("zdroj bez dat nemá pruh, bez jakéhokoli rozsahu není osa", () => {
    const t = timeline([{ start: 10, end: 20 }, { start: null, end: null }, {}], "overlap", null)!;
    expect(t.bars[1]).toBeNull();
    expect(t.bars[2]).toBeNull();
    expect(timeline([{ start: null, end: null }], "overlap", null)).toBeNull();
    expect(timeline([], "union", null)).toBeNull();
  });
  it("jediný bod v čase i velmi krátký zdroj mají viditelnou šířku", () => {
    const t = timeline([{ start: 5, end: 5 }, { start: 0, end: 10000 }], "overlap", null)!;
    expect(t.bars[0]!.width).toBeGreaterThan(0);
    const one = timeline([{ start: 5, end: 5 }], "overlap", null)!;
    expect(one.hi).toBeGreaterThan(one.lo);
  });
});

describe("osa", () => {
  it("krok osy je hezké číslo", () => {
    expect(niceStep(14400, 5)).toBe(3600);
    expect(niceStep(100, 5)).toBe(30);
    expect(niceStep(2, 5)).toBe(0.5);
  });
  it("značky se zarovnají na hodiny podle počátku", () => {
    const origin = "2026-03-01T08:30:00";
    const t = ticks(0, 14400, origin, 4);
    expect(t.map((x) => fmtClock(x, origin))).toEqual(["9:00", "10:00", "11:00", "12:00"]);
  });
  it("čas a rozsah s hodinami i bez nich", () => {
    const origin = "2026-10-08T06:00:00";
    expect(fmtClock(3600, origin)).toBe("7:00");
    expect(fmtClock(3600, origin, true)).toBe("8.10. 7:00");
    expect(fmtRange(0, 8 * 3600, origin)).toBe("8.10. 6:00–14:00");
    expect(fmtRange(0, 30 * 3600, origin)).toBe("8.10. 6:00 – 9.10. 12:00");
    expect(fmtRange(0, 90, null)).toBe("0 s – 90 s");
    expect(fmtRange(null, 5, origin)).toBe("–");
  });
  it("doby a periody", () => {
    expect(fmtDur(0.5)).toBe("0,5 s");
    expect(fmtDur(3600)).toBe("1 h");
    expect(fmtPeriod(0.5)).toBe("500 ms");
    expect(fmtPeriod(5)).toBe("5 s");
    expect(fmtPeriod(null)).toBe("–");
  });
  it("posun hodiny ⇄ sekundy", () => {
    expect(hoursToSec(1)).toBe(3600);
    expect(hoursToSec(-0.5)).toBe(-1800);
    expect(secToHours(5400)).toBe(1.5);
  });
});

describe("mappingStatus", () => {
  const r = ref("s1", "A");
  it("úplná smyčka má PV, SP a MV", () => expect(mappingStatus(loop({ pv: r, sp: r, mv: r }))).toEqual({ kind: "complete", level: "ok" }));
  it("bez SP je jen upozornění", () => expect(mappingStatus(loop({ pv: r, mv: r }))).toEqual({ kind: "no_sp", level: "warn" }));
  it("bez MV / PV je neúplná", () => {
    expect(mappingStatus(loop({ pv: r }))).toEqual({ kind: "only_pv", level: "err" });
    expect(mappingStatus(loop({ pv: r, sp: r }))).toEqual({ kind: "no_mv", level: "err" });
    expect(mappingStatus(loop({ mv: r }))).toEqual({ kind: "no_pv", level: "err" });
    expect(mappingStatus(loop())).toEqual({ kind: "no_pv", level: "err" });
  });
  it("úplné role bez dat jsou upozornění", () => expect(mappingStatus(loop({ pv: r, sp: r, mv: r }, { has_data: false })).kind).toBe("no_data"));
});

describe("role", () => {
  const a = ref("s1", "TIC101.PV"), b = ref("s2", "FIC205.PV");
  it("withRole nahradí roli a nemění původní objekt", () => {
    const m = loop({ pv: a });
    const n = withRole(m, "sp", b);
    expect(n.roles.sp).toEqual(b);
    expect(m.roles.sp).toBeUndefined();
    expect(withRole(n, "sp", null).roles.sp).toBeNull();
  });
  it("DV se přidává bez duplicit a odebírá podle pořadí", () => {
    let m = withRole(loop(), "dv", a);
    m = withRole(m, "dv", a);
    m = withRole(m, "dv", b);
    expect(m.roles.dv).toEqual([a, b]);
    expect(withRole(m, "dv", null)).toBe(m);
    expect(withoutDv(m, 0).roles.dv).toEqual([b]);
  });
  it("tělo PUT neobsahuje pole jen z odpovědi", () => {
    const body = mappingBody(loop({ pv: a }, { index: 3, norm_pv: [0, 150] }));
    expect(Object.keys(body).sort()).toEqual(["cascade_to", "description", "norm_mv", "norm_pv", "roles", "tag"]);
    expect(body.norm_pv).toEqual([0, 150]);
    expect(body.norm_mv).toBeNull();
  });
  it("klíč sloupce se dá zpět rozebrat (i s dvojtečkou v názvu)", () => {
    const r = ref("s1", "A:B/C");
    expect(parseKey(refKey(r))).toEqual(r);
    expect(parseKey("bez-oddelovace")).toBeNull();
  });
  it("použití sloupců ve smyčkách (jeden sloupec ve více smyčkách)", () => {
    const u = usageOf([loop({ pv: a, dv: [b] }), loop({ pv: b, mv: a })]);
    expect(u.get(refKey(a))).toEqual([{ loop: 0, role: "pv" }, { loop: 1, role: "mv" }]);
    expect(u.get(refKey(b))).toEqual([{ loop: 0, role: "dv" }, { loop: 1, role: "pv" }]);
  });
  it("popisek „soubor › sloupec“ bez přípony", () => {
    expect(refLabel(a, [{ id: "s1", name: "historian_K2.csv" }])).toBe("historian_K2 › TIC101.PV");
    expect(refLabel(a, [])).toBe("s1 › TIC101.PV");
  });
});

describe("sparkPath", () => {
  it("normalizuje do rámečku a vrací prázdno pro krátké řady", () => {
    expect(sparkPath([0], [1])).toBe("");
    const p = sparkPath([0, 1, 2], [0, 10, 0], 60, 18, 0);
    expect(p).toBe("M0.0,18.0 L30.0,0.0 L60.0,18.0");
  });
  it("konstantní řada je uprostřed", () => expect(sparkPath([0, 1], [5, 5], 60, 18)).toBe("M0.0,9.0 L60.0,9.0"));
});
