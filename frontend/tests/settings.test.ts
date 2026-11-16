// Typování nastavení smyčky (TICKET-013): čtení neexistujícího klíče musí selhat při `tsc` a pevné klíče mají typ ze schématu.
import { describe, expect, it } from "vitest";
import type { LoopSettings, SettingsData } from "../src/data";

describe("LoopSettings", () => {
  it("čtení neexistujícího klíče je typová chyba, známé klíče mají typ", () => {
    const st = { samp: 1, ctype: "PI", mvl_lo: null } as unknown as LoopSettings;
    // @ts-expect-error neexistující klíč na typu LoopSettings (bez průniku s Record) nesmí projít
    const bad = st.neexistuje;
    const samp: number = st.samp;                       // pevný číselný klíč má vždy hodnotu
    const lo: number | null = st.mvl_lo;                // klíč, který smí být None, je number | null
    const ct: "PI" | "PID" | "PD" = st.ctype;           // výčet je Literal
    expect([bad, samp, lo, ct]).toEqual([undefined, 1, null, "PI"]);
  });

  it("průnik s Record dovolí dynamický klíč s prefixem", () => {
    const st = { samp: 1, "tc|M|SIMC|PI": 12 } as unknown as SettingsData;
    expect(st["tc|M|SIMC|PI"]).toBe(12);
    const samp: number = st.samp;
    expect(samp).toBe(1);
  });
});
