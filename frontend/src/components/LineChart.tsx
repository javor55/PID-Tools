// Jednoduchý graf průběhů (SVG) – odezvy ladění, frekvenční charakteristiky. Řady se zředí na ~1500 bodů.
import { useEffect, useMemo, useRef, useState } from "react";
import { useUi } from "../store";
import { ChartMenu, Readout, useChartTexts, type Geo } from "./LineChartTools";

// legend: false = bez položky v legendě; NaN v x nebo y přeruší čáru (body mimo rozsah se tak jen vynechají);
// dots: body (kolečka o průměru `width`) místo čáry – fázové grafy a nelinearita
export interface Series { name: string; x: ArrayLike<number>; y: ArrayLike<number>; color: string; dash?: string; width?: number;
  legend?: boolean; dots?: boolean }

function ticks(lo: number, hi: number, n = 5): number[] {
  const span = hi - lo || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9 * span; v += step)
    out.push(Math.abs(v) < step * 1e-6 ? 0 : +v.toPrecision(12));     // nula místo zbytku zaokrouhlení (−7.8e-17)
  return out;
}

/** Podbarvené pásmo osy x (úseky dat, doba řízení omezujícím regulátorem); label = číslo / text uprostřed pásma. */
export interface Band { from: number; to: number; color?: string; label?: string }

export function LineChart({ series, height: heightProp, xLabel, yLabel, logX, testid, xDomain, yDomain, bands, title, tools = true }: {
  series: Series[]; height?: number; xLabel?: string; yLabel?: string; logX?: boolean; testid?: string;
  xDomain?: [number, number]; yDomain?: [number, number];        // pevný rozsah os (v jednotkách dat, bez logX)
  bands?: Band[];                                                // svislá pásma (bez logX)
  title?: string;                                                // přístupný název grafu (výchozí: názvy řad a popisky os)
  tools?: boolean;                                               // odečet hodnot, nabídka exportu a skrývání řad v legendě (výchozí zapnuto)
}) {
  const { T, dec } = useChartTexts();
  const svgRef = useRef<SVGSVGElement>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());    // skryté řady (klíč = pořadí + název); jen stav komponenty
  const hkey = (s: Series, i: number) => `${i}:${s.name}`;
  // řady v odečtu a exportu: s položkou v legendě a nepřeskrtnuté
  const shown = useMemo(() => series.filter((s, i) => s.legend !== false && !hidden.has(hkey(s, i))), [series, hidden]);
  const chartH = useUi((st) => st.chartH);
  // šířka podle skutečného místa (výška zůstane zadaná v px – graf se neroztahuje do výšky se šířkou okna)
  const box = useRef<HTMLElement>(null);
  const [W, setW] = useState(720);
  const H = heightProp ?? chartH, L = 52, R = 10, Tm = yLabel ? 20 : 10, B = 28;   // popisek osy Y nad grafem, ne přes čísla
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
  }, [series, logX, H, W, Tm, xDomain, yDomain]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => { const w = Math.round(el.clientWidth); if (w > 100) setW(w); });
    ro.observe(el);
    return () => ro.disconnect();
  }, [!prep]);              // eslint-disable-line react-hooks/exhaustive-deps
  if (!prep) return null;
  const { x0, x1, y0, y1, sx, sy, paths } = prep;
  const geo: Geo = { W, H, L, R, Tm, B, x0, x1, sx };
  const xt = logX ? Array.from({ length: Math.floor(x1) - Math.ceil(x0) + 1 }, (_, i) => 10 ** (Math.ceil(x0) + i)) : ticks(x0, x1);
  return (
    <figure className="chart" data-testid={testid} ref={box} tabIndex={tools ? 0 : undefined}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" role="img"
        aria-label={title ?? [...series.filter((s) => s.legend !== false).map((s) => s.name), yLabel, xLabel].filter(Boolean).join(", ")}>
        {!logX && bands?.map((b, i) => {
          const a = Math.max(L, sx(b.from)), z = Math.min(W - R, sx(b.to));
          return z > a ? (
            <g key={i} data-testid={testid ? `${testid}-band-${i}` : undefined}>
              <rect x={a} y={Tm} width={z - a} height={H - Tm - B} fill={b.color ?? "var(--pid-accent)"} opacity={0.16} />
              {b.label && <text x={(a + z) / 2} y={Tm + 12} textAnchor="middle" className="lab">{b.label}</text>}
            </g>) : null;
        })}
        {ticks(y0, y1).map((v) => <g key={v}><line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} className="grid" />
          <text x={L - 4} y={sy(v) + 3} textAnchor="end">{+v.toPrecision(4)}</text></g>)}
        {xt.map((v) => <g key={v}><line x1={sx(v)} x2={sx(v)} y1={Tm} y2={H - B} className="grid" />
          <text x={sx(v)} y={H - B + 14} textAnchor="middle">{+v.toPrecision(4)}</text></g>)}
        {series.map((s, i) => !hidden.has(hkey(s, i)) && <path key={i} d={paths[i]} fill="none" stroke={s.color} strokeWidth={s.width ?? (s.dots ? 4 : 1.6)}
          strokeDasharray={s.dash} strokeLinecap={s.dots ? "round" : undefined} vectorEffect="non-scaling-stroke" />)}
        {xLabel && <text x={W - R} y={H - 2} textAnchor="end" className="lab">{xLabel}</text>}
        {yLabel && <text x={4} y={12} className="lab">{yLabel}</text>}
      </svg>
      {tools && <Readout host={box} svgRef={svgRef} geo={geo} logX={logX} series={shown} xName={xLabel ?? T("lc_x")} dec={dec} T={T} />}
      {tools && <ChartMenu series={shown} legend={shown.map((s) => ({ name: s.name, color: s.color }))} xName={xLabel ?? T("lc_x")} dec={dec}
        name={testid ?? "chart"} svgRef={svgRef} W={W} H={H} T={T} />}
      <figcaption>{series.map((s, i) => s.legend !== false && (tools
        ? <span key={i} className={hidden.has(hkey(s, i)) ? "off" : undefined}>
          <button type="button" aria-pressed={!hidden.has(hkey(s, i))} title={T("lc_legend_toggle")} data-testid={testid ? `${testid}-leg-${i}` : "lc-leg"}
            onClick={() => setHidden((h) => { const n = new Set(h); const k = hkey(s, i); if (n.has(k)) n.delete(k); else n.add(k); return n; })}>
            <i style={{ background: s.color }} />{s.name}</button></span>
        : <span key={i}><i style={{ background: s.color }} />{s.name}</span>))}</figcaption>
    </figure>
  );
}
