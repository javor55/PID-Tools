// Záložka Diagnostika (M20): záznam s úseky A / B (sdílený trend.js, režim „ab“), výkon smyčky (A, volitelně B),
// oscilace a ventil (stikce, hystereze), grafy korelace, MV–PV, MV–poloha a nelinearita; panel: úseky a možnosti.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiError, binary, request } from "../api/client";
import type { components } from "../api/schema";
import { series, unframe } from "../api/signals";
import { LineChart, type Series } from "../components/LineChart";
import { CheckSetting } from "../components/Fields";
import { Trend } from "../components/Trend";
import { useSettings, useWs } from "../data";
import { useT } from "../i18n";
import { decimate, pick, range, timeUnit } from "../lib/series";
import { type DiagWin, useUi } from "../store";

type Diagnostics = components["schemas"]["Diagnostics"];
type Win = [number, number];
const TXT = ["mode", "h_mode", "common", "inputs", "zoom", "zoom_all", "zoom_win", "zoom_note", "excluded", "m_all",
  "m_mv", "m_dv", "resid", "r_win", "r_full", "model", "win", "drag_win", "start", "end", "zoom_one", "del", "add", "time"];
const C_A = "#1f5fa8", C_B = "#7c3aed";
const g = (x: unknown, n: number) => (typeof x === "number" && Number.isFinite(x) ? String(+x.toPrecision(n)) : "—");
const f = (x: unknown, n: number) => (typeof x === "number" && Number.isFinite(x) ? x.toFixed(n) : "—");

/** Úseky A / B a porovnání: stav prohlížeče podle záznamu (výchozí A = celý záznam, B = druhá polovina). */
export function useDiagWin(): DiagWin | null {
  const ws = useWs().data;
  const diag = useUi((s) => s.diag);
  const dur = ws?.has_data ? ws.duration ?? 0 : 0;
  const key = `${ws?.fname}|${ws?.n}|${dur}`;
  const stored = diag?.key === key ? diag : null;
  return useMemo(() => (!dur ? null : stored ?? { key, a: [0, dur] as Win, b: [dur / 2, dur] as Win, cmp: false }), [dur, key, stored]);
}

/** Diagnostika úseku z API (nepřepočítává se při návratu na záložku; po změně nastavení / modelu se načte znovu). */
export function useDiag(w: Win | null, enabled = true) {
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  const st = useSettings().data;
  const integ = typeof st?.diag_integ === "boolean" ? st.diag_integ : undefined;
  return useQuery({
    queryKey: ["ws", wid, "diag", w, integ, ws?.pv, ws?.mv, ws?.pos, ws?.n, ws?.rng],
    enabled: !!wid && !!w && !!ws?.has_data && enabled, retry: false, placeholderData: keepPreviousData,
    queryFn: () => request<Diagnostics>("GET", `/workspaces/${wid}/diagnostics?a=${w![0]}&b=${w![1]}`
      + (integ === undefined ? "" : `&integ=${integ}`)),
  });
}

function RecordTrend({ win }: { win: DiagWin }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const setDiag = useUi((s) => s.setDiag);
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const grid = useQuery({
    queryKey: ["ws", wid, "grid", ws?.pv, ws?.mv, ws?.sp, ws?.dists, ws?.n], enabled: !!wid && !!ws?.has_data, staleTime: Infinity,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/signals?source=grid`)),
  });
  const data = useMemo(() => {
    if (!ws || !grid.data) return null;
    const { meta, blob } = grid.data;
    const pv = series(meta, blob, "pv"), mv = series(meta, blob, "mv"), sp = series(meta, blob, "sp");
    if (!pv || !mv) return null;
    const t = pv.t, n = t.length, idx = decimate(n, pv.v);
    const [lo, hi] = range(pv.v, sp?.v);
    const u = (x: unknown) => (x ? ` [${String(x)}]` : "");
    const [ml, mh] = range(mv.v);
    const rows = [
      { id: "PV", kind: "pv", title: `PV · ${ws.pv}${u(st.u_pv)}`, color: "#1f5fa8", y: pick(pv.v, idx), lo, hi, h: 170,
        lines: sp ? [[pick(sp.v, idx), "#9aa5b1", "5 4", 1.3, "SP"]] : [] },
      { id: "MV", kind: "sig", title: `MV · ${ws.mv}${u(st.u_mv)}`, color: "#c2410c", y: pick(mv.v, idx), lo: ml, hi: mh, h: 100, lines: [] }];
    const T_end = t[n - 1];
    const clock = ws.origin ? Date.parse(ws.origin.replace(" ", "T") + "Z") + meta.tmin * 1000 : null;
    return {
      key: "diag_trend", view_key: `diag|${ws.fname}|${n}`, T: T_end, unit: timeUnit(T_end), clock: Number.isFinite(clock) ? clock : null,
      dec: lang === "cs" ? "," : ".", dark: document.documentElement.dataset.theme === "dark",
      txt: Object.fromEntries(TXT.map((k) => [k, T("mw_" + k)])), mode: "ab", t: pick(t, idx), step: ws.Ts, rows, excl: [],
      bar: { title: T("diag_rec_title"), note: T("diag_rec_help"), zoom: true },
      ab: { a: win.a, b: win.cmp ? win.b : null, ca: C_A, cb: C_B, la: T("seg_a"), lb: T("seg_b") },
    };
  }, [ws, grid.data, st.u_pv, st.u_mv, win, T, lang]);
  if (!data) return <div className="card muted">…</div>;
  return <Trend data={data} testid="diag-trend" onWins={(w) => {
    if (w.ab) setDiag({ ...win, a: w.ab.a, b: w.ab.b ?? win.b });
  }} />;
}

const KPI_ROWS = ["std", "iae", "travel", "rev", "lim", "harris", "osc"] as const;

function Performance({ win }: { win: DiagWin }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const a = useDiag(win.a);
  const b = useDiag(win.b, win.cmp);
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");
  const label = { std: T("kpi_std", { u: uPv }), iae: T("kpi_iae_h", { u: uPv }), travel: T("kpi_travel_h", { u: uMv }),
    rev: T("kpi_rev_h"), lim: T("kpi_at_lim"), harris: T("kpi_harris"), osc: T("kpi_osc") };
  const cell = (d: Diagnostics, r: (typeof KPI_ROWS)[number]) => {
    const k = d.kpis as Record<string, number | null> & { osc?: { osc: boolean; period: number | null } };
    switch (r) {
      case "std": return g(k.std_e, 4);
      case "iae": return g(k.iae_h, 4);
      case "travel": return g(k.travel_h, 4);
      case "rev": return g(k.rev_h, 3);
      case "lim": return `${f(k.at_lim, 1)} %`;
      case "harris": return f(k.harris, 2);
      default: return k.osc?.osc ? T("yes_period", { p: f(k.osc.period, 0) }) : T("no");
    }
  };
  const cols: [string, string, Diagnostics | undefined][] = [["a", T("seg_a"), a.data]];
  if (win.cmp && b.data && !b.isError) cols.push(["b", T("seg_b"), b.data]);
  return (
    <div className="card" data-testid="diag-perf">
      <h3>{T("perf_title")}</h3>
      <div className="muted small">{T("perf_help")}</div>
      {a.isError ? <div className="warn small" data-testid="diag-short">{T("err_short")}</div> : (
        <table className="tbl"><thead><tr><th />{cols.map(([id, n]) => <th key={id}>{n}</th>)}</tr></thead>
          <tbody>{KPI_ROWS.map((r) => (
            <tr key={r}><td>{label[r]}</td>
              {cols.map(([id, , d]) => <td key={id} className="mono" data-testid={`diag-kpi-${r}-${id}`}>{d ? cell(d, r) : "…"}</td>)}</tr>))}
          </tbody></table>)}
      {win.cmp && b.isError && <div className="warn small">{T("seg_b")}: {T("err_short")}</div>}
    </div>
  );
}

function Valve({ d }: { d: Diagnostics }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");
  const v = d.valve as { osc: { osc: boolean; period: number | null; amp: number | null; r: number | null };
    stic: { ratio: number | null }; verdict: string | null };
  const ws = useWs().data;
  const hyst = d.hysteresis;
  return (
    <div className="card stack" data-testid="diag-valve">
      <h3>{T("osc_title")}</h3>
      {v.osc.osc
        ? <div className="warn small" data-testid="diag-osc">〰 {T("osc_found", { p: f(v.osc.period, 0), a: g(v.osc.amp, 3), u: uPv, r: f(v.osc.r, 1) })}</div>
        : <div className="ok small" data-testid="diag-osc">✓ {T("osc_none")}</div>}
      {v.verdict && <div className={`small ${v.verdict === "likely" ? "err" : ""}`} data-testid="diag-stic">
        {T("stic_" + v.verdict, { r: f(v.stic.ratio, 2) })}</div>}
      {ws?.pos
        ? <div className="small" data-testid="diag-hyst">{T("hyst")}: <b className="mono">{hyst === null || hyst === undefined ? "—" : `${g(Math.abs(hyst), 3)} ${uMv}`}</b></div>
        : <div className="muted small">{T("pos_missing")}</div>}
    </div>
  );
}

const VIEWS = ["ccf", "phase", "pos", "nl"] as const;

function NonlinearityView({ d, onGainSched }: { d: Diagnostics; onGainSched: () => void }) {
  const T = useT();
  const ws = useWs().data;
  const nl = d.nonlinearity as null | { gains: { t: number; dmv: number; gain: number; ratio: number; from_e: number; to_e: number }[];
    spread: number | null; ref: number; param: string; integ: boolean };
  if (!nl) return <div className="muted small" data-testid="nl-need-model">{T("need_model")}</div>;
  const gains = nl.gains;
  if (gains.length < 2 || nl.spread === null) return <div className="muted small" data-testid="nl-few">{T("nl_few")}</div>;
  const mid = (q: (typeof gains)[number]) => (q.from_e + q.to_e) / 2;
  const up = gains.filter((q) => q.dmv > 0), dn = gains.filter((q) => q.dmv < 0);
  const xs = gains.map(mid), x0 = Math.min(...xs), x1 = Math.max(...xs);
  const ser: Series[] = [
    { name: "↑", x: up.map(mid), y: up.map((q) => q.gain), color: "#1f5fa8", dots: true, width: 8 },
    { name: "↓", x: dn.map(mid), y: dn.map((q) => q.gain), color: "#c2410c", dots: true, width: 8 },
    { name: nl.param, x: [x0, x1], y: [nl.ref, nl.ref], color: "#94a3b8", dash: "2 3", legend: false }];
  const mean = (a: number[]) => a.reduce((s, x) => s + x, 0) / a.length;
  const ratio = up.length && dn.length ? mean(up.map((q) => q.gain)) / mean(dn.map((q) => q.gain)) : null;
  const sp = nl.spread;
  return (
    <div className="stack">
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 320px" }}>
          <table className="tbl" data-testid="nl-table"><thead><tr><th>{T("nl_time")}</th><th>{T("nl_from")}</th><th>{T("nl_to")}</th>
            <th>{T("nl_dir")}</th><th>{T("nl_gain")}</th><th>{T("nl_ratio")}</th></tr></thead>
            <tbody>{gains.map((q, i) => (
              <tr key={i} data-testid={`nl-row-${i}`}><td className="mono">{f(q.t, 0)}</td><td className="mono">{g(q.from_e, 4)}</td>
                <td className="mono">{g(q.to_e, 4)}</td><td>{q.dmv > 0 ? "↑" : "↓"}</td><td className="mono">{g(q.gain, 4)}</td>
                <td className="mono">{f(q.ratio, 2)}</td></tr>))}</tbody></table>
        </div>
        <div style={{ flex: "1 1 320px" }}>
          <LineChart series={ser} height={260} xLabel={`MV${ws?.mv ? ` · ${ws.mv}` : ""}`} yLabel={nl.param} testid="nl-chart" />
        </div>
      </div>
      {sp > 1.5 ? <div className="warn small" data-testid="nl-verdict">⚠ {T("nl_warn", { s: f(sp, 1) })}</div>
        : <div className="ok small" data-testid="nl-verdict">✓ {T("nl_ok", { s: f(sp, 2) })}</div>}
      {sp > 1.5 && !nl.integ && <div><button className="btn" onClick={onGainSched} data-testid="nl-to-gs">{T("nl_to_gs")}</button></div>}
      {ratio !== null && Math.abs(ratio - 1) > 0.3 && <div className="small" data-testid="nl-dir-warn">↕ {T("nl_dir_warn", { r: f(ratio, 2) })}</div>}
      <div className="muted small">{T("nl_help")}</div>
    </div>
  );
}

function Charts({ d }: { d: Diagnostics }) {
  const T = useT();
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const setTab = useUi((s) => s.setTab);
  const setApcTech = useUi((s) => s.setApcTech);
  const [view, setView] = useState<(typeof VIEWS)[number]>("ccf");
  const v = d.valve as { stic: { lags: number[]; ccf: (number | null)[] } };
  const cur = view === "pos" && !d.position ? "ccf" : view;
  const mvLab = `MV${st.u_mv ? ` [${String(st.u_mv)}]` : ""}`;
  const names = { ccf: d.integ ? T("ccf_title_d") : T("ccf_title"), phase: T("phase_title"), pos: T("pos_title"), nl: T("nl_title") };
  return (
    <div className="card stack" data-testid="diag-charts">
      <div className="row" role="tablist">
        {VIEWS.filter((x) => x !== "pos" || d.position).map((x) => (
          <button key={x} role="tab" aria-selected={x === cur} className={x === cur ? "btn primary" : "btn"}
            data-testid={`diag-view-${x}`} onClick={() => setView(x)}>{names[x]}</button>))}
      </div>
      {cur === "ccf" && (
        <>
          <LineChart series={[{ name: T("ccf"), x: v.stic.lags, y: v.stic.ccf.map((x) => x ?? NaN), color: "#1f5fa8" }]} height={260}
            xLabel={T("lag_s")} yLabel={T("ccf")} testid="diag-ccf" />
          <div className="muted small">{T("osc_help")}</div>
        </>)}
      {cur === "phase" && (
        <LineChart series={[{ name: "MV–PV", x: d.phase.x.map((x) => x ?? NaN), y: d.phase.y.map((x) => x ?? NaN), color: "#1f5fa8", dots: true, width: 3 }]}
          height={300} xLabel={`${mvLab}${ws?.mv ? ` · ${ws.mv}` : ""}`} yLabel={d.integ ? "dPV/dt" : `PV${st.u_pv ? ` [${String(st.u_pv)}]` : ""}`}
          testid="diag-phase" />)}
      {cur === "pos" && d.position && (
        <LineChart series={[{ name: T("pos_title"), x: d.position.x.map((x) => x ?? NaN), y: d.position.y.map((x) => x ?? NaN), color: "#c2410c",
          dots: true, width: 3 }]} height={300} xLabel={mvLab} yLabel={T("col_pos")} testid="diag-pos" />)}
      {cur === "nl" && <NonlinearityView d={d} onGainSched={() => { setApcTech("gainsched"); setTab("apc"); }} />}
    </div>
  );
}

export function DiagMain() {
  const T = useT();
  const ws = useWs().data;
  const win = useDiagWin();
  const a = useDiag(win?.a ?? null);
  if (!ws?.has_data || !win) return <div className="card muted" data-testid="no-data">{T("ui_no_data")}</div>;
  return (
    <div className="stack">
      <RecordTrend win={win} />
      <Performance win={win} />
      {a.isError && a.error instanceof ApiError && a.error.status === 422 ? null : a.data && <Valve d={a.data} />}
      {a.data && <Charts d={a.data} />}
    </div>
  );
}

export function DiagSide() {
  const T = useT();
  const ws = useWs().data;
  const win = useDiagWin();
  const setDiag = useUi((s) => s.setDiag);
  const a = useDiag(win?.a ?? null);
  if (!ws?.has_data || !win) return null;
  return (
    <div className="stack">
      <section>
        <h3>{T("dk_sec_diag_seg")}</h3>
        <div className="muted small">{T("diag_intro")} {T("diag_ab_hint")}</div>
        <label className="small" title={T("h_perf_compare")}>
          <input type="checkbox" checked={win.cmp} data-testid="diag-cmp" onChange={(e) => setDiag({ ...win, cmp: e.target.checked })} />{" "}
          {T("perf_compare")}
        </label>
      </section>
      <section>
        <h3>{T("diag_opts")}</h3>
        <CheckSetting k="diag_integ" label={T("diag_integ")} title={T("h_diag_integ")} def={a.data?.integ ?? false} />
      </section>
    </div>
  );
}
