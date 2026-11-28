// Sloučení binárních balíků signálů (graf Modelu: mřížka + průběhy modelu + ostatní signály záznamu).
import { describe, expect, it } from "vitest";
import { mergePacks, series, type PackMeta } from "../src/api/signals";

/** Balík: časy (Float64) a hodnoty (Float32) jednoho signálu `name`. */
function pack(name: string, t: number[], v: number[], tmin = 0): { meta: PackMeta; blob: ArrayBuffer } {
  const tb = new Float64Array(t), vb = new Float32Array(v);
  const blob = new Uint8Array(tb.byteLength + vb.byteLength);
  blob.set(new Uint8Array(tb.buffer), 0);
  blob.set(new Uint8Array(vb.buffer), tb.byteLength);
  return { meta: { sigs: [{ name, ti: 0, off: tb.byteLength, n: v.length }], times: [{ off: 0, n: t.length }], tmin, T: t[t.length - 1], decim: 1, hash: name },
    blob: blob.buffer };
}

describe("mergePacks", () => {
  it("přeindexuje signály a časové osy druhého balíku za první", () => {
    const a = pack("pv", [0, 1, 2], [1, 2, 3]), b = pack("model", [0, 1, 2, 3], [4, 5, 6, 7]);
    const m = mergePacks(a, b, ["model"]);
    expect(m.meta.sigs.map((s) => s.name)).toEqual(["pv", "model"]);
    expect(m.meta.times).toHaveLength(2);
    expect(Array.from(series(m.meta, m.blob, "pv")!.v)).toEqual([1, 2, 3]);
    const s = series(m.meta, m.blob, "model")!;
    expect(Array.from(s.v)).toEqual([4, 5, 6, 7]);
    expect(Array.from(s.t)).toEqual([0, 1, 2, 3]);
    expect(m.meta.T).toBe(3);
    expect(m.meta.hash).toBe("pvmodel");
  });
  it("vezme jen vyjmenované signály a posune časy o dt", () => {
    const a = pack("pv", [0, 1, 2], [1, 2, 3]), b = pack("x", [10, 11], [9, 8]);
    const none = mergePacks(a, b, []);
    expect(none.meta.sigs.map((s) => s.name)).toEqual(["pv"]);
    const m = mergePacks(a, b, ["x"], -10);
    expect(Array.from(series(m.meta, m.blob, "x")!.t)).toEqual([0, 1]);
    expect(Array.from(series(m.meta, m.blob, "pv")!.t)).toEqual([0, 1, 2]);   // první balík beze změny
    expect(m.meta.T).toBe(2);
  });
});
