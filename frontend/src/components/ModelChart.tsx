// Graf záložky Model › Identifikace: prohlížeč záznamu (viewer.js) s vrstvou úseků identifikace (viewer_spans.js)
// a přepínači průběhu modelu (viewer_model.js). Výchozí rozložení: panel 1 = PV + SP + model, panel 2 = MV, pak panel na
// každou poruchu; uživatel může přidat další signály ze záznamu. Rozložení se ukládá do nastavení smyčky „mview“
// (odděleně od „dview“ Trendů). Data: mřížka smyčky (/signals?source=grid) + průběhy modelu (/model/curves) sloučené do
// jednoho balíku v paměti; úseky a režim úseků přicházejí z API (okno /windows, nastavení win_mode) a ven jdou přes onWins.
import { useEffect, useMemo, useRef } from "react";
import type { components } from "../api/schema";
import { mergePacks, series, type PackMeta } from "../api/signals";
import mountViewer, { type ViewerData, type ViewerSig, type ViewerSpans } from "../legacy/viewer.js";
import PIDViewAn from "../legacy/viewer_an.js";
import "../legacy/viewer.css";
import { decOf, useT, useTexts } from "../i18n";
import { readable, usePalette } from "../lib/palette";
import { runs, timeUnit } from "../lib/series";
import { useUi } from "../store";
import { DIST_STYLE, MV_STYLE, windowFits } from "../tabs/modelConst";

(window as unknown as { PIDViewAn?: unknown }).PIDViewAn ??= PIDViewAn;

type ModelState = components["schemas"]["ModelState"];
type WindowsInfo = components["schemas"]["WindowsInfo"];
type Pack = { meta: PackMeta; blob: ArrayBuffer };

export interface WinsOut { mode: string; wins: Record<string, [number, number][]>; common: [number, number] }
export interface ModelChartProps {
  ws: components["schemas"]["WorkspaceInfo"] | undefined;
  grid: Pack | undefined; curves: Pack | undefined;
  windows: WindowsInfo | undefined; model: ModelState | undefined;
  winMode: "common" | "inputs";
  units: { pv: string; mv: string };                       // jednotky PV a MV z nastavení smyčky
  layout: string | null;                                   // uložené rozložení (nastavení „mview“)
  onWins: (w: WinsOut) => void;
  onMode: (mode: string) => void;
  onLayout: (layout: string) => void;
}

const CURVES = ["model", "full", "model_mv", "model_dv", "residual"];
const SPAN_TXT = ["mode", "h_mode", "common", "inputs", "zoom_win", "win", "drag_win", "start", "end", "zoom_one", "del", "add", "excluded"];
const MODEL_TXT = ["m_all", "m_mv", "m_dv", "r_win", "r_full", "resid"];

export function ModelChart({ ws, grid, curves, windows, model, winMode, units, layout, onWins, onMode, onLayout }: ModelChartProps) {
  const T = useT();
  const texts = useTexts();
  const lang = useUi((s) => s.lang);
  const dark = useUi((s) => s.theme) === "dark" || document.documentElement.dataset.theme === "dark";
  const pal = usePalette();
  const box = useRef<HTMLDivElement>(null);
  const destroy = useRef<(() => void) | null>(null);      // odpojení viewer.js; volá se jen při odchodu komponenty
  const h = useRef({ onWins, onMode, onLayout });
  useEffect(() => { h.current = { onWins, onMode, onLayout }; }, [onWins, onMode, onLayout]);

  // balík v paměti: mřížka + průběhy modelu (bez duplicit pv / mv); názvy signálů podle smyčky
  const built = useMemo(() => {
    if (!ws?.has_data || !grid) return null;
    const merged = curves ? mergePacks(grid, curves, CURVES) : { meta: grid.meta, blob: grid.blob };
    const used = new Set<string>();
    const uniq = (n: string) => { let k = n || "?"; while (used.has(k)) k += "·"; used.add(k); return k; };
    const disp: Record<string, string> = {};
    disp.pv = uniq(ws.pv ?? "PV"); disp.mv = uniq(ws.mv ?? "MV");
    if (ws.sp) disp.sp = uniq(ws.sp);
    (ws.dists ?? []).forEach((d, j) => { disp[`d${j}`] = uniq(d); });
    disp.full = uniq(T("mw_sig_model")); disp.model = uniq(T("mw_sig_model_win"));
    disp.model_mv = uniq(T("mw_sig_mv")); disp.model_dv = uniq(T("mw_sig_dv")); disp.residual = uniq(T("mw_sig_resid"));
    const has = (k: string) => merged.meta.sigs.some((s) => s.name === k);
    // „celý model“ je průběh na celém záznamu (full); jen v úsecích (model) je druhá volba; bez full je celým modelem model
    const all = has("full") ? "full" : has("model") ? "model" : null;
    const win = all === "full" && has("model") ? "model" : null;
    return { merged, disp, all, win, has };
  }, [ws, grid, curves, T]);

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
      ccol: MV_STYLE[0], cbd: MV_STYLE[1], ctx: "#7a4b00", cbg: MV_STYLE[2],
      inputs: inputs.map(({ nm, ...r }) => ({ ...r, sig: nm })), excl: excl as number[][],
      txt: Object.fromEntries(SPAN_TXT.map((k) => [k, T("mw_" + k)])),
    };
  }, [ws, grid, curves, windows, model, winMode, T]);

  useEffect(() => {
    if (!box.current || !built || !spans || !ws || !texts) return;
    const { merged, disp, all, win } = built;
    const { meta, blob } = merged;
    const card = pal.card;
    const col = (c: string) => (dark ? readable(c, card) : c);
    const sigs: ViewerSig[] = meta.sigs.filter((s) => s.name !== "valid" && (disp[s.name] !== undefined)).map((s) => {
      const nm = disp[s.name];
      const j = /^d(\d+)$/.exec(s.name)?.[1];
      const base = { ...s, name: nm };
      if (s.name === "pv") return { ...base, role: "PV", color: pal.pv, unit: units.pv, axis: "pv" };
      if (s.name === "sp") return { ...base, role: "SP", color: pal.sp, unit: units.pv, axis: "pv" };
      if (s.name === "mv") return { ...base, role: "MV", color: pal.mv, unit: units.mv, axis: "mv" };
      if (j !== undefined) return { ...base, role: "DV", color: col(DIST_STYLE[+j % 4][0]), unit: "", axis: null };
      if (s.name === "residual") return { ...base, role: "", color: pal.model, unit: units.pv, axis: null };
      return { ...base, role: "", color: pal.model, unit: units.pv, axis: "pv", dash: "6 4" };
    });
    const nm = (k: string | null) => (k && disp[k] && meta.sigs.some((s) => s.name === k) ? disp[k] : null);
    const ds = (ws.dists ?? []).map((_, j) => disp[`d${j}`]).filter((x) => sigs.some((s) => s.name === x));
    const clock = ws.origin ? Date.parse(ws.origin.replace(" ", "T") + "Z") + meta.tmin * 1000 : null;
    const txt = Object.fromEntries(Object.entries(texts).filter(([k]) => k.startsWith("vw_")).map(([k, v]) => [k.slice(3), v]));
    const model_ = all ? {
      pv: disp.pv, all: nm(all) as string, win: nm(win), mv: nm("model_mv"), dv: nm("model_dv"), resid: nm("residual"),
      txt: Object.fromEntries(MODEL_TXT.map((k) => [k, T("mw_" + k)])),
    } : undefined;
    const data: Omit<ViewerData, "sig"> = {
      key: "model_view", view_key: `model|${ws.fname}|${meta.hash}`, sigs, times: meta.times, T: meta.T, decim: meta.decim,
      hash: meta.hash, clock: Number.isFinite(clock) ? clock : null, tunit: "auto", dec: decOf(lang), dark, txt,
      fname: ws.fname, layout, b64: null, url: null, buf: blob, spans, model: model_,
      defaults: { panels: [
        { sigs: [disp.pv, nm("sp"), nm(all)].filter((x): x is string => !!x), h: 230 },
        { sigs: [disp.mv], h: 150 },
        ...ds.map((d) => ({ sigs: [d], h: 130 })),
      ] },
      groups: undefined,
    };
    const sig = `${meta.hash}|${lang}|${dark}|${JSON.stringify(sigs.map((s) => [s.name, s.role, s.color, s.unit]))}`;
    destroy.current = mountViewer({
      data: { ...data, sig }, parentElement: box.current,
      setStateValue: (key, value) => {
        if (key === "layout" && typeof value === "string" && value.length <= 65536) h.current.onLayout(value);
        else if (key === "wins") h.current.onWins(value as WinsOut);
      },
      setTriggerValue: (key, value) => { if (key === "mode") h.current.onMode(String(value)); },
    });
  }, [built, spans, ws, texts, lang, dark, pal, T, layout, units.pv, units.mv]);

  // ne v úklidu efektu výše (ten běží při každé změně dat a modul by ztratil zoom): odpojit až s komponentou
  useEffect(() => () => { destroy.current?.(); destroy.current = null; }, []);

  return <div ref={box} className="viewer-host" data-testid="model-trend" aria-busy={!built || !spans} />;
}
