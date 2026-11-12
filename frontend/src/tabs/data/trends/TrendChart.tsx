// Trendy – panel grafu (canvas), časová osa a přehledový pruh. Společné pro všechny panely: zoom kolečkem, posun
// tažením, kurzory A / B (klik = A, Shift+klik = B, tažení čáry), osy Y podle veličiny nebo signálu.
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { fmtClock, fmtNum, niceTicks, panelAxes, stripUnit, type Axis, type Panel, type Series, type SigInfo } from "./model";

export const LEFT = 58, RIGHT = 58, PAD_T = 6, PAD_B = 6;
const FALLBACK = { text: "#1f2933", muted: "#52606d", soft: "#e5e9ef", line: "#c3ccd6" };

/** Hezký krok časové osy [s] pro rozpětí a počet dílů (1, 2, 5, 10, 15, 30 s; min; h; dny). */
export function timeStep(span: number, n: number): number {
  const raw = span / Math.max(1, n);
  const steps = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
    3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800];
  return steps.find((s) => s >= raw) ?? 604800 * Math.ceil(raw / 604800);
}

export function timeTicks(a: number, b: number, origin: string | null, n = 8): number[] {
  const step = timeStep(b - a, n);
  const base = origin ? Date.parse(origin.length > 19 ? origin : origin + "Z") / 1000 : 0;
  const out: number[] = [];
  for (let t = Math.ceil((base + a) / step) * step; t <= base + b + 1e-9 && out.length < 200; t += step) out.push(t - base);
  return out;
}

function palette(el: HTMLElement) {
  const cs = getComputedStyle(el);
  const g = (k: string, d: string) => cs.getPropertyValue(k).trim() || d;
  return { text: g("--pid-text", FALLBACK.text), muted: g("--pid-muted", FALLBACK.muted), soft: g("--pid-soft", FALLBACK.soft), line: g("--pid-ctl", FALLBACK.line) };
}

function useWidth(ref: React.RefObject<HTMLElement | null>) {
  const [w, setW] = useState(900);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(240, Math.round(el.clientWidth))));
    ro.observe(el);
    setW(Math.max(240, Math.round(el.clientWidth)));
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

function setupCanvas(cv: HTMLCanvasElement, w: number, h: number) {
  const r = window.devicePixelRatio || 1;
  cv.width = Math.round(w * r); cv.height = Math.round(h * r);
  cv.style.width = `${w}px`; cv.style.height = `${h}px`;
  const g = cv.getContext("2d")!;
  g.setTransform(r, 0, 0, r, 0, 0);
  g.clearRect(0, 0, w, h);
  return g;
}

export interface ChartCtx {
  view: [number, number]; full: [number, number]; origin: string | null;
  a: number | null; b: number | null;
  onView: (v: [number, number] | null) => void;
  onCursor: (which: "a" | "b", t: number) => void;
}

/** Zoom kolem bodu t (poměr f < 1 = přiblížit); okno zůstane v celém rozsahu. */
export function zoomView(view: [number, number], full: [number, number], f: number, t: number): [number, number] | null {
  const min = Math.max((full[1] - full[0]) * 1e-6, 1e-3);
  const span = Math.min(full[1] - full[0], Math.max(min, (view[1] - view[0]) * f));
  let lo = t - ((t - view[0]) / (view[1] - view[0])) * span;
  lo = Math.min(Math.max(lo, full[0]), full[1] - span);
  return span >= full[1] - full[0] - 1e-9 ? null : [lo, lo + span];
}

export function panView(view: [number, number], full: [number, number], dt: number): [number, number] {
  const span = view[1] - view[0];
  const lo = Math.min(Math.max(view[0] + dt, full[0]), full[1] - span);
  return [lo, lo + span];
}

export function TrendPanel({ panel, series, info, ctx, shared, height, onRemove }: {
  panel: Panel; series: Series[]; info: Map<string, SigInfo>; ctx: ChartCtx; shared: boolean; height: number;
  onRemove?: (ref: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const w = useWidth(box);
  const [view0, full, origin] = [ctx.view, ctx.full, ctx.origin];
  const axes = useMemo(() => panelAxes(series, info, shared, view0[0], view0[1]), [series, info, shared, view0]);
    const plot = { x0: LEFT, x1: w - RIGHT, y0: PAD_T, y1: height - PAD_B };
  const X = useCallback((t: number) => plot.x0 + ((t - view0[0]) / (view0[1] - view0[0])) * (plot.x1 - plot.x0), [plot.x0, plot.x1, view0]);
  const T = (x: number) => view0[0] + ((x - plot.x0) / (plot.x1 - plot.x0)) * (view0[1] - view0[0]);
  const axOf = useMemo(() => {
    const m = new Map<string, Axis>();
    axes.forEach((a) => a.refs.forEach((r) => m.set(r, a)));
    return m;
  }, [axes]);

  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    const g = setupCanvas(c, w, height);
    const P = palette(c);
    const Y = (a: Axis, v: number) => plot.y1 - ((v - a.lo) / (a.hi - a.lo)) * (plot.y1 - plot.y0);
    g.lineWidth = 1;
    // svislá mřížka
    g.strokeStyle = P.soft;
    for (const t of timeTicks(view0[0], view0[1], origin, Math.max(3, Math.round((plot.x1 - plot.x0) / 110)))) {
      const x = Math.round(X(t)) + 0.5;
      g.beginPath(); g.moveTo(x, plot.y0); g.lineTo(x, plot.y1); g.stroke();
    }
    axes.forEach((a, k) => {
      const col = k < 2 ? (info.get(a.refs[0])?.color ?? P.muted) : P.muted;
      const ticks = niceTicks(a.lo, a.hi, 4);
      g.font = "11px 'IBM Plex Sans', sans-serif"; g.textBaseline = "middle";
      for (const v of ticks) {
        const y = Math.round(Y(a, v)) + 0.5;
        if (k === 0) { g.strokeStyle = P.soft; g.beginPath(); g.moveTo(plot.x0, y); g.lineTo(plot.x1, y); g.stroke(); }
        if (k < 2) {
          g.fillStyle = col; g.textAlign = k === 0 ? "right" : "left";
          g.fillText(fmtNum(v, 4), k === 0 ? plot.x0 - 6 : plot.x1 + 6, y);
        }
      }
    });
    g.strokeStyle = P.line; g.strokeRect(plot.x0 + 0.5, plot.y0 + 0.5, plot.x1 - plot.x0, plot.y1 - plot.y0);
    // průběhy
    g.save();
    g.beginPath(); g.rect(plot.x0, plot.y0, plot.x1 - plot.x0, plot.y1 - plot.y0); g.clip();
    for (const s of series) {
      const a = axOf.get(s.ref), i = info.get(s.ref);
      if (!a || !s.t.length) continue;
      g.strokeStyle = i?.color ?? P.text; g.lineWidth = i?.role === "SP" ? 1.6 : 1.8; g.setLineDash(i?.dash ? i.dash.split(" ").map(Number) : []);
      g.beginPath();
      let pen = false;
      const gap = Math.max((view0[1] - view0[0]) / 20, 1e-9);
      for (let k = 0; k < s.t.length; k++) {
        if (s.t[k] < view0[0] - gap || s.t[k] > view0[1] + gap) { pen = false; continue; }
        const x = X(s.t[k]), y = Y(a, s.v[k]);
        if (!pen) { g.moveTo(x, y); pen = true; } else g.lineTo(x, y);
      }
      g.stroke();
    }
    g.restore(); g.setLineDash([]);
    // kurzory
    for (const [t, dash] of [[ctx.a, false], [ctx.b, true]] as const) {
      if (t === null || t < view0[0] || t > view0[1]) continue;
      const x = Math.round(X(t)) + 0.5;
      g.strokeStyle = P.text; g.lineWidth = 1.5; g.setLineDash(dash ? [5, 3] : []);
      g.beginPath(); g.moveTo(x, plot.y0); g.lineTo(x, plot.y1); g.stroke();
    }
    g.setLineDash([]);
  }, [axes, axOf, series, info, view0, w, height, ctx.a, ctx.b, origin, X, plot.x0, plot.x1, plot.y0, plot.y1]);

  // ovládání: kolečko = zoom, tažení = posun nebo tažení kurzoru, klik = A, Shift+klik = B
  const drag = useRef<{ x: number; view: [number, number]; cur: "a" | "b" | null; moved: boolean } | null>(null);
  const near = (x: number): "a" | "b" | null => {
    for (const k of ["a", "b"] as const) { const t = ctx[k]; if (t !== null && Math.abs(X(t) - x) <= 6) return k; }
    return null;
  };
  const xOf = (e: { clientX: number }) => e.clientX - cv.current!.getBoundingClientRect().left;
  const down = (e: RPointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { x: xOf(e), view: view0, cur: near(xOf(e)), moved: false };
  };
  const move = (e: RPointerEvent) => {
    const x = xOf(e), d = drag.current;
    if (!d) { cv.current!.style.cursor = near(x) ? "ew-resize" : "crosshair"; return; }
    if (Math.abs(x - d.x) > 3) d.moved = true;
    if (!d.moved) return;
    if (d.cur) { ctx.onCursor(d.cur, Math.min(Math.max(T(x), full[0]), full[1])); return; }
    const dt = -((x - d.x) / (plot.x1 - plot.x0)) * (d.view[1] - d.view[0]);
    ctx.onView(panView(d.view, full, dt));
  };
  const up = (e: RPointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved && !d.cur) ctx.onCursor(e.shiftKey ? "b" : "a", T(xOf(e)));
  };
  useEffect(() => {                       // kolečko musí být nepasivní (preventDefault)
    const c = cv.current;
    if (!c) return;
    const f = (e: WheelEvent) => {
      e.preventDefault();
      const x = e.clientX - c.getBoundingClientRect().left;
      ctx.onView(zoomView(view0, full, e.deltaY > 0 ? 1.25 : 0.8, view0[0] + ((x - plot.x0) / (plot.x1 - plot.x0)) * (view0[1] - view0[0])));
    };
    c.addEventListener("wheel", f, { passive: false });
    return () => c.removeEventListener("wheel", f);
  });

  const subtitle = useMemo(() => {
    const by = new Map<string, string[]>();
    for (const r of panel.refs) {
      const i = info.get(r);
      const u = i?.unit ?? "";
      by.set(u, [...(by.get(u) ?? []), stripUnit(i?.label ?? r)]);
    }
    return [...by.entries()].map(([u, l]) => `${l.join(", ")}${u ? ` [${u}]` : ""}`).join(" · ");
  }, [panel.refs, info]);
  const pts = series.reduce((n, s) => n + s.t.length, 0);

  return (
    <div className="trd-panel" data-testid="trd-panel" data-title={panel.title} data-refs={panel.refs.join(",")} data-points={pts}>
      <div className="trd-phead">
        <span className="trd-ptitle">{panel.title}</span>
        <span className="trd-psub">{subtitle}</span>
        <span className="trd-legend">
          {panel.refs.map((r) => {
            const i = info.get(r);
            return (
              <span key={r} className="trd-leg" title={r}>
                <span className="trd-sw" style={{ borderTopColor: i?.color, borderTopStyle: i?.dash ? "dashed" : "solid" }} />
                {i?.role === "DV" || !i?.role ? i?.column ?? r : i.label}
                {onRemove && <button type="button" className="trd-x" aria-label={`${r} ×`} title={`− ${r}`} onClick={() => onRemove(r)}>×</button>}
              </span>
            );
          })}
        </span>
      </div>
      <div ref={box} className="trd-cbox">
        <canvas ref={cv} data-testid="trd-canvas" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { drag.current = null; }} />
      </div>
    </div>
  );
}

/** Časová osa pod panely se značkami kurzorů A / B (hodiny, je-li zdroj má; jinak sekundy). */
export function TimeAxis({ ctx }: { ctx: ChartCtx }) {
  const box = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const w = useWidth(box);
  const [a, b] = ctx.view;
  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    const g = setupCanvas(c, w, 38);
    const P = palette(c);
    const x0 = LEFT, x1 = w - RIGHT;
    const X = (t: number) => x0 + ((t - a) / (b - a)) * (x1 - x0);
    g.font = "11px 'IBM Plex Sans', sans-serif"; g.fillStyle = P.muted; g.textAlign = "center"; g.textBaseline = "top";
    const step = timeStep(b - a, Math.max(3, Math.round((x1 - x0) / 110)));
    const day = ctx.origin && b - a > 86400;
    for (const t of timeTicks(a, b, ctx.origin, Math.max(3, Math.round((x1 - x0) / 110)))) g.fillText(fmtClock(ctx.origin, t, !!day, step < 60), X(t), 2);
    g.textBaseline = "bottom"; g.fillStyle = P.text; g.font = "600 11px 'IBM Plex Sans', sans-serif";
    for (const [k, t] of [["A", ctx.a], ["B", ctx.b]] as const) {
      if (t === null || t < a || t > b) continue;
      g.fillText(`${k} ${fmtClock(ctx.origin, t, false, true)}`, Math.min(Math.max(X(t), x0 + 40), x1 - 40), 37);
    }
  }, [w, a, b, ctx.a, ctx.b, ctx.origin]);
  return <div ref={box} className="trd-axis"><canvas ref={cv} data-testid="trd-axis" /></div>;
}

/** Přehledový pruh celého rozsahu s oknem zoomu: tažením okna posunete, tažením okrajů změníte rozsah. */
export function Navigator({ series, info, ctx, title }: { series: Series[]; info: Map<string, SigInfo>; ctx: ChartCtx; title: string }) {
  const box = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const w = useWidth(box);
  const [f0, f1] = ctx.full;
  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    const g = setupCanvas(c, w, 38);
    for (const s of series.slice(0, 3)) {
      let lo = Infinity, hi = -Infinity;
      for (let k = 0; k < s.v.length; k++) { lo = Math.min(lo, s.v[k]); hi = Math.max(hi, s.v[k]); }
      if (!(hi > lo)) continue;
      g.strokeStyle = info.get(s.ref)?.color ?? "#64748b"; g.lineWidth = 1;
      g.beginPath();
      for (let k = 0; k < s.t.length; k++) {
        const x = ((s.t[k] - f0) / (f1 - f0)) * w, y = 35 - ((s.v[k] - lo) / (hi - lo)) * 32;
        if (k) g.lineTo(x, y); else g.moveTo(x, y);
      }
      g.stroke();
    }
  }, [series, info, w, f0, f1]);
  const [a, b] = ctx.view;
  const pct = (t: number) => `${((t - f0) / (f1 - f0)) * 100}%`;
  const drag = useRef<{ x: number; view: [number, number]; mode: "move" | "l" | "r" } | null>(null);
  const start = (mode: "move" | "l" | "r", e: RPointerEvent) => {
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, view: ctx.view, mode };
  };
  const move = (e: RPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dt = ((e.clientX - d.x) / (box.current?.clientWidth || 1)) * (f1 - f0);
    const min = (f1 - f0) * 1e-4;
    if (d.mode === "move") ctx.onView(panView(d.view, ctx.full, dt));
    else if (d.mode === "l") ctx.onView([Math.max(f0, Math.min(d.view[0] + dt, d.view[1] - min)), d.view[1]]);
    else ctx.onView([d.view[0], Math.min(f1, Math.max(d.view[1] + dt, d.view[0] + min))]);
  };
  const end = () => { drag.current = null; };
  const click = (e: React.MouseEvent) => {                      // klik mimo okno vycentruje okno na toto místo
    if (e.target !== e.currentTarget && (e.target as HTMLElement).tagName !== "CANVAS") return;
    const r = box.current!.getBoundingClientRect();
    const t = f0 + ((e.clientX - r.left) / r.width) * (f1 - f0);
    ctx.onView(panView(ctx.view, ctx.full, t - (a + b) / 2));
  };
  const zoomed = a > f0 + 1e-9 || b < f1 - 1e-9;
  return (
    <div ref={box} className="trd-nav" data-testid="trd-nav" onClick={click}>
      <canvas ref={cv} />
      <div className="trd-nshade" style={{ left: 0, width: pct(a) }} />
      <div className="trd-nshade" style={{ left: pct(b), right: 0 }} />
      <div className="trd-nwin" data-testid="trd-nwin" title={title} style={{ left: pct(a), width: `${((b - a) / (f1 - f0)) * 100}%` }}
        data-zoomed={zoomed} onPointerDown={(e) => start("move", e)} onPointerMove={move} onPointerUp={end}>
        <span className="trd-nh l" onPointerDown={(e) => start("l", e)} onPointerMove={move} onPointerUp={end} />
        <span className="trd-nh r" onPointerDown={(e) => start("r", e)} onPointerMove={move} onPointerUp={end} />
      </div>
    </div>
  );
}
