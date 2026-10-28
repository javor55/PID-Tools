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
