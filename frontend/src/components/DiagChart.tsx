// Graf záložky Diagnostika: prohlížeč záznamu (viewer.js) s vrstvou úseků v režimu „ab“ (viewer_spans.js) – úsek A a volitelně
// B pro srovnání. Výchozí rozložení: panel 1 = PV + SP, panel 2 = MV; ostatní signály záznamu (včetně poruch) lze přidat
// ze seznamu. Rozložení se ukládá do nastavení smyčky „diagview“ (odděleně od „dview“ Trendů a „mview“ Modelu). Data:
// mřížka smyčky (/signals?source=grid) a ostatní signály záznamu v jednom balíku v paměti; úseky ven jdou přes onWins.
import { useMemo, useRef } from "react";
import type { components } from "../api/schema";
import { series } from "../api/signals";
import type { ViewerData, ViewerSig, ViewerSpans } from "../legacy/viewer.js";
import { readable } from "../lib/palette";
import { timeUnit } from "../lib/series";
import { type DiagWin } from "../store";
import { QueryState } from "./QueryState";
import { Help } from "./Ui";
import { clockOf, uniqueNames, useGridPack, useRawPack, useViewerEnv, useViewerMount, viewerTxt, withRecordSignals } from "./viewerMount";

type Ws = components["schemas"]["WorkspaceInfo"];
type Pack = NonNullable<ReturnType<typeof useGridPack>["data"]>;

export interface DiagWinsOut { mode: string; ab?: { a: [number, number]; b: [number, number] | null } }
export interface DiagChartProps {
  ws: Ws | undefined; win: DiagWin;
  units: { pv: string; mv: string };                       // jednotky PV a MV z nastavení smyčky
  layout: string | null;                                   // uložené rozložení (nastavení „diagview“)
  onWins: (a: [number, number], b: [number, number] | null) => void;
  onLayout: (layout: string) => void;
}

const SPAN_TXT = ["zoom_win", "drag_win", "start", "end", "zoom_one"];
const RESERVED = new Set(["pv", "mv", "sp", "valid"]);

function Chart({ ws, win, grid, raw, units, layout, onWins, onLayout }: DiagChartProps & { ws: Ws; grid: Pack; raw: Pack | undefined }) {
  const { T, texts, dark, pal, col, dec } = useViewerEnv();
  const box = useRef<HTMLDivElement>(null);

  const data = useMemo<Omit<ViewerData, "sig"> | null>(() => {
    if (!texts) return null;
    const t = series(grid.meta, grid.blob, "pv")?.t;
    if (!t?.length || !series(grid.meta, grid.blob, "mv")) return null;
    const { merged, extra } = withRecordSignals(grid, raw, ws, RESERVED);
    const { meta, blob } = merged;
    const uniq = uniqueNames();
    const disp: Record<string, string> = { pv: uniq(ws.pv ?? "PV"), mv: uniq(ws.mv ?? "MV") };
    if (ws.sp) disp.sp = uniq(ws.sp);
    (ws.dists ?? []).forEach((d, j) => { disp[`d${j}`] = uniq(d); });
    for (const n of extra) disp[n] = uniq(n);
    const sigs: ViewerSig[] = meta.sigs.filter((s) => disp[s.name] !== undefined).map((s, k) => {
      const base = { ...s, name: disp[s.name] };
      if (s.name === "pv") return { ...base, role: "PV", color: pal.pv, unit: units.pv, axis: "pv" };
      if (s.name === "sp") return { ...base, role: "SP", color: pal.sp, unit: units.pv, axis: "pv" };
      if (s.name === "mv") return { ...base, role: "MV", color: pal.mv, unit: units.mv, axis: "mv" };
      if (/^d\d+$/.test(s.name)) return { ...base, role: "DV", color: col(pal.dist[+s.name.slice(1) % pal.dist.length]), unit: "", axis: null };
      return { ...base, role: "", color: col(pal.series[k % pal.series.length]), unit: "", axis: null };   // ostatní signál záznamu
    });
    const Tend = t[t.length - 1];
    const tx = (c: string) => readable(c, pal.card, 4.5);     // text štítků úseků: kontrast ≥ 4,5 : 1 proti pozadí štítku
    const spans: ViewerSpans = {
      mode: "ab", step: ws.Ts ?? 1, unit: timeUnit(Tend), inputs: [], excl: [],
      ab: { a: win.a, b: win.cmp ? win.b : null, ca: pal.segA, cb: pal.segB, ta: tx(pal.segA), tb: tx(pal.segB), bg: pal.card,
        la: T("seg_a"), lb: T("seg_b") },
      txt: Object.fromEntries(SPAN_TXT.map((k) => [k, T("mw_" + k)])),
    };
    return {
      key: "diag_view", view_key: `diag|${ws.fname}|${meta.hash}`, sigs, times: meta.times, T: meta.T, decim: meta.decim,
      hash: meta.hash, clock: clockOf(ws, meta.tmin), tunit: "auto", dec, dark, txt: viewerTxt(texts),
      fname: ws.fname, layout, b64: null, url: null, buf: blob, spans, compact: true,
      defaults: { panels: [
        { sigs: [disp.pv, ws.sp ? disp.sp : null].filter((x): x is string => !!x), h: 230 },
        { sigs: [disp.mv], h: 150 },
      ] },
    };
  }, [ws, win, grid, raw, texts, dec, dark, pal, col, T, layout, units.pv, units.mv]);

  useViewerMount(box, data, {
    onLayout,
    onWins: (w) => { const o = w as DiagWinsOut; if (o.ab) onWins(o.ab.a, o.ab.b); },
  });
  return <div ref={box} className="viewer-host" data-testid="diag-trend" aria-busy={!data} />;
}

/** Záznam s úseky A / B: stavy načítání, prázdno a chyba jako v ostatních pohledech (QueryState). */
export function DiagChart(props: DiagChartProps) {
  const { ws } = props;
  const T = useViewerEnv().T;
  const grid = useGridPack();
  const raw = useRawPack();
  return (
    <section className="diag-rec" data-testid="diag-rec">
      <div className="diag-rec-head"><h2>{T("diag_rec_title")}<Help text={T("diag_rec_help")} /></h2></div>
      <QueryState q={grid} emptyText={T("ui_no_data")}
        empty={(g) => !series(g.meta, g.blob, "pv") || !series(g.meta, g.blob, "mv")}>
        {(g) => (ws?.has_data ? <Chart {...props} ws={ws} grid={g} raw={raw.data} /> : null)}
      </QueryState>
    </section>
  );
}
