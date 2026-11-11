// Záložka Ladění (M16, M17) podle návrhu: nahoře lišta pohledu (scénář v čase / frekvenční analýza / všechny metody),
// odezva scénáře s měřicími kurzory, ukazatele kvality (Set 1, Set 2, Návrh) a srovnání metod; vpravo karty Metoda
// ladění, Návrh a sady v PLC, Scénář simulace, Robustnost, Blok PIDConL a Historie návrhů.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { series } from "../api/signals";
import { CheckSetting, NumSetting, SelectSetting } from "../components/Fields";
import { LabelHelp, Md, PrimaryAction, Seg, SideCard } from "../components/Ui";
import { useSettings, usePatchSettings, useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { dur } from "../lib/format";
import { useUi } from "../store";
import "../styles/tuning.css";
import { useApc } from "./apc/common";
import { type Line, ScenarioChart } from "./TuningChart";
import { CompareCard, FreqCard, ScenarioEvents, ScenarioSide, UNITS, fnum, unitOf, useFreq, useScenario, useSim } from "./TuningMore";
import { type Suggestion, type Unit, type View, settingsSig, useCalc, useTun, useTunSync } from "./tuningState";

type TuningInfo = components["schemas"]["TuningInfo"];
type ModelState = components["schemas"]["ModelState"];
type FreqSet = components["schemas"]["FreqSet"];
type Kpi = Record<string, unknown> | null;

const FAST = (m: string) => m !== "OPT";                          // rychlé metody (pravidla) se přepočítají samy

/** Metoda zvolená v panelu (jinak výchozí podle API). */
function useMethod(info: TuningInfo | undefined) {
  const m = useTun((s) => s.method);
  return m ?? info?.default_method ?? "SIMC";
}

// ---------------------------------------------------------------- hlavní plocha
export function TuningMain() {
  useTunSync();
  const T = useT();
  const dec = useUi((s) => s.lang) === "cs" ? "," : ".";
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const info = useWsQuery<TuningInfo>("tuning", "/tuning");
  const model = useWsQuery<ModelState>("model", "/model");
  const reco = useApc<components["schemas"]["Recommendation"][]>("reco", "/apc/recommend");
  const setTab = useUi((s) => s.setTab);
  const setTech = useUi((s) => s.setApcTech);
  const { view, unit, measure, sug, set } = useTun();
  const { sim, curves, preview, spread } = useSim();
  const freq = useFreq(preview);
  const sc = useScenario();

  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (info.isError || (info.data === undefined && !info.isLoading)) return <div className="card muted">{T("need_model")}</div>;
  if (!info.data) return <div className="card muted">…</div>;
  const T_end = sim.data?.T_end ?? 0;
  const u = unitOf(unit, T_end);
  const k = (sim.data?.kpis ?? {}) as Record<string, Kpi>;
  const cur0 = model.data?.current as { code: string; p: number[] } | null | undefined;
  const names = model.data?.results.find((r) => r.code === cur0?.code)?.names ?? [];
  const samp = Number(st.samp ?? 1);
  const items = reco.data ?? [];

  return (
    <div className="tn-main">
      <div className="tn-bar">
        <div className="tn-barrow">
          <Seg<View> value={view} options={["time", "freq", "all"]} onChange={(v) => set({ view: v })} label={T("tn_view")}
            fmt={(v) => T("tn_view_" + v)} testid="tun-view" help="h_tn_view" />
          <span className="tn-cmp" dangerouslySetInnerHTML={{ __html: T("tn_cmp_line", { a: T("dk_suggest"), b: T("set_2") }) }} />
          <div className="tn-right tn-axis">
            <span>{T("ui_tuning_axis")}</span>
            <select value={unit} aria-label={T("time_unit")} title={T("h_chart_tunit")} data-testid="tun-unit" onChange={(e) => set({ unit: e.target.value as Unit })}>
              <option value="auto">auto ({unitOf("auto", T_end)})</option>
              {(["s", "min", "h"] as const).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
            <button type="button" className="tn-btn" aria-pressed={measure} data-testid="tun-measure" title={T("dk_ch_measure")}
              onClick={() => set({ measure: !measure, cur: [] })}>{T("dk_chb_measure")}</button>
          </div>
        </div>
        {view !== "all" && (
          <div className="tn-modelline" data-testid="tun-model">
            {T("model_" + info.data.model)}
            {cur0 ? " · " + cur0.p.map((x, i) => `${names[i] ?? ""} = ${fnum(Math.abs(x) < 1e-9 ? 0 : x, dec, 4)}`).join(", ") : ""}
            {" · " + T("samp_note", { s: fnum(samp, dec, 6), h: fnum(samp / 2, dec, 6) })}
            {items.length > 0 && <span className="tn-hint" data-testid="tun-apc-hint"> · 💡 {T("g_tuning_hint", {
              m: [...new Set(items.map((r) => T("apc_" + r.kind)))].join(", ") })}{" "}
              <button type="button" className="link" onClick={() => { setTech(items[0].kind); setTab("apc"); }}>
                {T("g_open", { m: "APC" })}</button></span>}
          </div>)}
      </div>

      {view === "time" && (
        <>
          <ResponseCard curves={curves.data} sc={sc.data} T_end={T_end} u={u} spread={spread} sug={sug} dec={dec} />
          <KpiCard k={k} freq={freq.data} info={info.data} sug={sug} dec={dec} />
          <CompareCard />
          <ScenarioEvents />
        </>
      )}
      {view === "freq" && freq.data && <FreqCard data={freq.data} />}
      {view === "all" && <CompareCard withRun={false} />}
    </div>
  );
}

// ---- odezva scénáře
function ResponseCard({ curves, sc, T_end, u, spread, sug, dec }: {
  curves: ReturnType<typeof useSim>["curves"]["data"]; sc: components["schemas"]["Scenario"] | undefined; T_end: number;
  u: "s" | "min" | "h"; spread: boolean; sug: Suggestion | null; dec: string;
}) {
  const T = useT();
  const st = useSettings().data ?? {};
  const { measure, cur, set } = useTun();
  const preview = !!sug;
  const get = (key: string) => (curves ? series(curves.meta, curves.blob, key) : null);
  const mk = (name: string, key: string, color: string, dash?: string, width?: number): Line[] => {
    const x = get(key);
    return x ? [{ name, x: x.t, y: x.v, color, dash, width }] : [];
  };
  const pv: Line[] = [];
  if (curves && spread) curves.meta.sigs.map((x) => x.name).filter((n) => n.startsWith("pv_x") && n.endsWith("unc_variants"))
    .forEach((n, i) => pv.push(...mk(T("unc_variants"), n, "var(--pid-soft)", undefined, 1).map((l) => ({ ...l, legend: i === 0 }))));
  if (curves) curves.meta.sigs.map((x) => x.name).filter((n) => /^pv_x\d+_(new_err|set2_noff)$/.test(n)).forEach((n) => {
    const nm = n.endsWith("new_err") ? "new_err" : "set2_noff";
    pv.push(...mk(T(nm), n, nm === "new_err" ? "var(--pid-set2)" : "var(--pid-sp)", "2 3", 1.4));
  });
  pv.push(...mk("SP", "sp", "var(--pid-text)", "6 4", 1.5), ...mk("Set 1", "pv_1", "var(--pid-set1)", "2 3", 1.5),
    ...mk("Set 2", "pv_2", preview ? "var(--pid-sp)" : "var(--pid-pv)", preview ? "5 3" : undefined, preview ? 1.8 : 2.4));
  if (preview) pv.push(...mk(T("dk_suggest"), "pv_sug", "var(--tn-sug)", undefined, 2.5));
  const mv: Line[] = [...mk("Set 1", "mv_1", "var(--pid-set1)", "2 3", 1.4),
    ...mk("Set 2", "mv_2", preview ? "var(--pid-sp)" : "var(--pid-mv)", preview ? "5 3" : undefined, preview ? 1.6 : 2.2),
    ...(preview ? mk(T("dk_suggest"), "mv_sug", "var(--pid-mv)", undefined, 2.2) : [])];
  const rows = (sc?.rows ?? []) as [boolean, string, string, number, number | null][];
  const markers = rows.filter((r) => r[0] && r[1] !== "SP" && r[4] !== null).map((r) => ({ t: r[4] as number, label:
    r[1].startsWith("M") ? "DV" : T("tg_" + r[1]).split(" ").slice(0, 1).join(" ") }));
  const mainName = preview ? T("dk_suggest") : "Set 2";
  const legend = pv.filter((l) => l.legend !== false).map((l, i, a) => a.findIndex((x) => x.name === l.name) === i && l);
  const kindNote = sc ? `${T("dk_sc_" + sc.kind)} · ${T("sim_len")} ${dur(T_end, dec)}` : "";
  return (
    <section className="tn-card" data-testid="response">
      <div className="tn-head">
        <h2>{T("tn_chart")}</h2><span className="tn-sub">{kindNote}</span>
        <span className="tn-legend tn-right">{legend.map((l) => l && (
          <span key={l.name}><i style={{ borderTopColor: l.color, borderTopStyle: l.dash ? "dashed" : "solid",
            borderTopWidth: l.dash ? 2 : 3 }} />{l.name}{l.name === mainName && sug ? ` (${T("m_" + sug.method)})` : ""}</span>))}
        </span>
      </div>
      <ScenarioChart pv={pv} mv={mv} markers={markers} unitSec={UNITS[u]} unitName={u} cur={cur} measure={measure} dec={dec}
        pvLabel={`PV ${String(st.u_pv ?? "")}`.trim()} mvLabel={`MV ${String(st.u_mv ?? "")}`.trim()} mainName={mainName}
        onCursor={(t) => set({ cur: cur.length >= 2 ? [t] : [...cur, t] })} testid="resp-pv" />
      {measure && cur.length === 0 && <div className="tn-note">{T("ui_tuning_measure_hint")}</div>}
    </section>
  );
}

// ---- ukazatele kvality: Set 1 / Set 2 / Návrh, lepší hodnota v řádku zvýrazněná
type KRow = { key: string; label: string; val: (n: string) => number | null; text: (n: string) => string; better?: "low" | "none" };

function KpiCard({ k, freq, info, sug, dec }: { k: Record<string, Kpi>; freq: FreqSet[] | undefined; info: TuningInfo;
  sug: Suggestion | null; dec: string }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");
  const cols = [["1", "Set 1"], ["2", "Set 2"], ...(sug ? [["sug", `${T("dk_suggest")} · ${T("m_" + sug.method)}`]] : [])]
    .filter(([n]) => n in k);
  if (!cols.length) return null;
  const val = (n: string, f: (r: Record<string, unknown>) => unknown): number | null => {
    const r = k[n];
    const x = r ? Number(f(r)) : NaN;
    return Number.isFinite(x) ? x : null;
  };
  const step = (r: Record<string, unknown>) => (r.step ?? {}) as Record<string, number | null>;
  const fr = (n: string) => freq?.find((x) => x.name === (n === "sug" ? "sug" : `set${n}`));
  const pid = (n: string) => (n === "sug" ? (sug ? { g: sug.Kc, ti: sug.Ti } : null)
    : (() => { const s = info.sets.find((x) => String(x.n) === n); return s ? { g: s.gain, ti: s.ti } : null; })());
  const dash = "–";
  const num = (x: number | null, p = 3, suf = "") => (x === null ? dash : fnum(x, dec, p) + suf);
  const rows: KRow[] = [
    { key: "pid", label: "Gain / TI", better: "none", val: () => null,
      text: (n) => { const p = pid(n); return p ? `${fnum(p.g, dec, 3)} / ${dur(p.ti, dec)}` : dash; } },
    { key: "t90", label: T("kpi_t90"), val: (n) => val(n, (r) => step(r).t90), text: (n) => dur(val(n, (r) => step(r).t90), dec) },
    { key: "over", label: T("kpi_over"), val: (n) => { const x = val(n, (r) => step(r).over); return x === null ? null : Math.abs(x); },
      text: (n) => num(val(n, (r) => step(r).over), 3, " %") },
    { key: "settle", label: T("kpi_settle"), val: (n) => val(n, (r) => step(r).settle),
      text: (n) => dur(val(n, (r) => step(r).settle), dec) },
    { key: "iae", label: "IAE [%·s]", val: (n) => val(n, (r) => r.iae), text: (n) => num(val(n, (r) => r.iae), 4) },
    { key: "dev", label: T("kpi_maxdev", { u: uPv }), val: (n) => val(n, (r) => r.maxdev), text: (n) => num(val(n, (r) => r.maxdev), 3) },
    { key: "travel", label: T("kpi_mvtravel", { u: uMv }), val: (n) => val(n, (r) => r.mv_travel),
      text: (n) => num(val(n, (r) => r.mv_travel), 3) },
    { key: "range", label: T("kpi_mvrange", { u: uMv }), better: "none", val: () => null,
      text: (n) => num(val(n, (r) => r.mv_range), 3) },
    { key: "rev", label: T("kpi_rev"), val: (n) => val(n, (r) => r.reversals), text: (n) => num(val(n, (r) => r.reversals), 3) },
    { key: "rob", label: "Ms / GM / PM", val: (n) => { const f = fr(n); return f?.stable && f.Ms != null ? f.Ms : null; },
      text: (n) => { const f = fr(n); return f?.stable ? `${num(f.Ms ?? null, 3)} / ${num(f.GM ?? null, 3)} / ${f.PM == null ? dash : f.PM.toFixed(0) + "°"}` : dash; } },
  ];
  const best = (r: KRow) => {
    if (r.better === "none") return new Set<string>();
    const v = cols.map(([n]) => [n, r.val(n)] as const).filter((x): x is readonly [string, number] => x[1] !== null);
    if (v.length < 2) return new Set<string>();
    const lo = Math.min(...v.map((x) => x[1]));
    if (v.every((x) => Math.abs(x[1] - lo) < 1e-9 * Math.max(1, Math.abs(lo)))) return new Set<string>();
    return new Set(v.filter((x) => Math.abs(x[1] - lo) < 1e-9 * Math.max(1, Math.abs(lo))).map((x) => x[0]));
  };
  return (
    <section className="tn-card" data-testid="kpi-card">
      <div className="tn-head"><h2>{T("tn_kpi")}<Qm text={T("ui_tuning_help_kpi")} /></h2><span className="tn-sub">{T("tn_kpi_note")}</span></div>
      <div className="tn-scroll">
        <table className="tn-tbl kpi" data-testid="kpis"><thead><tr><th scope="col" />
          {cols.map(([n, lab]) => <th key={n} scope="col" className={"r " + (n === "sug" ? "sug" : "")}>{lab}</th>)}</tr></thead>
          <tbody>{rows.map((r) => {
            const b = best(r);
            return <tr key={r.key}><th scope="row">{r.label}</th>
              {cols.map(([n]) => <td key={n} className={"r mono" + (b.has(n) ? " best" : "")}>{r.text(n)}</td>)}</tr>;
          })}</tbody></table>
      </div>
    </section>
  );
}

const Qm = LabelHelp;

// ---------------------------------------------------------------- pravý panel
type Pid3 = { Kc: number; Ti: number; Td: number };

export function TuningSide() {
  useTunSync();
  const T = useT();
  const wid = useUi((s) => s.wid);
  const dec = useUi((s) => s.lang) === "cs" ? "," : ".";
  const setTab = useUi((s) => s.setTab);
  const qc = useQueryClient();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const ws = useWs().data;
  const info = useWsQuery<TuningInfo>("tuning", "/tuning");
  const model = useWsQuery<ModelState>("model", "/model");
  const calc = useCalc();
  const { sug, err, busy, spread, robust, ffcmp, set } = useTun();
  const { preview, hasUnc } = useSim();
  const freq = useFreq(preview);
  const m = useMethod(info.data);
  const sigNow = `${m}|${settingsSig(st)}`;
  const tried = useRef<string | null>(null);
  // rychlé metody (pravidla) se přepočítají samy, optimalizace (sekundy) až na tlačítko Vypočítat
  useEffect(() => {
    if (!info.data || !FAST(m) || busy) return;
    if ((!sug || (sug.sig !== sigNow && !sug.fromRow && sug.method === m)) && tried.current !== sigNow) {
      tried.current = sigNow;
      void calc(m);
    }
  }, [info.data, m, sigNow, sug, busy]);          // eslint-disable-line react-hooks/exhaustive-deps
  if (!ws?.has_data || !info.data) return null;
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");
  const PR = Number(st.pv_hi ?? 100) - Number(st.pv_lo ?? 0), MR = Number(st.mv_hi ?? 100) - Number(st.mv_lo ?? 0);
  const ctype = String(st.ctype ?? "PI") as "PI" | "PID";
  const crit = String(st.opt_crit ?? "OVS");
  const adv = info.data.d_advice as { rec?: string; key?: string } | null;
  const stale = !!sug && !sug.fromRow && sug.sig !== undefined && sug.sig !== `${sug.method}|${settingsSig(st)}`;
  const chk = (key: string, args: Record<string, unknown>) =>
    T(key, { ...args, m: T("model_" + info.data!.model), th: dur(Number(args.th), dec), T: dur(Number(args.T), dec),
      kk: Number(args.kk ?? 0).toPrecision(3), r: Number(args.r ?? 0).toPrecision(3), g: Number(args.g ?? 0).toPrecision(4) });
  const writeSet = async (n: number, p: Pid3, log?: Record<string, unknown>) => {
    await request("PUT", `/workspaces/${wid}/tuning/sets/${n}`, { ...p, ...(log ? { log } : {}) });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const write = (n: number) => { if (sug) void writeSet(n, { Kc: sug.Kc, Ti: sug.Ti, Td: sug.Td }, { method: T("m_" + sug.method) }); };
  const fq = (n: string) => freq.data?.find((x) => x.name === n);

  return (
    <div className="tn-side">
      <SideCard title={T("tn_sec_method")} help={T("ui_tuning_help_method")} testid="card-method">
        <label className="trow"><span>{T("method")}</span>
          <select value={m} onChange={(e) => set({ method: e.target.value })} data-testid="method">
            {info.data.methods.map((x) => <option key={x} value={x}>{T("m_" + x)}</option>)}
          </select></label>
        <div className="trow"><span>{T("ctrl_type")}</span>
          <Seg<"PI" | "PID"> value={ctype} options={["PI", "PID"]} onChange={(v) => void patch({ ctype: v })} label={T("ctrl_type")}
            small testid="set-ctype" titles={() => T("h_ctype")} /></div>
        {m === "AVG" && <>
          <NumRow k="avg_dpv" label={T("avg_dpv", { u: uPv })} def={+(0.1 * PR).toPrecision(3)} />
          <NumRow k="avg_dmv" label={T("avg_dmv", { u: uMv })} def={+(0.1 * MR).toPrecision(3)} />
        </>}
        {m === "OPT" && <>
          <label className="trow"><span>{T("opt_crit")}</span>
            <select value={crit} data-testid="set-opt_crit" title={T("h_opt_crit")} onChange={(e) => void patch({ opt_crit: e.target.value })}>
              {["MIGO", "IAE", "ISE", "ITAE", "OVS"].map((x) => <option key={x} value={x}>{T("crit_" + x)}</option>)}</select></label>
          {crit !== "MIGO" && <label className="trow"><span>{T("opt_target")}</span>
            <select value={String(st.opt_target ?? "both")} data-testid="set-opt_target" title={T("h_opt_target")}
              onChange={(e) => void patch({ opt_target: e.target.value })}>
              {["scen", "dist", "sp", "both"].map((x) => <option key={x} value={x}>{T("tgt_" + x)}</option>)}</select></label>}
          {crit === "OVS" && <div className="trow"><span>{T("opt_ovs")}</span>
            <Seg<number> value={Number(st.opt_ovs ?? 2)} options={[0, 2, 5, 10]} onChange={(v) => void patch({ opt_ovs: v })}
              label={T("opt_ovs")} small fmt={(x) => `${x} %`} testid="set-opt_ovs" titles={() => T("h_opt_ovs")} /></div>}
          <div className="trow"><span>{T("opt_ms")}</span>
            <Seg<number> value={Number(st.opt_ms ?? 1.6)} options={[1.4, 1.6, 1.8, 2.0]} onChange={(v) => void patch({ opt_ms: v })}
              label={T("opt_ms")} small fmt={(x) => x.toFixed(1)} testid="set-opt_ms" titles={() => T("opt_ms_help")} /></div>
          {ctype === "PID" && <NumRow k="opt_noise" label={T("opt_noise", { u: uMv })} def={+(0.01 * MR).toPrecision(3)} />}
          <CheckSetting k="opt_robust" label={T("opt_robust")} title={T("h_opt_robust_corner")} />
        </>}
        {adv?.rec && <div className="tn-note" data-testid="d-advice"><b>{adv.rec}</b>{adv.key ? ` — ${T(adv.key)}` : ""}</div>}
        <details className="tn-more"><summary>{T("ui_tuning_method_desc")}</summary>
          <Md text={T("mdesc_" + m)} />{m === "OPT" && <Md text={T("cdesc_" + crit)} />}</details>
        {err && <div className="err small">{err}</div>}
        {sug && sug.notes.map((n) => <div key={n.key} className="tn-info" data-testid="sug-note">💡 {T(n.key, n.args)}</div>)}
        {sug && sug.Kc < 0 && <div className="tn-warn">⚠ {T("warn_neg_gain")}</div>}
        {sug && sug.checks.map((c) => <div key={c.key} className="tn-warn" data-testid="sug-check">⚠ {chk(c.key, c.args)}</div>)}
        {!sug ? <div className="tn-note"><Md text={T("dk_calc_hint")} /></div>
          : stale ? <div className="tn-warn">{T("web_stale")}</div>
          : sug.t ? <div className="tn-note ok">✓ {T("web_calc_done", { t: sug.t })}</div> : null}
        <PrimaryAction onClick={() => void calc(m)} disabled={busy} testid="calc" title={T("dk_calc_help")}>
          {busy ? "…" : T("dk_calc")}</PrimaryAction>
      </SideCard>

      <SideCard title={T("tn_sec_sets")} testid="card-sets">
        <table className="tn-sets" data-testid="sets">
          <thead><tr><th scope="col" /><th scope="col" className="sug" title={T("dk_calc_help")}>{T("dk_suggest")}</th>
            <th scope="col" title={T("h_set_1")}>{T("set_1")}</th><th scope="col" title={T("h_set_2")}>{T("set_2")}</th></tr></thead>
          <tbody data-testid="sug-values">{([["Gain", "gain", "Kc", "h_gain"], ["TI [s]", "ti", "Ti", "h_ti"], ["TD [s]", "td", "Td", "h_td"]] as const)
            .map(([lab, key, sk, hk]) => (
              <tr key={key}><th scope="row" title={T(hk)}>{lab}</th>
                <td className="sugv mono">{sug ? fnum(sug[sk], dec, 4) : "—"}</td>
                {info.data!.sets.map((s) => (
                  <td key={s.n}><SetInput value={s[key]} placeholder={s.placeholder} label={`${T("set_" + s.n)} ${lab}`}
                    testid={`set${s.n}-${key}`} onCommit={(x) => {
                      const p = { Kc: s.gain, Ti: s.ti, Td: s.td };
                      void writeSet(s.n, { ...p, [sk]: x });
                    }} /></td>))}
              </tr>))}
          </tbody>
        </table>
        <div className="tn-btns">
          <button type="button" className="tn-btn sug" disabled={!sug} onClick={() => write(2)} data-testid="to-set2">{T("tn_write_s2")}</button>
          <button type="button" className="tn-btn" disabled={!sug} onClick={() => write(1)} data-testid="to-set1">{T("tn_write_s1")}</button>
        </div>
        <div className="tn-note">{T("tn_sets_note")}</div>
        {info.data.sets.map((s) => {
          const f = fq(`set${s.n}`);
          if (!f || f.stable) return null;
          return <div key={s.n} className={s.placeholder ? "tn-info" : "tn-warn"} data-testid={`set${s.n}-unstable`}>
            {s.placeholder ? T(`set${s.n}_placeholder`) : "⚠ " + T("err_unstable", { n: T("set_" + s.n) })}</div>;
        })}
      </SideCard>

      <SideCard title={T("tn_sec_scen")} help={T("ui_tuning_help_scen")} testid="card-scenario"><ScenarioSide /></SideCard>

      <SideCard title={T("tn_sec_rob")} help={T("ui_tuning_help_rob")} testid="card-robust">
        <RobTiles freq={freq.data} sug={!!sug} dec={dec} />
        <label className="tn-check" title={T("h_robust_on")}>
          <input type="checkbox" checked={robust} data-testid="sim-robust" onChange={(e) => set({ robust: e.target.checked })} /> {T("robust_on")}</label>
        <label className="tn-check" title={T("h_spread_on")}>
          <input type="checkbox" checked={spread && hasUnc} disabled={!hasUnc} data-testid="sim-spread"
            onChange={(e) => set({ spread: e.target.checked })} /> {T("spread_on")}</label>
        <label className="tn-check" title={T("h_ff_cmp")}>
          <input type="checkbox" checked={ffcmp} data-testid="sim-ffcmp" onChange={(e) => set({ ffcmp: e.target.checked })} /> {T("ff_cmp")}</label>
      </SideCard>

      <SideCard title={T("tn_blk")} defaultOpen={false} testid="card-block">
        <BlockSettings model={model.data} />
      </SideCard>

      <SideCard title={T("dk_sec_hist")} defaultOpen={false} testid="card-history">
        {info.data.history.length === 0 ? <div className="tn-note">{T("dk_hist_help")}</div> : (
          <ul className="tn-hist" data-testid="history">{info.data.history.slice(0, 20).map((e, i) => {
            const p = { Kc: Number(e.Kc), Ti: Number(e.Ti), Td: Number(e.Td) };
            return <li key={i}><span className="mono">{String(e.time ?? "").slice(-5)} · {String(e.method ?? "")} · {fnum(p.Kc, dec, 4)} / {dur(p.Ti, dec)}
              {e.set ? ` · ${T("set_" + e.set)}` : ""}</span>
              <span className="tn-hbtn">
                <button type="button" className="link" onClick={() => void writeSet(1, p)}>{T("dk_hist_s1")}</button>
                <button type="button" className="link" onClick={() => void writeSet(2, p)}>{T("dk_hist_s2")}</button></span></li>;
          })}</ul>)}
      </SideCard>

      <button type="button" className="btn primary big" onClick={() => setTab("live")} data-testid="to-live">{T("tn_to_live")}</button>
    </div>
  );
}

// ---- prvky panelu
/** Číselné nastavení s popiskem vlevo (řádek karty Metoda ladění). */
function NumRow({ k, label, def }: { k: string; label: string; def: number }) {
  return <div className="trow"><span>{label}</span><NumBare k={k} def={def} min={1e-9} /></div>;
}

/** Číselné pole navázané na klíč nastavení; uloží se po opuštění pole / Enter. */
function NumBare({ k, def, min, step, label }: { k: string; def?: number; min?: number; step?: number; label?: string }) {
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const cur = st[k] ?? def ?? "";
  const ref = useRef<HTMLInputElement>(null);
  return (
    <input ref={ref} type="number" step={step ?? "any"} min={min} className="tn-in" aria-label={label}
      key={`${k}-${String(cur)}`} defaultValue={typeof cur === "number" ? +cur.toPrecision(6) : String(cur)} data-testid={`set-${k}`}
      onBlur={(e) => { const v = e.target.value; if (v !== "" && Number.isFinite(+v) && +v !== Number(cur)) void patch({ [k]: +v }); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

/** Pole sady v PLC: hodnota se zapíše po opuštění pole; zástupné hodnoty (výchozí) se ukážou jako „[z PLC]“. */
function SetInput({ value, placeholder, label, testid, onCommit }: { value: number; placeholder: boolean; label: string; testid: string;
  onCommit: (x: number) => void }) {
  const T = useT();
  return (
    <input type="number" step="any" className="tn-setin" aria-label={label} data-testid={testid} key={`${value}-${placeholder}`}
      defaultValue={placeholder ? "" : +value.toPrecision(5)} placeholder={placeholder ? T("ui_tuning_from_plc") : undefined}
      onBlur={(e) => { const v = e.target.value; if (v !== "" && Number.isFinite(+v) && +v !== value) onCommit(+v); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

function RobTiles({ freq, sug, dec }: { freq: FreqSet[] | undefined; sug: boolean; dec: string }) {
  const T = useT();
  if (!freq) return null;
  const main = freq.find((x) => x.name === (sug ? "sug" : "set2")), ref = freq.find((x) => x.name === (sug ? "set2" : "set1"));
  const refName = sug ? T("set_2") : T("set_1");
  const val = (f: FreqSet | undefined, key: "Ms" | "GM" | "PM", p: number) => (f?.stable && f[key] != null ? fnum(f[key], dec, p) : "—");
  const lvl = (x: number | null | undefined, ok: number, warn: number, low: boolean) => {
    if (x == null) return "bad";
    return (low ? x <= ok : x >= ok) ? "good" : (low ? x <= warn : x >= warn) ? "warn" : "bad";
  };
  const tiles = [
    { k: "Ms", v: val(main, "Ms", 3), r: val(ref, "Ms", 3), c: lvl(main?.stable ? main.Ms : null, 1.8, 2.0, true) },
    { k: "GM", v: val(main, "GM", 3), r: val(ref, "GM", 3), c: lvl(main?.stable ? main.GM : null, 2.0, 1.7, false) },
    { k: "PM", v: val(main, "PM", 2) + (main?.stable ? "°" : ""), r: val(ref, "PM", 2) + (ref?.stable ? "°" : ""),
      c: lvl(main?.stable ? main.PM : null, 45, 30, false) },
  ];
  return (
    <div className="tn-tiles" data-testid="rob-tiles">
      {tiles.map((t) => (
        <div key={t.k} className={"tn-tile " + t.c} data-testid={`tile-${t.k}`}>
          <div className="k">{t.k}</div><div className="v mono">{t.v}</div><div className="r">{refName}: {t.r}</div></div>))}
    </div>
  );
}

function BlockSettings({ model }: { model: ModelState | undefined }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");
  void model;
  const g = (lab: string, a: [string, number | undefined, string?], b?: [string, number | undefined, string?], title?: string) => (
    <>
      <span className="tn-lab" title={title}>{lab}</span>
      <NumBare k={a[0]} def={a[1]} label={a[2] ?? `${lab} ${a[0]}`} />
      {b ? <NumBare k={b[0]} def={b[1]} label={b[2] ?? `${lab} ${b[0]}`} /> : <span />}
    </>
  );
  return (
    <>
      <div className="tn-grid3 blk">
        {g("NormPV", ["pv_lo", 0, "NormPV Low"], ["pv_hi", 100, "NormPV High"], T("h_normpv"))}
        {g("NormMV", ["mv_lo", 0, "NormMV Low"], ["mv_hi", 100, "NormMV High"], T("h_normmv"))}
        {g(T("ui_tuning_mv_limits"), ["mvl_lo", Number(st.mv_lo ?? 0), "MV_LoLim"], ["mvl_hi", Number(st.mv_hi ?? 100), "MV_HiLim"], T("h_mvlim"))}
        {g(T("sampletime"), ["samp", 1, "SampleTime"])}
        {g("DiffGain", ["diffgain", 5])}
        {g("PropFacSP", ["propfac", 1], undefined, T("pfb_help"))}
      </div>
      <button type="button" className="tn-btn small" data-testid="blk-reset" title={T("h_mvlim")}
        onClick={() => void patch({ mvl_lo: Number(st.mv_lo ?? 0), mvl_hi: Number(st.mv_hi ?? 100) })}>{T("ui_tuning_reset_block")}</button>
      <CheckSetting k="dfb" label={T("dfb")} def title={T("h_dfb")} />
      <h3 className="tn-h3">{T("blk_elems")}</h3>
      <NumSetting k="db" label={T("deadband")} min={0} title={T("h_deadband")} />
      <SelectSetting k="db_mode" label={T("db_mode")} options={["cont", "step"] as const} def="cont" fmt={(x) => T("db_" + x)} />
      <NumSetting k="pvfilt" label={T("pvfilt")} min={0} title={T("h_pvfilt")} />
      <NumSetting k="mvrate" label={T("mvrate", { u: uMv })} min={0} title={T("h_mvrate")} />
      <NumSetting k="sprate" label={T("sprate", { u: uPv })} min={0} title={T("h_sprate")} />
    </>
  );
}
