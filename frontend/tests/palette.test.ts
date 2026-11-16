// Paleta prohlížeče záznamu: čtení proměnných CSS, náhradní hodnoty a přepočet při změně data-theme.
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FALLBACK, readPalette, usePalette } from "../src/lib/palette";

const VARS = ["--pid-pv", "--pid-sp", "--pid-mv", "--pid-pos", ...Array.from({ length: 14 }, (_, i) => `--pid-series-${i + 1}`),
  ...Array.from({ length: 4 }, (_, i) => `--pid-dist-${i + 1}`)];
const reset = () => { VARS.forEach((v) => document.documentElement.style.removeProperty(v)); document.documentElement.removeAttribute("data-theme"); };
afterEach(reset);

describe("readPalette", () => {
  it("bez proměnných CSS vrátí FALLBACK", () => {
    expect(readPalette()).toEqual(FALLBACK);
    expect(FALLBACK.series).toHaveLength(14);
    expect(FALLBACK.dist).toHaveLength(4);
  });

  it("s nastavenými proměnnými vrátí je (oříznuté)", () => {
    const s = document.documentElement.style;
    s.setProperty("--pid-pv", "#123456"); s.setProperty("--pid-sp", " #234567 "); s.setProperty("--pid-mv", "#345678");
    s.setProperty("--pid-pos", "#456789"); s.setProperty("--pid-series-1", "#111111"); s.setProperty("--pid-series-14", "#141414");
    s.setProperty("--pid-dist-2", "#222222");
    const p = readPalette();
    expect([p.pv, p.sp, p.mv, p.pos]).toEqual(["#123456", "#234567", "#345678", "#456789"]);
    expect(p.series[0]).toBe("#111111");
    expect(p.series[13]).toBe("#141414");
    expect(p.series[1]).toBe(FALLBACK.series[1]);
    expect(p.dist[1]).toBe("#222222");
    expect(p.dist[0]).toBe(FALLBACK.dist[0]);
  });
});

describe("usePalette", () => {
  it("po změně data-theme a proměnné vrátí novou hodnotu", async () => {
    const { result } = renderHook(() => usePalette());
    expect(result.current.pv).toBe(FALLBACK.pv);
    act(() => {
      document.documentElement.style.setProperty("--pid-pv", "#abcdef");
      document.documentElement.setAttribute("data-theme", "dark");
    });
    await waitFor(() => expect(result.current.pv).toBe("#abcdef"));
  });

  it("po odpojení už atribut nesleduje", async () => {
    const { result, unmount } = renderHook(() => usePalette());
    unmount();
    document.documentElement.style.setProperty("--pid-pv", "#fedcba");
    document.documentElement.setAttribute("data-theme", "dark");
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.pv).toBe(FALLBACK.pv);
  });
});
