// Sloupcový graf korelací (ACF / CCF reziduí) s mezemi ±bound; sloupce mimo mez jsou červeně (jako na desktopu).
export function BarChart({ lags, values, bound, xLabel, testid, height = 180 }: {
  lags: number[]; values: number[]; bound: number; xLabel?: string; testid?: string; height?: number;
}) {
  const W = 720, H = height, L = 40, R = 10, Tm = 10, B = 28;
  const lim = Math.max(bound * 1.3, ...values.map((v) => Math.abs(v)), 0.05);
  const x0 = Math.min(...lags), x1 = Math.max(...lags);
  const step = lags.length > 1 ? (x1 - x0) / (lags.length - 1) : 1;
  const sx = (x: number) => L + ((x - x0 + step) / (x1 - x0 + 2 * step || 1)) * (W - L - R);
  const sy = (y: number) => Tm + (1 - (y + lim) / (2 * lim)) * (H - Tm - B);
  const bw = Math.max(1, 0.7 * ((W - L - R) / (lags.length + 1)));
  const xt = [0, 0.25, 0.5, 0.75, 1].map((f) => x0 + f * (x1 - x0));
  return (
    <figure className="chart" data-testid={testid} data-n={values.length} data-bound={bound}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img">
        {[-lim, -lim / 2, 0, lim / 2, lim].map((v) => <g key={v}><line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} className="grid" />
          <text x={L - 4} y={sy(v) + 3} textAnchor="end">{+v.toPrecision(2)}</text></g>)}
        {xt.map((v) => <text key={v} x={sx(v)} y={H - B + 14} textAnchor="middle">{+v.toPrecision(3)}</text>)}
        {values.map((v, i) => (
          <rect key={i} data-bad={Math.abs(v) > bound ? 1 : 0} x={sx(lags[i]) - bw / 2} width={bw}
            y={Math.min(sy(0), sy(v))} height={Math.abs(sy(v) - sy(0))} fill={Math.abs(v) > bound ? "#dc2626" : "#1f5fa8"} />))}
        {[bound, -bound].map((b) => <line key={b} className="bound" x1={L} x2={W - R} y1={sy(b)} y2={sy(b)}
          stroke="#94a3b8" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />)}
        {xLabel && <text x={W - R} y={H - 2} textAnchor="end" className="lab">{xLabel}</text>}
      </svg>
    </figure>
  );
}
