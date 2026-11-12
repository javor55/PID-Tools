// Data › Trendy (E4-C, deska docs/design/v2/DataTrends.dc.html): všechny signály všech zdrojů na společné časové ose.
// Hlavní plocha (TrendsMain): nástroje, panely (canvas) s kurzory A / B, časová osa, přehledový pruh, označení úseku
// pro Model / Diagnostiku a odečet kurzorů. Pravý panel (TrendsSide): strom signálů (smyčky / zdroje) a vypočtené signály.
// Data: zředěné průběhy ze serveru (`/signals/trend`, min / max po skupinách) pro viditelné okno; viewer.js (jeden záznam
// smyčky) se zde nepoužívá, sdílí se z něj jen jazyk vzorců (viewer_an.js).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { request } from "../../api/client";
import { Card } from "../../components/Card";
import { LabelHelp, Seg, SideCard } from "../../components/Ui";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { useUi } from "../../store";
import "../../styles/trends.css";
import { useDiagWin } from "../DiagTab";
import { useActiveLoop, useTrendSeries } from "./trends/hooks";
import {
  calcRefs, computeCalc, fmtClock, fmtDur, fmtNum, formulaNames, layoutPanels, statsOf, toCsv, treeGroups, valueAt,
  type Calc, type LayoutMode, type Series,
} from "./trends/model";
import { useTrends } from "./trends/state";
import { Navigator, TimeAxis, TrendPanel, type ChartCtx } from "./trends/TrendChart";
import { useSelection } from "./trends/useSelection";

const N_POINTS = 1200;               // skupin pro zředění (≈ 2 body na pixel šířky grafu)
const isCalc = (r: string) => r.startsWith("calc:");

function download(name: string, blob: Blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/** Řady vybraných signálů (server) doplněné o vypočtené signály; závislosti vzorců se načtou také. */
function useVisibleSeries(a: number | null, b: number | null, n: number) {
  const sel = useSelection();
  const calcs = useTrends((s) => s.calcs);
  const names = useMemo(() => formulaNames(sel.sigs), [sel.sigs]);
  const real = useMemo(() => {
    const need = new Set(sel.checked.filter((r) => !isCalc(r)));
    for (const c of calcs) if (sel.checked.includes(`calc:${c.id}`)) calcRefs(c.expr, names).refs.forEach((r) => need.add(r));
    return sel.sigs.filter((s) => need.has(s.ref)).map((s) => s.ref);
  }, [sel.checked, sel.sigs, calcs, names]);
  const q = useTrendSeries(real, a, b, n);
  const map = useMemo(() => {
    const m = new Map<string, Series>();
    for (const s of q.data?.series ?? []) m.set(s.ref, { ref: s.ref, t: s.t, v: s.v });
    const errors: Record<string, string> = {};
    for (const c of calcs) {
      if (!sel.checked.includes(`calc:${c.id}`)) continue;
      const r = computeCalc(c, names, m);
      if (r.series) m.set(r.series.ref, r.series);
      if (r.error) errors[c.id] = r.error;
    }
    return { m, errors };
  }, [q.data, calcs, names, sel.checked]);
  return { ...map, q, names, decimated: (q.data?.series ?? []).some((s) => s.decimated) };
}

export function TrendsMain() {
  const T = useT();
  const qc = useQueryClient();
  const wid = useUi((s) => s.wid);
  const setTab = useUi((s) => s.setTab);
  const setDiag = useUi((s) => s.setDiag);
  const win = useDiagWin();
  const sel = useSelection();
  const st = useTrends();
  const full = sel.full;
  const view: [number, number] | null = full ? (st.view ? [Math.max(st.view[0], full[0]), Math.min(st.view[1], full[1])] : full) : null;
  const [fv, setFv] = useState(view);                       // okno pro dotaz: s krátkým odstupem po zoomu / posunu
  const v0 = view?.[0], v1 = view?.[1];
  useEffect(() => {
    const id = setTimeout(() => setFv(v0 === undefined || v1 === undefined ? null : [v0, v1]), 120);
    return () => clearTimeout(id);
  }, [v0, v1]);
  const cur = useVisibleSeries(fv?.[0] ?? null, fv?.[1] ?? null, N_POINTS);
  const ov = useVisibleSeries(full?.[0] ?? null, full?.[1] ?? null, 300);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; to?: "model" | "diag" } | null>(null);
  const charts = useRef<HTMLDivElement>(null);

  const visible = sel.checked.map((r) => sel.allInfo.get(r)!).filter(Boolean);
  const panels = layoutPanels(visible, st.layout, { one: T("trd_ui_panel_all"), none: T("trd_ui_panel_none") });
  const hasAB = st.a !== null && st.b !== null && st.a !== st.b;
  const lo = hasAB ? Math.min(st.a!, st.b!) : null, hi = hasAB ? Math.max(st.a!, st.b!) : null;
  const realChecked = sel.checked.filter((r) => !isCalc(r));
  const rd = useTrendSeries(realChecked, lo, hi, 10, hasAB ? [st.a!, st.b!] : [], hasAB && realChecked.length > 0);

  if (!wid || (sel.ready && (!full || !sel.sigs.length))) return <Card title={T("trd_ui_title")} testid="trd-empty"><p className="muted">{T("trd_ui_empty")}</p></Card>;
  if (!full || !view) return <Card title={T("trd_ui_title")} testid="trd-empty"><p className="muted">…</p></Card>;

  const setView = (v: [number, number] | null) => st.set({ view: v });
  const ctx: ChartCtx = {
    view, full, origin: sel.origin, a: st.a, b: st.b, onView: setView,
    onCursor: (w, t) => st.set(w === "a" ? { a: t } : { b: t }),
  };
  const zoomSel = () => { if (hasAB) setView([lo!, hi!]); };
  const small = panels.length > 2;

  async function exportCsv() {
    const refs = Array.from(new Set(realChecked.concat(st.calcs.filter((c) => sel.checked.includes(`calc:${c.id}`)).flatMap((c) => calcRefs(c.expr, cur.names).refs))));
    const q = new URLSearchParams();
    refs.forEach((r) => q.append("names", r));
    q.set("a", String(view![0])); q.set("b", String(view![1])); q.set("n", "20000");
    const out = await request<{ series: { ref: string; t: number[]; v: number[] }[] }>("GET", `/workspaces/${wid}/signals/trend?${q.toString()}`);
    const m = new Map<string, Series>(out.series.map((s) => [s.ref, { ref: s.ref, t: s.t, v: s.v }]));
    const cols: { name: string; t: ArrayLike<number>; v: ArrayLike<number> }[] = [];
    for (const r of sel.checked) {
      const i = sel.allInfo.get(r)!;
      if (isCalc(r)) {
        const c = st.calcs.find((x) => `calc:${x.id}` === r)!;
        const s = computeCalc(c, cur.names, m).series;
        if (s) cols.push({ name: i.column, t: s.t, v: s.v });
      } else if (m.get(r)) cols.push({ name: r, t: m.get(r)!.t, v: m.get(r)!.v });
    }
    download("trends.csv", new Blob(["﻿" + toCsv(cols, sel.origin, view![0], view![1])], { type: "text/csv;charset=utf-8" }));
  }

  function exportPng() {
    const root = charts.current;
    if (!root) return;
    const r = window.devicePixelRatio || 1;
    const items = [...root.querySelectorAll<HTMLElement>(".trd-panel")].map((p) => ({
      title: `${p.dataset.title ?? ""} – ${p.querySelector(".trd-psub")?.textContent ?? ""}`, cv: p.querySelector("canvas")!,
    }));
    const axis = root.querySelector<HTMLCanvasElement>('[data-testid="trd-axis"]');
    const w = Math.max(...items.map((i) => i.cv.width), 1), head = 22 * r;
    const h = items.reduce((s, i) => s + head + i.cv.height, 0) + (axis?.height ?? 0);
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const g = c.getContext("2d")!;
    g.fillStyle = getComputedStyle(root).getPropertyValue("--pid-card").trim() || "#ffffff";
    g.fillRect(0, 0, w, h);
    g.fillStyle = getComputedStyle(root).getPropertyValue("--pid-text").trim() || "#1f2933";
    g.font = `600 ${13 * r}px 'IBM Plex Sans', sans-serif`; g.textBaseline = "middle";
    let y = 0;
    for (const i of items) { g.fillText(i.title, 4 * r, y + head / 2); g.drawImage(i.cv, 0, y + head); y += head + i.cv.height; }
    if (axis) g.drawImage(axis, 0, y);
    c.toBlob((b) => { if (b) download("trends.png", b); }, "image/png");
  }

  async function markModel() {
    if (!hasAB) return;
    try {
      await request("PUT", `/workspaces/${wid}/range/common`, { a: lo, b: hi });
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
      setMsg({ ok: true, text: T("trd_ui_marked_model"), to: "model" });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
  }
  async function markDiag() {
    if (!hasAB || !win) return;
    try {
      const r = await request<{ a: number; b: number }>("PUT", `/workspaces/${wid}/range/common?apply=false`, { a: lo, b: hi });
      setDiag({ ...win, a: [r.a, r.b] });
      setMsg({ ok: true, text: T("trd_ui_marked_diag"), to: "diag" });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
  }
  const goto = (tab: "model" | "diag") => setTab(tab);

  // ---- odečet kurzorů
  const rows = visible.map((i) => {
    const s = cur.m.get(i.ref);
    if (isCalc(i.ref)) {
      return { i, a: s && st.a !== null ? valueAt(s, st.a) : null, b: s && st.b !== null ? valueAt(s, st.b) : null,
        st: s && hasAB ? statsOf(s, lo!, hi!) : null };
    }
    const r = rd.data?.series.find((x) => x.ref === i.ref);
    return { i, a: r?.at?.[0] ?? null, b: r?.at?.[1] ?? null, st: r ? { min: r.stats.min ?? null, max: r.stats.max ?? null, mean: r.stats.mean ?? null, std: r.stats.std ?? null } : null };
  });
  const span = view[1] - view[0];
  const note = `${fmtClock(sel.origin, view[0], true, false)}–${fmtClock(sel.origin, view[1], false, false)} · ${T(sel.isCommon ? "trd_ui_span_common" : "trd_ui_span_union")}`;

  return (
    <div className="trd-main" data-testid="trends-main">
      <Card testid="trd-tools" className="trd-tools">
        <div className="trd-toolbar">
          <span className="trd-tg">
            <span className="trd-lbl">{T("trd_ui_layout")}</span>
            <Seg<LayoutMode> value={st.layout} options={["one", "loop", "unit"]} label={T("trd_ui_layout")} small testid="trd-layout"
              fmt={(v) => T(`trd_ui_l_${v}`)} onChange={(v) => st.set({ layout: v })} help="trd_ui_help_layout" />
          </span>
          <span className="trd-tg">
            <span className="trd-lbl">{T("trd_ui_zoom")}</span>
            <Seg<"all" | "sel"> value={st.view ? "sel" : "all"} options={["all", "sel"]} label={T("trd_ui_zoom")} small testid="trd-zoom"
              fmt={(v) => T(`trd_ui_z_${v}`)} onChange={(v) => (v === "all" ? setView(null) : zoomSel())} help="trd_ui_help_zoom" />
          </span>
          <span className="trd-tg">
            <span className="trd-lbl">{T("trd_ui_cursors")}</span>
            <span className="seg-help">
              <span className="seg small" role="group" aria-label={T("trd_ui_cursors")}>
                <button type="button" aria-pressed={hasAB} title={T("trd_ui_c_ab_t")} data-testid="trd-ab"
                  onClick={() => st.set(hasAB ? { a: null, b: null } : { a: view[0] + span * 0.3, b: view[0] + span * 0.7 })}>{T("trd_ui_c_ab")}</button>
              </span>
              <LabelHelp text="trd_ui_help_cursors" />
            </span>
          </span>
          <label className="trd-chk" title={T("trd_ui_help_shared")}>
            <input type="checkbox" checked={st.sharedY} onChange={(e) => st.set({ sharedY: e.target.checked })} data-testid="trd-shared" />
            {T("trd_ui_shared")}<LabelHelp text="trd_ui_help_shared" />
          </label>
          <span className="trd-exp">
            <button type="button" className="btn" title={T("trd_ui_png_t")} data-testid="trd-png" onClick={exportPng}>{T("trd_ui_png")}</button>
            <button type="button" className="btn" title={T("trd_ui_csv_t")} data-testid="trd-csv" onClick={() => void exportCsv()}>{T("trd_ui_csv")}</button>
          </span>
        </div>
      </Card>

      <Card title={T("trd_ui_title")} help="trd_ui_help_trends" right={<span className="muted trd-note" data-testid="trd-note">{note}{cur.decimated ? ` · ${T("trd_ui_decimated")}` : ""}</span>}
        testid="trd-charts">
        <div ref={charts} className="trd-charts">
          {panels.length === 0 && <p className="muted" data-testid="trd-nosel">{T("trd_ui_no_sel")}</p>}
          {panels.map((p) => (
            <TrendPanel key={p.id} panel={p} ctx={ctx} info={sel.allInfo} shared={st.sharedY} height={small ? 130 : p === panels[0] ? 190 : 150}
              series={p.refs.map((r) => cur.m.get(r)).filter((s): s is Series => !!s)}
              onRemove={(r) => st.toggle(r, sel.checked)} />
          ))}
          {panels.length > 0 && <TimeAxis ctx={ctx} right />}
          {panels.length > 0 && (
            <div className="trd-navrow"><span className="trd-lbl">{T("trd_ui_overview")}</span>
              <Navigator ctx={ctx} info={sel.allInfo} title={T("trd_ui_nav_win")}
                series={sel.checked.slice(0, 3).map((r) => ov.m.get(r)).filter((s): s is Series => !!s)} />
              <span className="muted trd-nrange">{fmtDur(span)}</span></div>)}
        </div>
        <div className="trd-mark" data-testid="trd-mark">
          <span>{T("trd_ui_mark")}<LabelHelp text="trd_ui_help_mark" /></span>
          <button type="button" className="btn" disabled={!hasAB} title={hasAB ? T("trd_ui_to_model_t") : T("trd_ui_mark_need")} data-testid="trd-mark-model"
            onClick={() => void markModel()}>{T("trd_ui_to_model")}</button>
          <button type="button" className="btn" disabled={!hasAB || !win} title={hasAB ? T("trd_ui_to_diag_t") : T("trd_ui_mark_need")} data-testid="trd-mark-diag"
            onClick={() => void markDiag()}>{T("trd_ui_to_diag")}</button>
          {hasAB
            ? <span className="muted">({T("trd_ui_ab_range", { a: fmtClock(sel.origin, lo!, false, true), b: fmtClock(sel.origin, hi!, false, true), d: fmtDur(hi! - lo!) })})</span>
            : <span className="muted">{T("trd_ui_cursor_hint")}</span>}
          {msg && <span className={msg.ok ? "trd-ok" : "trd-err"} role="status" data-testid="trd-mark-msg">
            {msg.text}{msg.ok && <> <button type="button" className="link" onClick={() => goto(msg.to!)}>{T("trd_ui_open")}</button></>}</span>}
        </div>
      </Card>

      <Card title={T("trd_ui_readout")} help="trd_ui_help_readout" testid="trd-readout"
        right={<span className="muted">{hasAB ? T("trd_ui_ab_range", { a: fmtClock(sel.origin, lo!, false, true), b: fmtClock(sel.origin, hi!, false, true), d: fmtDur(hi! - lo!) }) : ""}</span>}>
        {!hasAB ? <p className="muted">{T("trd_ui_cursor_hint")}</p> : (
          <div className="trd-tablebox">
            <table className="trd-table">
              <thead><tr>
                <th>{T("trd_ui_th_sig")}</th><th>A</th><th>B</th><th>Δ</th><th>min</th><th>max</th><th>{T("trd_ui_th_mean")}</th><th>σ</th>
              </tr></thead>
              <tbody>{rows.map(({ i, a, b, st: s }) => (
                <tr key={i.ref} data-ref={i.ref}>
                  <td><span className="trd-sw" style={{ borderTopColor: i.color, borderTopStyle: i.dash ? "dashed" : "solid" }} />{i.loop ? `${i.loop}.` : ""}{i.label === i.column ? i.column : i.label}</td>
                  <td data-c="a">{fmtNum(a)}</td><td data-c="b">{fmtNum(b)}</td><td data-c="d">{a !== null && b !== null ? fmtNum(b - a) : "–"}</td>
                  <td>{fmtNum(s?.min)}</td><td>{fmtNum(s?.max)}</td><td>{fmtNum(s?.mean)}</td><td>{fmtNum(s?.std)}</td>
                </tr>))}</tbody>
            </table>
          </div>)}
      </Card>
    </div>
  );
}

let calcSeq = 1;

export function TrendsSide() {
  const T = useT();
  const sel = useSelection();
  const st = useTrends();
  const ws = useWs().data;
  const active = useActiveLoop();
  const activeTag = sel.sigs.find((s) => s.role === "PV" && s.loopIndex === active)?.loop
    ?? (ws?.pv ? sel.sigs.find((s) => s.role === "PV" && s.column === ws.pv)?.loop ?? null : null);
  const groups = treeGroups(sel.sigs, st.groupBy, st.search, st.onlyActive ? activeTag : null, T("trd_ui_no_loop"));
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [form, setForm] = useState(false);
  const [c, setC] = useState({ name: "e", expr: "", unit: "" });
  const names = useMemo(() => formulaNames(sel.sigs), [sel.sigs]);
  const chk = new Set(sel.checked);
  const test = c.expr.trim() ? calcRefs(c.expr, names) : null;
  const nameBad = !c.name.trim() || sel.all.some((s) => s.column === c.name.trim() && s.source === "calc");

  function add() {
    if (!test || test.error || !test.refs.length || nameBad) return;
    const id = `c${calcSeq++}_${Date.now().toString(36)}`;
    const cc: Calc = { id, name: c.name.trim(), expr: c.expr.trim(), unit: c.unit.trim() };
    st.set({ calcs: [...st.calcs, cc], checked: [...sel.checked, `calc:${id}`] });
    setC({ name: `${c.name.trim()}2`, expr: "", unit: "" });
    setForm(false);
  }
  const rm = (id: string) => st.set({ calcs: st.calcs.filter((x) => x.id !== id), checked: sel.checked.filter((r) => r !== `calc:${id}`) });

  return (
    <div className="trd-side" data-testid="trends-side">
      <SideCard title={T("trd_ui_signals")} help="trd_ui_help_signals" testid="trd-signals">
        <input type="search" className="trd-search" aria-label={T("trd_ui_search")} placeholder={T("trd_ui_search")} value={st.search}
          data-testid="trd-search" onChange={(e) => st.set({ search: e.target.value })} />
        <Seg<"loop" | "source"> value={st.groupBy} options={["loop", "source"]} label={T("trd_ui_by")} small stretch testid="trd-by"
          fmt={(v) => T(`trd_ui_by_${v}`)} onChange={(v) => st.set({ groupBy: v })} help="trd_ui_help_by" />
        <label className="trd-chk" title={T("trd_ui_help_only_active")}>
          <input type="checkbox" checked={st.onlyActive} disabled={!activeTag} onChange={(e) => st.set({ onlyActive: e.target.checked })} />
          {T("trd_ui_only_active", { tag: activeTag ?? "–" })}<LabelHelp text="trd_ui_help_only_active" />
        </label>
        <div className="trd-tree" data-testid="trd-tree">
          {groups.map((g) => (
            <div key={g.key} className="trd-grp">
              <button type="button" className="trd-gh" aria-expanded={!closed[g.key]} onClick={() => setClosed({ ...closed, [g.key]: !closed[g.key] })}>
                <span aria-hidden="true">{closed[g.key] ? "▸" : "▾"}</span>{g.title}
                <span className="muted trd-gn">{g.items.filter((s) => chk.has(s.ref)).length}/{g.items.length}</span>
              </button>
              {!closed[g.key] && g.items.map((s) => (
                <label key={s.ref} className="trd-item" title={`${s.ref}${s.unit ? ` [${s.unit}]` : ""}`}>
                  <input type="checkbox" aria-label={s.ref} checked={chk.has(s.ref)} onChange={() => st.toggle(s.ref, sel.checked)} />
                  <span className="trd-sw" style={{ borderTopColor: s.color, borderTopStyle: s.dash ? "dashed" : "solid" }} />
                  <span className="trd-iname">{st.groupBy === "loop" && s.role && s.role !== "DV" ? s.role : s.column}</span>
                  {st.groupBy === "loop" && <span className="muted trd-isrc">{s.role === "DV" || !s.role ? "" : s.column === s.role ? "" : s.column}</span>}
                </label>
              ))}
            </div>
          ))}
          {!groups.length && <p className="muted trd-none">{T("trd_ui_tree_none")}</p>}
        </div>
        <div className="trd-selrow">
          <span className="muted">{T("trd_ui_sel_n", { n: sel.checked.length })}</span>
          <button type="button" className="link" onClick={() => st.set({ checked: [] })}>{T("trd_ui_clear")}</button>
        </div>
      </SideCard>

      <SideCard title={T("trd_ui_calc")} help="trd_ui_help_calc" testid="trd-calc">
        {st.calcs.map((x) => (
          <div key={x.id} className="trd-calcrow" data-testid="trd-calc-row">
            <label className="trd-item"><input type="checkbox" aria-label={x.name} checked={chk.has(`calc:${x.id}`)} onChange={() => st.toggle(`calc:${x.id}`, sel.checked)} />
              <span className="trd-sw" style={{ borderTopColor: sel.allInfo.get(`calc:${x.id}`)?.color }} /><b>{x.name}</b></label>
            <code className="trd-expr" title={x.expr}>= {x.expr}</code>
            <button type="button" className="link" onClick={() => rm(x.id)} aria-label={`${T("trd_ui_calc_del")} ${x.name}`}>{T("trd_ui_calc_del")}</button>
          </div>))}
        {!form
          ? <button type="button" className="btn trd-calcbtn" title={T("trd_ui_calc_t")} data-testid="trd-calc-open" onClick={() => setForm(true)}>
            ƒ {T("trd_ui_calc_btn")} <span className="muted">{T("trd_ui_calc_eg")}</span></button>
          : (
            <div className="trd-calcform" data-testid="trd-calc-form">
              <label className="field"><span>{T("trd_ui_calc_name")}</span><input type="text" value={c.name} aria-label={T("trd_ui_calc_name")} onChange={(e) => setC({ ...c, name: e.target.value })} /></label>
              <label className="field wide"><span>{T("trd_ui_calc_expr")}<LabelHelp text="trd_ui_calc_expr_help" /></span>
                <textarea rows={2} value={c.expr} aria-label={T("trd_ui_calc_expr")} data-testid="trd-calc-expr" placeholder="[A:SP] - [A:PV]" onChange={(e) => setC({ ...c, expr: e.target.value })} /></label>
              <label className="field"><span>{T("trd_ui_calc_unit")}</span><input type="text" value={c.unit} aria-label={T("trd_ui_calc_unit")} onChange={(e) => setC({ ...c, unit: e.target.value })} /></label>
              <select aria-label={T("trd_ui_calc_insert")} value="" onChange={(e) => e.target.value && setC({ ...c, expr: `${c.expr}${c.expr && !/[\s(]$/.test(c.expr) ? " " : ""}[${e.target.value}]` })}>
                <option value="">{T("trd_ui_calc_insert")}</option>
                {sel.sigs.map((s) => <option key={s.ref} value={s.ref}>{s.loop ? `${s.loop}.${s.label}` : s.column} ({s.sourceName})</option>)}
              </select>
              {test?.error && <p className="trd-err" role="alert" data-testid="trd-calc-err">{test.error}</p>}
              {test && !test.error && !test.refs.length && <p className="trd-err">{T("trd_ui_calc_noref")}</p>}
              <div className="trd-calcact">
                <button type="button" className="btn primary" disabled={!test || !!test.error || !test.refs.length || nameBad} data-testid="trd-calc-add" onClick={add}>{T("trd_ui_calc_add")}</button>
                <button type="button" className="btn" onClick={() => setForm(false)}>{T("trd_ui_cancel")}</button>
              </div>
            </div>)}
      </SideCard>
    </div>
  );
}
