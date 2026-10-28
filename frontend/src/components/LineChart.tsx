// Jednoduchý graf průběhů (SVG) – odezvy ladění, frekvenční charakteristiky. Řady se zředí na ~1500 bodů.
import { useMemo } from "react";

// legend: false = bez položky v legendě; NaN v x nebo y přeruší čáru (body mimo rozsah se tak jen vynechají);
// dots: body (kolečka o průměru `width`) místo čáry – fázové grafy a nelinearita
export interface Series { name: string; x: ArrayLike<number>; y: ArrayLike<number>; color: string; dash?: string; width?: number;
  legend?: boolean; dots?: boolean }

function ticks(lo: number, hi: number, n = 5): number[] {
  const span = hi - lo || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9 * span; v += step) out.push(+v.toPrecision(12));
  return out;
}

export function LineChart({ series, height = 220, xLabel, yLabel, logX, testid, xDomain, yDomain }: {
  series: Series[]; height?: number; xLabel?: string; yLabel?: string; logX?: boolean; testid?: string;
  xDomain?: [number, number]; yDomain?: [number, number];        // pevný rozsah os (v jednotkách dat, bez logX)
}) {
  const W = 720, H = height, L = 52, R = 10, Tm = 10, B = 28;
  const prep = useMemo(() => {
    const tx = (v: number) => (logX ? Math.log10(Math.max(v, 1e-12)) : v);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const s of series) for (let i = 0; i < s.x.length; i++) {
      const x = tx(s.x[i]), y = s.y[i];
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    if (xDomain) [x0, x1] = xDomain;
    if (yDomain) [y0, y1] = yDomain;
    if (!Number.isFinite(x0)) return null;
    if (!yDomain) {
      if (y1 - y0 < 1e-12) { y0 -= 1; y1 += 1; }
      const pad = 0.05 * (y1 - y0); y0 -= pad; y1 += pad;
    }
    const sx = (x: number) => L + ((tx(x) - x0) / (x1 - x0 || 1)) * (W - L - R);
    const sy = (y: number) => Tm + (1 - (y - y0) / (y1 - y0)) * (H - Tm - B);
    const paths = series.map((s) => {
      const n = s.x.length, step = Math.max(1, Math.floor(n / 1500));
      let d = "", pen = false;
      for (let i = 0; i < n; i += step) {
        const x = s.x[i], y = s.y[i];
        if (!Number.isFinite(tx(x)) || !Number.isFinite(y)) { pen = false; continue; }
        d += s.dots ? `M${sx(x).toFixed(1)},${sy(y).toFixed(1)}h0` : `${pen ? "L" : "M"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`;
        pen = true;
      }
      return d;
    });
    return { x0, x1, y0, y1, sx, sy, paths };
  }, [series, logX, H, xDomain, yDomain]);
  if (!prep) return null;
  const { x0, x1, y0, y1, sx, sy, paths } = prep;
  const xt = logX ? Array.from({ length: Math.floor(x1) - Math.ceil(x0) + 1 }, (_, i) => 10 ** (Math.ceil(x0) + i)) : ticks(x0, x1);
  return (
    <figure className="chart" data-testid={testid}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img">
        {ticks(y0, y1).map((v) => <g key={v}><line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} className="grid" />
          <text x={L - 4} y={sy(v) + 3} textAnchor="end">{+v.toPrecision(4)}</text></g>)}
        {xt.map((v) => <g key={v}><line x1={sx(v)} x2={sx(v)} y1={Tm} y2={H - B} className="grid" />
          <text x={sx(v)} y={H - B + 14} textAnchor="middle">{+v.toPrecision(4)}</text></g>)}
        {series.map((s, i) => <path key={i} d={paths[i]} fill="none" stroke={s.color} strokeWidth={s.width ?? (s.dots ? 4 : 1.6)}
          strokeDasharray={s.dash} strokeLinecap={s.dots ? "round" : undefined} vectorEffect="non-scaling-stroke" />)}
        {xLabel && <text x={W - R} y={H - 2} textAnchor="end" className="lab">{xLabel}</text>}
        {yLabel && <text x={4} y={Tm + 8} className="lab">{yLabel}</text>}
      </svg>
      <figcaption>{series.map((s, i) => s.legend !== false && <span key={i}><i style={{ background: s.color }} />{s.name}</span>)}</figcaption>
    </figure>
  );
}
