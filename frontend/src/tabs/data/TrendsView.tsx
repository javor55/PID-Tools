// Data › Trendy: hlavní nástroj na prohlížení všech signálů všech zdrojů na společné časové ose. Graf je sdílený
// prohlížeč viewer.js (panely, Pan / Zoom X / Zoom Y, zpět / vpřed, přehled, události, tabulka, CSV / PNG, vypočtené
// signály, nezávislé časové kurzory A / B a hodnotové Y₁ / Y₂ s odečtem). Seznam signálů prohlížeče je v pravém panelu
// (skupiny podle smyček nebo souborů); rozvržení panelů a vyznačení úseku A–B pro Model / Diagnostiku dělá stránka.
// Data: binární balík `/signals/all` (bez převzorkování, nad limitem min / max po skupinách).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { binary, request } from "../../api/client";
import { unframe } from "../../api/signals";
import { Card } from "../../components/Card";
import { LabelHelp, Seg, SideCard } from "../../components/Ui";
import { decOf, useTexts, useT } from "../../i18n";
import { useUi } from "../../store";
import "../../styles/trends.css";
import mountViewer from "../../../../pidtools/ui/static/viewer.js";
import PIDViewAn from "../../../../pidtools/ui/static/viewer_an.js";
import "../../../../pidtools/ui/static/viewer.css";
import { useDiagWin } from "../DiagTab";
import { useActiveLoop, useTrendCatalog, useTrendSources } from "./trends/hooks";
import { layoutPanels, type LayoutMode, type SigInfo, treeGroups } from "./trends/model";
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

(window as unknown as { PIDViewAn?: unknown }).PIDViewAn ??= PIDViewAn;

const KEY = "trends_view";

interface ViewerApi {
  state?: () => { panels: { sigs: string[] }[]; cur: { on: boolean; a: number | null; b: number | null } };
  setGroups?: (g: { label: string; names: string[] }[]) => void;
  setPanels?: (p: { sigs: string[]; h?: number }[]) => void;
}
const api = (): ViewerApi | undefined => (window as unknown as { __pidView?: Record<string, ViewerApi> }).__pidView?.[KEY];

/** Stav stránky Trendů sdílený hlavní plochou a pravým panelem. */
interface TrendsUi {
  by: "loop" | "source"; onlyActive: boolean; host: HTMLDivElement | null; names: Record<string, string>;   // ref → název v grafu
  set: (p: Partial<Omit<TrendsUi, "set">>) => void;
}
export const useTrendsUi = create<TrendsUi>((set) => ({ by: "loop", onlyActive: false, host: null, names: {}, set: (p) => set(p) }));

/** Skupiny seznamu signálů prohlížeče (smyčky → role, nebo soubory). */
function viewerGroups(sigs: SigInfo[], names: Record<string, string>, by: "loop" | "source", only: string | null, none: string) {
  return treeGroups(sigs, by, "", only, none).map((g) => ({ label: g.title, names: g.items.map((s) => names[s.ref]).filter(Boolean) }));
}

function useActiveTag(sigs: SigInfo[]) {
  const active = useActiveLoop();
  return sigs.find((s) => s.role === "PV" && s.loopIndex === active)?.loop ?? null;
}

export function TrendsMain() {
  const T = useT();
  const texts = useTexts();
  const qc = useQueryClient();
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const setTab = useUi((s) => s.setTab);
  const setDiag = useUi((s) => s.setDiag);
  const dark = useUi((s) => s.theme) === "dark" || document.documentElement.dataset.theme === "dark";
  const win = useDiagWin();
  const cat = useTrendCatalog();
  const src = useTrendSources().data;
  const ui = useTrendsUi(useShallow((s) => ({ by: s.by, onlyActive: s.onlyActive, host: s.host })));
  const activeTag = useActiveTag(cat.sigs);
  const box = useRef<HTMLDivElement>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; to?: "model" | "diag" } | null>(null);
  const [layout, setLayout] = useState<LayoutMode | "custom">("loop");
  // balík signálů: klíč podle zdrojů (ne pod ["ws", wid], aby ho nenačítala znovu každá změna nastavení)
  const ver = JSON.stringify((src?.sources ?? []).map((s) => [s.id, s.columns?.length, s.start, s.end, s.offset_s, s.timezone, s.loaded]));
  const pack = useQuery({
    queryKey: ["allsignals", wid, ver], enabled: !!wid && !!src && (src.sources ?? []).some((s) => s.loaded !== false),
    staleTime: Infinity, gcTime: 60_000,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/signals/all`)),
  });
  const meta = pack.data?.meta as (NonNullable<typeof pack.data>["meta"] & { refs?: Record<string, string>; origin?: string | null }) | undefined;
  const names = useMemo(() => Object.fromEntries(Object.entries(meta?.refs ?? {}).map(([n, r]) => [r, n])), [meta]);
  const groups = useMemo(() => viewerGroups(cat.sigs, names, ui.by, ui.onlyActive ? activeTag : null, T("trd_ui_no_loop")),
    [cat.sigs, names, ui.by, ui.onlyActive, activeTag, T]);

  const presetPanels = (mode: LayoutMode, sigsNow?: string[]) => {
    const byName = new Map(cat.sigs.map((s) => [names[s.ref], s]));
    const vis = (sigsNow ?? []).map((n) => byName.get(n)).filter((s): s is SigInfo => !!s);
    const base = vis.length ? vis : cat.sigs.filter((s) => s.role === "PV" || s.role === "SP" || s.role === "MV").slice(0, 9);
    return layoutPanels(base, mode, { one: "", none: "" }).map((p, i) => ({ sigs: p.refs.map((r) => names[r]).filter(Boolean), h: i ? 160 : 210 }));
  };

  // prohlížeč: mount při novém balíku / jazyku / vzhledu; seznam signálů do pravého panelu
  useEffect(() => {
    if (!box.current || !pack.data || !meta || !texts) return;
    const { blob } = pack.data;
    const info = new Map(cat.sigs.map((s) => [names[s.ref], s]));
    const sigs = meta.sigs.map((s) => {
      const i = info.get(s.name);
      return { ...s, role: i?.role ?? "", color: i?.color ?? "#64748b", unit: i?.unit ?? "", axis: i?.quantity ?? null };
    });
    window.__pidViewData = { [meta.hash]: { buf: blob, sigs: {} } };
    const o = meta.origin ? Date.parse(meta.origin.replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(meta.origin) ? "" : "Z")) : NaN;
    const clock = Number.isFinite(o) ? o + meta.tmin * 1000 : null;
    const txt = Object.fromEntries(Object.entries(texts).filter(([k]) => k.startsWith("vw_")).map(([k, v]) => [k.slice(3), v]));
    const sig = `${meta.hash}|${lang}|${dark}|${JSON.stringify(sigs.map((s) => [s.name, s.role, s.color]))}`;
    const fresh = !(window as unknown as { __pidViewState?: Record<string, unknown> }).__pidViewState?.[`trends|${meta.hash}`];
    mountViewer({
      data: {
        key: KEY, view_key: `trends|${meta.hash}`, sigs, times: meta.times, T: meta.T, decim: meta.decim, hash: meta.hash,
        clock, tunit: "auto", dec: decOf(lang), dark, txt, fname: "trends", layout: null, b64: null, url: null, groups, sig,
      },
      parentElement: box.current, listHost: useTrendsUi.getState().host ?? undefined,
      setStateValue: () => undefined,
    });
    if (fresh) setTimeout(() => api()?.setPanels?.(presetPanels("loop")), 0);      // výchozí: panel na smyčku
    useTrendsUi.getState().set({ names });
  }, [pack.data, meta, texts, lang, dark, ui.host]);       // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { api()?.setGroups?.(groups); }, [groups]);

  const cursor = () => {
    const c = api()?.state?.().cur;
    if (!c?.on || c.a === null || c.b === null || c.a === c.b || !meta) return null;
    return [Math.min(c.a, c.b) + meta.tmin, Math.max(c.a, c.b) + meta.tmin] as [number, number];
  };
  async function markModel() {
    const ab = cursor();
    if (!ab) { setMsg({ ok: false, text: T("trd_ui_mark_need") }); return; }
    try {
      await request("PUT", `/workspaces/${wid}/range/common`, { a: ab[0], b: ab[1] });
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
      setMsg({ ok: true, text: T("trd_ui_marked_model"), to: "model" });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
  }
  async function markDiag() {
    const ab = cursor();
    if (!ab || !win) { setMsg({ ok: false, text: T("trd_ui_mark_need") }); return; }
    try {
      const r = await request<{ a: number; b: number }>("PUT", `/workspaces/${wid}/range/common?apply=false`, { a: ab[0], b: ab[1] });
      setDiag({ ...win, a: [r.a, r.b] });
      setMsg({ ok: true, text: T("trd_ui_marked_diag"), to: "diag" });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
  }
  const applyLayout = (m: LayoutMode) => {
    setLayout(m);
    const cur = api()?.state?.().panels.flatMap((p) => p.sigs) ?? [];
    api()?.setPanels?.(presetPanels(m, cur));
  };

  if (!wid || (cat.ready && !cat.sigs.length)) return <Card title={T("trd_ui_title")} testid="trd-empty"><p className="muted">{T("trd_ui_empty")}</p></Card>;
  return (
    <div className="trd-main" data-testid="trends-main">
      <Card testid="trd-tools" className="trd-tools">
        <div className="trd-toolbar">
          <span className="trd-tg">
            <span className="trd-lbl">{T("trd_ui_layout")}</span>
            <Seg<LayoutMode | "custom"> value={layout} options={["one", "loop", "unit"]} label={T("trd_ui_layout")} small testid="trd-layout"
              fmt={(v) => T(`trd_ui_l_${v}`)} onChange={(v) => { if (v !== "custom") applyLayout(v); }} help="trd_ui_help_layout" />
          </span>
          <span className="trd-tg trd-mark" data-testid="trd-mark">
            <span className="trd-lbl">{T("trd_ui_mark")}<LabelHelp text="trd_ui_help_mark" /></span>
            <button type="button" className="btn small" title={T("trd_ui_to_model_t")} data-testid="trd-mark-model" onClick={() => void markModel()}>{T("trd_ui_to_model")}</button>
            <button type="button" className="btn small" disabled={!win} title={T("trd_ui_to_diag_t")} data-testid="trd-mark-diag" onClick={() => void markDiag()}>{T("trd_ui_to_diag")}</button>
          </span>
          {msg && <span className={msg.ok ? "trd-ok" : "trd-err"} role="status" data-testid="trd-mark-msg">
            {msg.text}{msg.ok && <> <button type="button" className="link" onClick={() => setTab(msg.to!)}>{T("trd_ui_open")}</button></>}</span>}
        </div>
      </Card>
      {pack.isError && <Card title={T("trd_ui_title")}><p className="err">{String((pack.error as Error).message)}</p></Card>}
      {!pack.data && !pack.isError && <Card title={T("trd_ui_title")} testid="trd-loading"><p className="muted">…</p></Card>}
      <div ref={box} className="viewer-host trd-viewer" data-testid="trd-viewer" />
    </div>
  );
}

export function TrendsSide() {
  const T = useT();
  const ui = useTrendsUi();
  const cat = useTrendCatalog();
  const activeTag = useActiveTag(cat.sigs);
  // prvek, do kterého prohlížeč vloží seznam signálů; po znovuvložení (sbalení karty) se prohlížeč připojí znovu
  const hostRef = useCallback((el: HTMLDivElement | null) => {
    if (el && el !== useTrendsUi.getState().host) useTrendsUi.getState().set({ host: el });
  }, []);
  return (
    <div className="trd-side" data-testid="trends-side">
      <SideCard title={T("trd_ui_signals")} help="trd_ui_help_signals" testid="trd-signals">
        <Seg<"loop" | "source"> value={ui.by} options={["loop", "source"]} label={T("trd_ui_by")} small stretch testid="trd-by"
          fmt={(v) => T(`trd_ui_by_${v}`)} onChange={(v) => ui.set({ by: v })} help="trd_ui_help_by" />
        <label className="trd-chk" title={T("trd_ui_help_only_active")}>
          <input type="checkbox" checked={ui.onlyActive} disabled={!activeTag} onChange={(e) => ui.set({ onlyActive: e.target.checked })} />
          {T("trd_ui_only_active", { tag: activeTag ?? "–" })}<LabelHelp text="trd_ui_help_only_active" />
        </label>
        <div ref={hostRef} className="trd-listhost" data-testid="trd-tree" />
      </SideCard>
    </div>
  );
}
