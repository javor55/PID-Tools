// Graf odezvy scénáře podle návrhu: PV nahoře, MV pod ním, společná časová osa, svislé značky poruch a měřicí kurzory
// t1 / t2 (tlačítko „Měření“). Osy jsou HTML popisky kolem SVG s `preserveAspectRatio="none"` (jako v návrhu).
import { type MouseEvent } from "react";

export interface Line { name: string; x: ArrayLike<number>; y: ArrayLike<number>; color: string; dash?: string; width?: number;
  legend?: boolean }
export interface Marker { t: number; label: string }

const PV_H = 200, MV_H = 110;

function ticks(lo: number, hi: number, n = 5): number[] {
  const span = hi - lo || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9 * span; v += step) out.push(+v.toPrecision(12));
  return out;
}

function range(lines: Line[], x0: number, x1: number): [number, number] {
  let lo = Infinity, hi = -Infinity;
  for (const s of lines) for (let i = 0; i < s.x.length; i++) {
    const y = s.y[i];
    if (Number.isFinite(y) && s.x[i] >= x0 && s.x[i] <= x1) { if (y < lo) lo = y; if (y > hi) hi = y; }
  }
  if (!Number.isFinite(lo)) return [0, 1];
  if (hi - lo < 1e-12) { lo -= 1; hi += 1; }
  const pad = 0.06 * (hi - lo);
  return [lo - pad, hi + pad];
}

/** Hodnota řady v čase t (nejbližší vzorek zleva). */
export function valueAt(s: Line, t: number): number {
  let lo = 0, hi = s.x.length - 1;
  if (hi < 0) return NaN;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (s.x[m] <= t) lo = m; else hi = m - 1; }
  return s.y[lo];
}

function path(s: Line, x0: number, x1: number, y0: number, y1: number, H: number): string {
  const n = s.x.length, step = Math.max(1, Math.floor(n / 1200));
  let d = "", pen = false;
  for (let i = 0; i < n; i += step) {
    const x = s.x[i], y = s.y[i];
    if (!Number.isFinite(x) || !Number.isFinite(y)) { pen = false; continue; }
    d += `${pen ? "L" : "M"}${(((x - x0) / (x1 - x0 || 1)) * 1000).toFixed(1)},${((1 - (y - y0) / (y1 - y0)) * H).toFixed(1)}`;
    pen = true;
  }
  return d;
}

export function ScenarioChart({ pv, mv, markers, unitSec, unitName, cur, measure, onCursor, pvLabel, mvLabel, mainName, dec,
  testid }: {
  pv: Line[]; mv: Line[]; markers: Marker[]; unitSec: number; unitName: string; cur: number[]; measure: boolean;
  onCursor: (t: number) => void; pvLabel: string; mvLabel: string; mainName: string; dec: string; testid?: string;
}) {
  let x0 = Infinity, x1 = -Infinity;
  for (const s of [...pv, ...mv]) for (let i = 0; i < s.x.length; i++) {
    if (Number.isFinite(s.x[i])) { if (s.x[i] < x0) x0 = s.x[i]; if (s.x[i] > x1) x1 = s.x[i]; }
  }
  if (!Number.isFinite(x0) || x1 <= x0) return null;
  const f = (v: number, p = 4) => String(+v.toPrecision(p)).replace(".", dec === "," ? "," : ".");
  const [py0, py1] = range(pv, x0, x1), [my0, my1] = range(mv, x0, x1);
  const xt = ticks(x0 / unitSec, x1 / unitSec, 6);
  const pct = (t: number) => `${(100 * (t - x0) / (x1 - x0)).toFixed(2)}%`;
  const click = (e: MouseEvent<HTMLDivElement>) => {
    if (!measure) return;
    const r = e.currentTarget.getBoundingClientRect();
    onCursor(x0 + ((e.clientX - r.left) / r.width) * (x1 - x0));
  };
  const main = pv.find((s) => s.name === mainName) ?? pv[pv.length - 1];
  const [c1, c2] = cur;
  const tfmt = (t: number) => `${f(t / unitSec, 3)} ${unitName}`;
  const marks = (H: number) => <>
    {markers.map((m, i) => <line key={i} x1={((m.t - x0) / (x1 - x0)) * 1000} x2={((m.t - x0) / (x1 - x0)) * 1000} y1={0} y2={H}
      className="tc-mark" vectorEffect="non-scaling-stroke" />)}
  </>;
  const grid = (lo: number, hi: number, H: number) => ticks(lo, hi).map((v) =>
    <line key={v} x1={0} x2={1000} y1={(1 - (v - lo) / (hi - lo)) * H} y2={(1 - (v - lo) / (hi - lo)) * H} className="tc-grid"
      vectorEffect="non-scaling-stroke" />);
  const plot = (lines: Line[], lo: number, hi: number, H: number, withLabel: boolean) => (
    <div className={"tc-plot" + (measure ? " measure" : "")} style={{ height: H }} onClick={click}>
      <svg viewBox={`0 0 1000 ${H}`} preserveAspectRatio="none" width="100%" height={H} aria-hidden="true">
        {grid(lo, hi, H)}{marks(H)}
        {lines.map((s, i) => <path key={i} d={path(s, x0, x1, lo, hi, H)} fill="none" style={{ stroke: s.color }}
          strokeWidth={s.width ?? 2} strokeDasharray={s.dash} vectorEffect="non-scaling-stroke" />)}
      </svg>
      {withLabel && markers.map((m, i) => <span key={i} className="tc-mlab" style={{ left: pct(m.t) }}>{m.label}</span>)}
      {c1 !== undefined && <div className="tc-cur c1" style={{ left: pct(c1) }} />}
      {c2 !== undefined && <div className="tc-cur c2" style={{ left: pct(c2) }} />}
      {withLabel && c1 !== undefined && (
        <div className="tc-meas mono" style={{ left: pct(c1) }} data-testid="measure-box">
          t₁ = {tfmt(c1)}{c2 !== undefined && ` · t₂ = ${tfmt(c2)} · Δt = ${tfmt(c2 - c1)}`}
          {c2 !== undefined && main && ` · ΔPV(${main.name}) = ${f(valueAt(main, c2) - valueAt(main, c1), 3)}`}
        </div>)}
    </div>
  );
  return (
    <div className="tc" data-testid={testid}>
      <div className="tc-y" style={{ height: PV_H }}>
        {ticks(py0, py1).map((v) => <span key={v} style={{ top: `${(1 - (v - py0) / (py1 - py0)) * 100}%` }}>{f(v)}</span>)}
        <b className="tc-lab pv">{pvLabel}</b>
      </div>
      {plot(pv, py0, py1, PV_H, true)}
      <div className="tc-y" style={{ height: MV_H }}>
        {ticks(my0, my1, 3).map((v) => <span key={v} style={{ top: `${(1 - (v - my0) / (my1 - my0)) * 100}%` }}>{f(v)}</span>)}
        <b className="tc-lab mv">{mvLabel}</b>
      </div>
      {plot(mv, my0, my1, MV_H, false)}
      <span />
      <div className="tc-x">
        {xt.map((v, i) => <span key={v} style={{ left: pct(v * unitSec), transform: i === 0 && v * unitSec - x0 < 1e-9 ? "none" : "translateX(-50%)" }}>
          {f(v)}{i === xt.length - 1 ? ` ${unitName}` : ""}</span>)}
      </div>
    </div>
  );
}
