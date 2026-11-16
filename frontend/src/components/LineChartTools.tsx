// Nástroje grafu `LineChart` (FEATURE-004): odečtová vrstva (svislá čára + plovoucí tabulka) a nabídka exportu.
// Odečet je samostatná komponenta se vlastním stavem – pohyb ukazatele tak nepřekresluje SVG grafu ani cesty řad.
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { decOf } from "../i18n";
import { copyText } from "../lib/clipboard";
import { format } from "../lib/format";
import { queryClient } from "../queryClient";
import { useUi } from "../store";
import { toastError, useToasts } from "./Toasts";
import { downloadBlob, nearestIndex, showNum, svgToPngBlob, toCsv, toTsv, unionRows, xRange, type ExportTable, type LegendItem } from "./chartTools";

/** Řada viditelná v odečtu a exportu (bez položek s `legend: false`, bez skrytých). */
export interface ShownSeries { name: string; x: ArrayLike<number>; y: ArrayLike<number>; color: string }

/** Rozměry grafu: viewBox W × H, okraje L/R/Tm/B, rozsah osy x (u logX v logaritmu) a převod x → px. */
export interface Geo { W: number; H: number; L: number; R: number; Tm: number; B: number; x0: number; x1: number; sx: (x: number) => number }

type T = (key: string, args?: Record<string, unknown>) => string;

/**
 * Texty a desetinný oddělovač pro graf. Čte stejný dotaz jako `useT` / `useDec`, ale s pevným `queryClient` aplikace,
 * takže `LineChart` jde vykreslit i mimo `QueryClientProvider` (stávající testy a malé ukázky grafu).
 */
export function useChartTexts(): { T: T; dec: string } {
  const lang = useUi((st) => st.lang);
  const texts = useQuery({ queryKey: ["i18n", lang], queryFn: () => api.texts(lang), staleTime: Infinity }, queryClient).data;
  return { T: (key, args) => format(texts?.[key] ?? key, args), dec: decOf(lang, texts) };
}

export function Readout({ host, svgRef, geo, logX, series, xName, dec, T }: {
  host: RefObject<HTMLElement | null>; svgRef: RefObject<SVGSVGElement | null>; geo: Geo; logX?: boolean;
  series: ShownSeries[]; xName: string; dec: string; T: T;
}) {
  const [hover, setHover] = useState<number | null>(null);     // x (v datech) vzorku pod ukazatelem
  const [pins, setPins] = useState<number[]>([]);              // připíchnuté čáry A, B (x v datech)
  const ref = series.find((s) => s.x.length > 0);              // první viditelná řada určuje krok šipek a polohu čáry
  const ranges = useMemo(() => series.map((s) => xRange(s.x)), [series]);
  const live = useRef({ geo, logX, ref, pins });                // poslední hodnoty pro posluchače (neváží se znovu při každém pohybu)
  useEffect(() => { live.current = { geo, logX, ref, pins }; });     // po každém renderu

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let raf = 0, last: [number, number, EventTarget | null] | null = null;
    // poloha ukazatele → x nejbližšího vzorku první řady; null mimo plochu grafu nebo mimo SVG
    const snap = (cx: number, cy: number, target: EventTarget | null): number | null => {
      const { geo: g, logX: lg, ref: r } = live.current;
      const svg = svgRef.current;
      if (!svg || !r || !(target instanceof Node) || !svg.contains(target)) return null;
      const b = svg.getBoundingClientRect();
      if (!b.width || !b.height) return null;
      const vx = ((cx - b.left) * g.W) / b.width, vy = ((cy - b.top) * g.H) / b.height;
      if (vx < g.L || vx > g.W - g.R || vy < g.Tm || vy > g.H - g.B) return null;
      const t = g.x0 + ((vx - g.L) / (g.W - g.L - g.R)) * (g.x1 - g.x0);
      const i = nearestIndex(r.x, lg ? 10 ** t : t, lg);
      return i < 0 ? null : r.x[i];
    };
    const onMove = (e: PointerEvent) => {
      last = [e.clientX, e.clientY, e.target];
      if (raf) return;
      raf = requestAnimationFrame(() => {                       // nejvýš jeden přepočet na snímek
        raf = 0;
        if (last) setHover((h) => { const v = snap(last![0], last![1], last![2]); return v === h ? h : v; });
      });
    };
    const onLeave = () => { last = null; if (raf) { cancelAnimationFrame(raf); raf = 0; } setHover(null); };
    const onClick = (e: MouseEvent) => {
      const v = snap(e.clientX, e.clientY, e.target);
      if (v === null) return;
      setPins((p) => (p.length >= 2 ? [v] : [...p, v]));        // třetí klik začíná znovu
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setPins([]); setHover(null); return; }
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const { ref: r, pins: pn } = live.current;
      if (!r || !pn.length) return;
      e.preventDefault();
      const dir = e.key === "ArrowLeft" ? -1 : 1;
      let i = nearestIndex(r.x, pn[pn.length - 1], live.current.logX);
      if (i < 0) return;
      for (let j = i + dir; j >= 0 && j < r.x.length; j += dir) if (Number.isFinite(r.x[j])) { i = j; break; }
      const v = r.x[i];
      setPins((p) => [...p.slice(0, -1), v]);
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    el.addEventListener("click", onClick);
    el.addEventListener("keydown", onKey);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("click", onClick);
      el.removeEventListener("keydown", onKey);
    };
  }, [host, svgRef]);

  const pts = pins.length < 2 && hover !== null ? [...pins, hover] : pins;
  if (!pts.length || !ref) return null;
  const at = (s: ShownSeries, k: number, x: number): number | null => {      // hodnota řady v x (jen v rozsahu její osy x)
    const r = ranges[k];
    if (!r || x < r[0] || x > r[1]) return null;
    const i = nearestIndex(s.x, x, logX);
    return i >= 0 && Number.isFinite(s.y[i]) ? s.y[i] : null;
  };
  const rows = series.map((s, k) => ({ s, k, v: pts.map((x) => at(s, k, x)) }));
  const two = pts.length === 2;
  const dx = two ? pts[1] - pts[0] : null;
  const dif = (v: (number | null)[]) => (two && v[0] !== null && v[1] !== null ? v[1] - v[0] : null);
  const active = pts[pts.length - 1];
  const flip = geo.sx(active) > geo.W * 0.55;
  const pct = (x: number) => `${(geo.sx(x) / geo.W) * 100}%`;
  const lineStyle = (x: number) => ({ left: pct(x), top: geo.Tm, height: geo.H - geo.Tm - geo.B });
  const labels = [T("lc_pin_a"), T("lc_pin_b")];
  return (
    <div className="lc-layer" style={{ height: geo.H }} data-testid="lc-layer">
      {pts.map((x, i) => <div key={i} className={`lc-line${i < pins.length ? " pinned" : ""}`} style={lineStyle(x)}
        data-testid={i < pins.length ? `lc-pin-${i}` : "lc-hover"} />)}
      <div className={`lc-readout${flip ? " flip" : ""}`} data-testid="lc-readout"
        style={{ left: pct(active), top: geo.Tm + 4, maxHeight: geo.H - geo.Tm - geo.B - 8 }}>
        <table>
          {(two || pins.length > 0) && <thead><tr><th />{pts.map((_, i) => <th key={i}>{labels[i]}</th>)}{two && <th>{T("lc_delta")}</th>}</tr></thead>}
          <tbody>
            <tr><th>{xName}</th>{pts.map((x, i) => <td key={i} data-testid={`lc-x-${i}`}>{showNum(x, dec, 5)}</td>)}
              {two && <td data-testid="lc-dx" title={T("lc_dx")}>{showNum(dx, dec, 5)}</td>}</tr>
            {rows.map(({ s, k, v }) => (
              <tr key={k} data-testid={`lc-row-${k}`}>
                <th><i style={{ background: s.color }} />{s.name}</th>
                {v.map((y, i) => <td key={i} data-testid={`lc-val-${k}-${i}`}>{showNum(y, dec)}</td>)}
                {two && <td data-testid={`lc-dy-${k}`} title={T("lc_dy")}>{showNum(dif(v), dec)}</td>}
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Nabídka „⋯“ v rohu grafu: kopie TSV, uložení CSV a PNG. Tabulka exportu se sestaví až při volbě položky. */
export function ChartMenu({ series, legend, xName, dec, name, svgRef, W, H, T }: {
  series: ShownSeries[]; legend: LegendItem[]; xName: string; dec: string; name: string;
  svgRef: RefObject<SVGSVGElement | null>; W: number; H: number; T: T;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    wrap.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  const table = (): ExportTable => unionRows(series, xName);
  const close = () => { setOpen(false); btn.current?.focus(); };
  const run = (f: () => Promise<void> | void) => {
    setOpen(false);
    Promise.resolve().then(f).catch(toastError);
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); return; }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = Array.from(wrap.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const i = items.indexOf(document.activeElement as HTMLElement);
    items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
  };
  return (
    <div className="lc-menu-wrap" ref={wrap} onKeyDown={onKey}>
      <button type="button" className="lc-menu-btn" ref={btn} data-testid="lc-menu" aria-haspopup="menu" aria-expanded={open}
        aria-label={T("lc_menu")} title={T("lc_menu")} onClick={() => setOpen((o) => !o)} />
      {open && (
        <div className="lc-menu" role="menu" aria-label={T("lc_menu")} data-testid="lc-menu-list">
          <button type="button" role="menuitem" data-testid="lc-copy" onClick={() => run(async () => {
            await copyText(toTsv(table(), dec));
            useToasts.getState().push({ kind: "ok", text: T("lc_copied") });
          })}>{T("lc_copy_tsv")}</button>
          <button type="button" role="menuitem" data-testid="lc-csv" onClick={() => run(() => {
            downloadBlob(new Blob([toCsv(table())], { type: "text/csv;charset=utf-8" }), `${name}.csv`);
          })}>{T("lc_save_csv")}</button>
          <button type="button" role="menuitem" data-testid="lc-png" onClick={() => run(async () => {
            const svg = svgRef.current;
            if (!svg) throw new Error("PNG: no chart");
            downloadBlob(await svgToPngBlob(svg, W, H, legend), `${name}.png`);
          })}>{T("lc_save_png")}</button>
        </div>)}
    </div>
  );
}
