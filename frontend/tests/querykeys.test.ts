// Tabulka nastavení → skupiny dotazů a cílené zneplatnění (TICKET-006).
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { affected, ALL_GROUPS, invalidateGroups } from "../src/queryKeys";

describe("affected", () => {
  it("opt_ms nezneplatní data ani model", () => {
    const g = affected(["opt_ms"]);
    expect(g).not.toContain("data");
    expect(g).not.toContain("model");
    expect(g).toContain("tuning");
    expect(g).not.toContain("ws");
  });
  it("rozsah pv_hi zneplatní všechny skupiny", () => expect(affected(["pv_hi"])).toEqual([...ALL_GROUPS]));
  it("neznámý klíč = všechny skupiny", () => expect(affected(["neexistuje"])).toEqual([...ALL_GROUPS]));
  it("dview = jen ws", () => expect(affected(["dview"])).toEqual(["ws"]));
  it("prefixy: method| ladění, fx| identifikace, rep_ protokol", () => {
    expect(affected(["method|abc"])).not.toContain("model");
    expect(affected(["fx|M1|0"])).toContain("model");
    expect(affected(["rep_author"])).toEqual(["project", "ws"]);
  });
  it("více klíčů = sjednocení", () => {
    const g = affected(["opt_ms", "chosen"]);
    expect(g).toContain("model");
    expect(g).toContain("tuning");
  });
});

describe("invalidateGroups", () => {
  const mk = () => {
    const qc = new QueryClient();
    for (const k of [["ws", "w"], ["ws", "w", "sources"], ["ws", "w", "tuning"], ["ws", "w", "settings"],
      ["ws", "w", "save-state"], ["ws", "w", "sim", 1, "kpi"], ["ws", "w", "validate|x"], ["ws", "w", "neznama"],
      ["ws", "jiny", "tuning"]]) qc.setQueryData(k, 1);
    return qc;
  };
  const inv = (qc: QueryClient, k: unknown[]) => qc.getQueryState(k)?.isInvalidated;

  it("zneplatní jen dotazy skupiny a vždy settings + save-state", async () => {
    const qc = mk();
    await invalidateGroups(qc, "w", ["tuning"]);
    expect(inv(qc, ["ws", "w", "tuning"])).toBe(true);
    expect(inv(qc, ["ws", "w", "sim", 1, "kpi"])).toBe(true);
    expect(inv(qc, ["ws", "w", "settings"])).toBe(true);
    expect(inv(qc, ["ws", "w", "save-state"])).toBe(true);
    expect(inv(qc, ["ws", "w", "neznama"])).toBe(true);        // neznámá část patří do všech skupin
    expect(inv(qc, ["ws", "w", "sources"])).toBe(false);
    expect(inv(qc, ["ws", "w", "validate|x"])).toBe(false);
    expect(inv(qc, ["ws", "w"])).toBe(false);
    expect(inv(qc, ["ws", "jiny", "tuning"])).toBe(false);
  });
  it("opts.settings = false nezneplatní settings, save-state ano", async () => {
    const qc = mk();
    await invalidateGroups(qc, "w", ["tuning"], { settings: false });
    expect(inv(qc, ["ws", "w", "settings"])).toBe(false);
    expect(inv(qc, ["ws", "w", "save-state"])).toBe(true);
  });
  it("skupina ws zahrne samotný prostor", async () => {
    const qc = mk();
    await invalidateGroups(qc, "w", ["ws"]);
    expect(inv(qc, ["ws", "w"])).toBe(true);
    expect(inv(qc, ["ws", "w", "sources"])).toBe(false);
  });
});
