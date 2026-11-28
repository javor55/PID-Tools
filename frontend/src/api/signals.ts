// Binární balík signálů z API (app.signalpack.frame): [uint32 LE délka popisu][popis JSON][Float64 časy][Float32 hodnoty].
export interface PackSig { name: string; ti: number; off: number; n: number }
export interface PackMeta { sigs: PackSig[]; times: { off: number; n: number }[]; tmin: number; T: number; decim: number; hash: string }

export function unframe(buf: ArrayBuffer): { meta: PackMeta; blob: ArrayBuffer } {
  const n = new DataView(buf).getUint32(0, true);
  const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n))) as PackMeta;
  return { meta, blob: buf.slice(4 + n) };
}

export function series(meta: PackMeta, blob: ArrayBuffer, name: string): { t: Float64Array; v: Float32Array } | null {
  const s = meta.sigs.find((x) => x.name === name);
  if (!s) return null;
  const tm = meta.times[s.ti];
  return { t: new Float64Array(blob, tm.off, tm.n), v: new Float32Array(blob, s.off, s.n) };
}

/**
 * Sloučí dva balíky do jednoho (graf Modelu: signály mřížky + průběhy modelu + ostatní signály záznamu). Z druhého se vezmou
 * jen `names`; jeho časové osy a signály se přeindexují za první balík (blob druhého začíná na násobku 8 B kvůli
 * Float64Array). Časy druhého balíku se posunou o `dt` [s] (rozdíl počátků `tmin`, aby ležely na ose prvního).
 */
export function mergePacks(a: { meta: PackMeta; blob: ArrayBuffer }, b: { meta: PackMeta; blob: ArrayBuffer },
  names: string[], dt = 0): { meta: PackMeta; blob: ArrayBuffer } {
  const shift = Math.ceil(a.blob.byteLength / 8) * 8;
  const blob = new Uint8Array(shift + b.blob.byteLength);
  blob.set(new Uint8Array(a.blob), 0);
  blob.set(new Uint8Array(b.blob), shift);
  if (dt !== 0) for (const t of b.meta.times) {
    const f = new Float64Array(blob.buffer, shift + t.off, t.n);
    for (let i = 0; i < f.length; i++) f[i] += dt;
  }
  const meta: PackMeta = {
    sigs: [...a.meta.sigs, ...b.meta.sigs.filter((s) => names.includes(s.name))
      .map((s) => ({ ...s, ti: s.ti + a.meta.times.length, off: s.off + shift }))],
    times: [...a.meta.times, ...b.meta.times.map((t) => ({ ...t, off: t.off + shift }))],
    tmin: a.meta.tmin, T: Math.max(a.meta.T, b.meta.T + dt), decim: Math.max(a.meta.decim, b.meta.decim),
    hash: `${a.meta.hash}${b.meta.hash}`,
  };
  return { meta, blob: blob.buffer };
}
