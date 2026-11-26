// Graf záložky Model › Identifikace: prohlížeč záznamu (viewer.js) s vrstvou úseků identifikace (viewer_spans.js)
// a přepínači průběhu modelu (viewer_model.js). Výchozí rozložení: panel 1 = PV + SP + model, panel 2 = MV, pak panel na
// každou poruchu; uživatel může přidat další signály ze záznamu. Rozložení se ukládá do nastavení smyčky „mview“
// (odděleně od „dview“ Trendů). Data: mřížka smyčky (/signals?source=grid) + průběhy modelu (/model/curves) sloučené do
// jednoho balíku v paměti; úseky a režim úseků přicházejí z API (okno /windows, nastavení win_mode) a ven jdou přes onWins.
import { useMemo, useRef } from "react";
import type { components } from "../api/schema";
import { mergePacks, series } from "../api/signals";
import type { ViewerData, ViewerSig, ViewerSpans } from "../legacy/viewer.js";
import { runs, timeUnit } from "../lib/series";
import { DIST_STYLE, MV_STYLE, windowFits } from "../tabs/modelConst";
import { clockOf, type Pack, uniqueNames, useViewerEnv, useViewerMount, viewerTxt, withRecordSignals } from "./viewerMount";

type ModelState = components["schemas"]["ModelState"];
type WindowsInfo = components["schemas"]["WindowsInfo"];

export interface WinsOut { mode: string; wins: Record<string, [number, number][]>; common: [number, number] }
export interface ModelChartProps {
  ws: components["schemas"]["WorkspaceInfo"] | undefined;
  grid: Pack | undefined; curves: Pack | undefined;
  raw: Pack | undefined;                                   // všechny signály záznamu (ostatní lze přidat do grafu)
  windows: WindowsInfo | undefined; model: ModelState | undefined;
  winMode: "common" | "inputs";
  units: { pv: string; mv: string };                       // jednotky PV a MV z nastavení smyčky
  layout: string | null;                                   // uložené rozložení (nastavení „mview“)
  onWins: (w: WinsOut) => void;
  onMode: (mode: string) => void;
  onLayout: (layout: string) => void;
}

const CURVES = ["model", "full", "model_mv", "model_dv", "residual"];
const RESERVED = new Set(["pv", "mv", "sp", "valid", ...CURVES]);
const SPAN_TXT = ["mode", "h_mode", "common", "inputs", "zoom_win", "win", "drag_win", "start", "end", "zoom_one", "del", "add"];
const MODEL_TXT = ["m_all", "m_mv", "m_dv", "r_win", "r_full", "resid"];

export function ModelChart({ ws, grid, curves, raw, windows, model, winMode, units, layout, onWins, onMode, onLayout }: ModelChartProps) {
  const { T, texts, dark, pal, col, dec } = useViewerEnv();
  const box = useRef<HTMLDivElement>(null);

  // balík v paměti: mřížka + průběhy modelu (bez duplicit pv / mv); názvy signálů podle smyčky
  const built = useMemo(() => {
    if (!ws?.has_data || !grid) return null;
    const base: Pack = curves ? mergePacks(grid, curves, CURVES) : { meta: grid.meta, blob: grid.blob };
    const { merged, extra } = withRecordSignals(base, raw, ws, RESERVED);   // názvy balíku mřížky / modelu nesmí kolidovat
    const uniq = uniqueNames();
    const disp: Record<string, string> = {};
    disp.pv = uniq(ws.pv ?? "PV"); disp.mv = uniq(ws.mv ?? "MV");
    if (ws.sp) disp.sp = uniq(ws.sp);
    (ws.dists ?? []).forEach((d, j) => { disp[`d${j}`] = uniq(d); });
    disp.full = uniq(T("mw_sig_model")); disp.model = uniq(T("mw_sig_model_win"));
    disp.model_mv = uniq(T("mw_sig_mv")); disp.model_dv = uniq(T("mw_sig_dv")); disp.residual = uniq(T("mw_sig_resid"));
    for (const n of extra) disp[n] = uniq(n);
    const has = (k: string) => merged.meta.sigs.some((s) => s.name === k);
    // „celý model“ je průběh na celém záznamu (full); jen v úsecích (model) je druhá volba; bez full je celým modelem model
    const all = has("full") ? "full" : has("model") ? "model" : null;
    const win = all === "full" && has("model") ? "model" : null;
    return { merged, disp, all, win, has };
  }, [ws, grid, curves, raw, T]);

  const spans = useMemo<ViewerSpans | null>(() => {
    if (!ws?.has_data || !grid || !windows) return null;
    const get = (n: string) => series(grid.meta, grid.blob, n);
    const t = get("pv")?.t;
    if (!t?.length) return null;
    const Tend = t[t.length - 1], Ts = ws.Ts ?? 1;
    const sel = model?.results.find((x) => x.code === model.selected);
    const wf = winMode === "inputs" && sel?.method === "win" && curves ? windowFits(windows.wins, sel.window_fits, Ts) : {};
    const ids = ["MV", ...(ws.dists ?? [])];                 // klíče úseků: MV a názvy poruch (jako v API /windows)
    const inputs = ids.map((id, k) => {
      const sty = k === 0 ? MV_STYLE : DIST_STYLE[(k - 1) % 4];
      const w = windows.wins?.[id] ?? [];
      const nm = k === 0 ? ws.mv ?? "MV" : (ws.dists ?? [])[k - 1];
      return { id, sig: "", wins: w, fits: wf[id] ?? [], wcol: sty[0], wtx: sty[1], wbg: sty[2], wbd: sty[3],
        badge: winMode === "inputs" ? T("mw_badge", { k: k + 1, n: w.length }) : null,
        note: winMode === "inputs" ? T("mw_note_in") : null, nm };
    });
    const valid = get("valid");
    const excl = winMode === "inputs" && valid ? runs(Array.from(valid.v, (x) => (x > 0.5 ? 0 : 1)), t) : [];
    return {
      mode: winMode, common: ws.rng ?? [0, Tend], step: Ts, unit: timeUnit(Tend),
      ccol: MV_STYLE[0], cbd: MV_STYLE[1], ctx: MV_STYLE[1], cbg: MV_STYLE[2],
      inputs: inputs.map(({ nm, ...r }) => ({ ...r, sig: nm })), excl: excl as number[][],
      txt: Object.fromEntries(SPAN_TXT.map((k) => [k, T("mw_" + k)])),
    };
  }, [ws, grid, curves, windows, model, winMode, T]);

  const data = useMemo<Omit<ViewerData, "sig"> | null>(() => {
    if (!built || !spans || !ws || !texts) return null;
    const { merged, disp, all, win } = built;
    const { meta, blob } = merged;
    const sigs: ViewerSig[] = meta.sigs.filter((s) => s.name !== "valid" && (disp[s.name] !== undefined)).map((s, k) => {
      const nm = disp[s.name];
      const j = /^d(\d+)$/.exec(s.name)?.[1];
      const base = { ...s, name: nm };
      if (s.name === "pv") return { ...base, role: "PV", color: pal.pv, unit: units.pv, axis: "pv" };
      if (s.name === "sp") return { ...base, role: "SP", color: pal.sp, unit: units.pv, axis: "pv" };
      if (s.name === "mv") return { ...base, role: "MV", color: pal.mv, unit: units.mv, axis: "mv" };
      if (j !== undefined) return { ...base, role: "DV", color: col(DIST_STYLE[+j % 4][0]), unit: "", axis: null };
      if (!CURVES.includes(s.name)) return { ...base, role: "", color: col(pal.series[k % pal.series.length]), unit: "", axis: null };   // ostatní signál záznamu
      if (s.name === "residual") return { ...base, role: "", color: pal.model, unit: units.pv, axis: null };
      return { ...base, role: "", color: pal.model, unit: units.pv, axis: "pv", dash: "6 4" };
    });
    const nm = (k: string | null) => (k && disp[k] && meta.sigs.some((s) => s.name === k) ? disp[k] : null);
    const ds = (ws.dists ?? []).map((_, j) => disp[`d${j}`]).filter((x) => sigs.some((s) => s.name === x));
    const model_ = all ? {
      pv: disp.pv, all: nm(all) as string, win: nm(win), mv: nm("model_mv"), dv: nm("model_dv"), resid: nm("residual"),
      txt: Object.fromEntries(MODEL_TXT.map((k) => [k, T("mw_" + k)])),
    } : undefined;
    return {
      key: "model_view", view_key: `model|${ws.fname}|${meta.hash}`, sigs, times: meta.times, T: meta.T, decim: meta.decim,
      hash: meta.hash, clock: clockOf(ws, meta.tmin), tunit: "auto", dec, dark, txt: viewerTxt(texts),
      fname: ws.fname, layout, b64: null, url: null, buf: blob, spans, model: model_,
      defaults: { panels: [
        { sigs: [disp.pv, nm("sp"), nm(all)].filter((x): x is string => !!x), h: 230 },
        { sigs: [disp.mv], h: 150 },
        ...ds.map((d) => ({ sigs: [d], h: 130 })),
      ] },
      groups: undefined,
      compact: true,
    };
  }, [built, spans, ws, texts, dec, dark, pal, col, T, layout, units.pv, units.mv]);

  useViewerMount(box, data, { onLayout, onWins: (w) => onWins(w as WinsOut), onMode });

  return <div ref={box} className="viewer-host" data-testid="model-trend" aria-busy={!built || !spans} />;
}
