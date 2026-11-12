// Ladění podle profilu regulátoru smyčky (E8-B): karta Regulátor smyčky (výběr z knihovny, odkaz do knihovny, nastavení
// bloku generované z parametrů profilu), Proces a ventil v simulaci, tabulka robustnosti, upozornění ladění, τc
// a Export pro řídicí systém (PCS 7 / TIA / DeltaV / CSV).
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { bytes, request } from "../api/client";
import type { components } from "../api/schema";
import { CheckSetting, NumSetting, SelectSetting } from "../components/Fields";
import { LabelHelp } from "../components/Ui";
import { useSettings, usePatchSettings, useWsQuery } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";
import { fnum } from "./TuningMore";
import { useTun } from "./tuningState";

type TuningInfo = components["schemas"]["TuningInfo"];
type Summary = components["schemas"]["ControllerSummary"];
type BlockParam = components["schemas"]["BlockParam"];
type RobRow = components["schemas"]["RobRow"];
type Plant = components["schemas"]["PlantInfo"];
type Warn = components["schemas"]["Warn"];

/** Odkaz do knihovny regulátorů: událost, kterou zachytí rozhraní Nastavení › Regulátory (id = profil k otevření). */
export const OPEN_SETTINGS_EVENT = "pid:open-settings";
export const openControllerLibrary = (id: string) =>
  window.dispatchEvent(new CustomEvent(OPEN_SETTINGS_EVENT, { detail: { section: "controllers", id } }));

const ROLE_HELP: Record<string, string> = { Ts: "sampletime_help", N: "diffgain_help", b: "pfb_help", d_on_pv: "h_dfb",
  deadband: "h_deadband", deadband_mode: "h_db_mode", mv_lo: "h_mvlim", mv_hi: "h_mvlim", pv_filter: "h_pvfilt",
  mv_rate: "h_mvrate", sp_rate: "h_sprate" };
const label = (q: { name: string; unit?: string | null }) => (q.unit && q.unit !== "-" ? `${q.name} [${q.unit}]` : q.name);

/** Číselné pole bez popisku navázané na klíč nastavení (rozsahy NormPV / NormMV); uloží se po opuštění pole / Enter. */
function BareNum({ k, def, label, title }: { k: string; def: number; label: string; title: string }) {
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const cur = Number(st[k] ?? def);
  return (
    <input type="number" step="any" className="tn-in" aria-label={label} title={title} key={`${k}-${cur}`} defaultValue={+cur.toPrecision(6)}
      data-testid={`set-${k}`} onBlur={(e) => { const v = e.target.value; if (v !== "" && Number.isFinite(+v) && +v !== cur) void patch({ [k]: +v }); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

// ---------------------------------------------------------------- karta Regulátor smyčky
export function ControllerCard({ info }: { info: TuningInfo }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const patch = usePatchSettings();
  const st = useSettings().data ?? {};
  const lib = useQuery({ queryKey: ["controllers"], queryFn: () => request<Summary[]>("GET", "/controllers") });
  const c = info.controller;
  if (!c) return null;
  const opts = lib.data ?? [];
  const change = async (id: string) => {
    await request("PUT", `/workspaces/${wid}/controller`, { from_id: id });
    useTun.setState({ sug: null, err: null });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const ro = (q: BlockParam) => (
    <div className="field" key={q.key} data-testid={`blk-ro-${q.key}`}>
      <span className="lbl">{label(q)}<LabelHelp text={T("tun_ui_blk_ro")} /></span>
      <span className="mono tn-faint">{String(q.default ?? "—")}</span>
    </div>);
  const row = (q: BlockParam) => {
    const lab = label(q), help = ROLE_HELP[q.role] ? T(ROLE_HELP[q.role]) : T("tun_ui_blk_ro");
    if (!q.setting) return ro(q);
    if (q.role === "d_on_pv") return <CheckSetting key={q.key} k={q.setting} label={lab} def help={help} />;
    if (q.role === "deadband_mode")
      return <SelectSetting key={q.key} k={q.setting} label={lab} help={help} options={["cont", "step"] as const} def="cont"
        fmt={(x) => T("db_" + x)} />;
    return <NumSetting key={q.key} k={q.setting} label={lab} help={help} def={Number(q.value ?? q.default ?? 0)}
      min={q.role === "mv_lo" || q.role === "mv_hi" ? undefined : 0} />;
  };
  const g = (lab: string, a: [string, number], b: [string, number], title: string) => (
    <>
      <span className="tn-lab" title={title}>{lab}</span>
      <BareNum k={a[0]} def={a[1]} label={`${lab} Low`} title={title} />
      <BareNum k={b[0]} def={b[1]} label={`${lab} High`} title={title} />
    </>
  );
  return (
    <>
      <div className="tn-ctl" data-testid="loop-ctrl">
        <label className="trow" title={T("tun_ui_ctrl_pick_help")}><span>{T("tun_ui_ctrl_pick")}</span>
          <select value={c.id} data-testid="ctrl-select" aria-label={T("tun_ui_ctrl_pick")} onChange={(e) => void change(e.target.value)}>
            {!opts.some((o) => o.id === c.id) && <option value={c.id}>{c.vendor} · {c.name}</option>}
            {opts.map((o) => <option key={o.id} value={o.id}>{o.vendor} · {o.name}{o.verified ? "" : " ⚠"}</option>)}
          </select></label>
        <div className="tn-note" data-testid="ctrl-name">{c.vendor} · {c.block} · {T("tun_ui_ctrl_" + c.tag)} ·{" "}
          <b className={c.verified ? "tn-ok" : "tn-faint"}>{c.verified ? T("tun_ui_ctrl_verified") : T("tun_ui_ctrl_unverified")}</b>{" "}
          <button type="button" className="link" data-testid="ctrl-open-lib" title={T("tun_ui_ctrl_open_help")}
            onClick={() => openControllerLibrary(c.id)}>{T("tun_ui_ctrl_open")}</button></div>
      </div>
      <h3 className="tn-h3">{T("tun_ui_ctrl_blk")}<LabelHelp text={T("tun_ui_ctrl_help")} /></h3>
      <div className="tn-grid3 blk">
        {g("NormPV", ["pv_lo", 0], ["pv_hi", 100], T("h_normpv"))}
        {g("NormMV", ["mv_lo", 0], ["mv_hi", 100], T("h_normmv"))}
      </div>
      <div data-testid="blk-params">{info.block_params.map(row)}</div>
      <button type="button" className="tn-btn small" data-testid="blk-reset" title={T("h_mvlim")}
        onClick={() => void patch({ mvl_lo: Number(st.mv_lo ?? 0), mvl_hi: Number(st.mv_hi ?? 100) })}>{T("ui_tuning_reset_block")}</button>
      <div className="tn-note">{T("tun_ui_ctrl_note")}</div>
    </>
  );
}

// ---------------------------------------------------------------- τc
export function TcRow({ method, ctype, def }: { method: string; ctype: string; def: number | null | undefined }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const k = `tc|${String(st.mcode ?? "")}|${method}|${ctype}`;
  const cur = Number(st[k]);
  return (
    <div className="trow"><span className="lbl">{T("tun_ui_tc")}<LabelHelp text={T("tun_ui_tc_help")} /></span>
      <input type="number" step="any" min={1e-9} className="tn-in" data-testid="set-tc" aria-label={T("tun_ui_tc")} key={`${k}-${cur}`}
        defaultValue={cur > 0 ? +cur.toPrecision(6) : ""} placeholder={def ? T("tun_ui_tc_auto", { v: +def.toPrecision(4) }) : undefined}
        onBlur={(e) => { const v = e.target.value; if (v === "" ? cur > 0 : Number.isFinite(+v) && +v > 0 && +v !== cur) void patch({ [k]: v === "" ? 0 : +v }); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} /></div>
  );
}

// ---------------------------------------------------------------- Proces a ventil v simulaci
export function PlantBody() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const st = useSettings().data ?? {};
  const q = useQuery({ queryKey: ["ws", wid, "plant", st], placeholderData: keepPreviousData,
    queryFn: () => request<Plant>("GET", `/workspaces/${wid}/tuning/plant`) });
  const put = async (body: Record<string, unknown>) => {
    await request("PUT", `/workspaces/${wid}/tuning/plant`, body);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const p = q.data;
  if (!p) return null;
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");
  const num = (v: number, key: string, lab: string, help: string, tid: string, max?: number) => (
    <label className="trow" title={help}><span className="lbl">{lab}<LabelHelp text={help} /></span>
      <input type="number" step="any" min={0} max={max} className="tn-in" data-testid={tid} aria-label={lab} key={`${tid}-${v}`}
        defaultValue={+v.toPrecision(5)} onBlur={(e) => { const x = e.target.value; if (x !== "" && Number.isFinite(+x) && +x !== v) void put({ [key]: +x }); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} /></label>);
  const W = 120, X = (x: number) => (x / 100) * W, Y = (y: number) => W - (Math.min(y, 100) / 100) * W;
  return (
    <div data-testid="plant">
      <div className="tn-note">{T("plant_help")}</div>
      {num(p.stic, "stic", T("sim_stic", { u: uMv }), T("h_sim_stic"), "plant-stic")}
      {p.stic_default > 0 && <div className="tn-sub">{T("tun_ui_plant_stic_from_fit", { v: +p.stic_default.toPrecision(3) })}</div>}
      {num(p.slip, "slip", T("sim_slip"), T("h_sim_slip"), "plant-slip", 100)}
      {num(p.noise, "noise", T("sim_noise", { u: uPv }), T("h_sim_noise", { s: +p.sigma_pv.toPrecision(3) }), "plant-noise")}
      <h3 className="tn-h3">{T("vchar_title")}<LabelHelp text={T("h_vchar")} /></h3>
      <div className="tn-vchar" data-testid="plant-vchar">
        {p.vchar.map((g, i) => (
          <label key={i} className="tn-vc"><span className="tn-sub">{10 * i}–{10 * i + 10}</span>
            <input type="number" step="any" min={0} className="tn-setin" data-testid={`vchar-${i}`} key={`${i}-${g}`} defaultValue={+g.toPrecision(4)}
              aria-label={`${T("vchar_gain")} ${10 * i}–${10 * i + 10} ${uMv}`}
              onBlur={(e) => { const x = e.target.value; if (x !== "" && Number.isFinite(+x) && +x >= 0 && +x !== g) void put({ vchar: p.vchar.map((v, j) => (j === i ? +x : v)) }); }}
              onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} /></label>))}
      </div>
      <svg viewBox={`-2 -2 ${W + 4} ${W + 4}`} className="tn-vcurve" role="img" aria-label={T("tun_ui_plant_curve")}>
        <line x1={0} y1={W} x2={W} y2={0} stroke="var(--pid-soft)" strokeDasharray="3 3" />
        <polyline fill="none" stroke="var(--pid-mv)" strokeWidth={2} points={p.curve_x.map((x, i) => `${X(x)},${Y(p.curve_y[i])}`).join(" ")} />
      </svg>
      <div className="tn-note">{T("tun_ui_plant_note")}</div>
    </div>
  );
}

// ---------------------------------------------------------------- upozornění ladění (T3–T5)
export function TuningWarnings({ unstable }: { unstable: string[] }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  const q = useQuery({ queryKey: ["ws", wid, "twarn", st], placeholderData: keepPreviousData,
    queryFn: () => request<Warn[]>("GET", `/workspaces/${wid}/tuning/warnings`) });
  const items = q.data ?? [];
  if (!items.length && !unstable.length) return null;
  return (
    <div className="tn-warns" data-testid="tun-warnings" aria-label={T("tun_ui_warn_title")}>
      {items.map((w) => <div key={w.key} className="tn-warn" data-testid={`warn-${w.key}`}>⚠ {w.text}</div>)}
      {unstable.map((n) => <div key={n} className="tn-warn err" data-testid="warn-unstable">⛔ {T("err_sim_unstable", { n })}</div>)}
    </div>
  );
}

// ---------------------------------------------------------------- tabulka robustnosti
export function useRob(preview: { Kc: number; Ti: number; Td: number } | null) {
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  const info = useWsQuery<TuningInfo>("tuning", "/tuning");
  return useQuery({ queryKey: ["ws", wid, "rob", info.data?.sets, info.data?.controller?.id, preview, st], enabled: !!info.data,
    placeholderData: keepPreviousData, queryFn: () => request<RobRow[]>("POST", `/workspaces/${wid}/tuning/robustness`, preview ?? undefined) });
}

export function RobTable({ rows, dec }: { rows: RobRow[] | undefined; dec: string }) {
  const T = useT();
  const st = useSettings().data ?? {};
  if (!rows?.length) return null;
  const nm = (n: string) => (n === "sug" ? T("dk_suggest") : n === "set1" ? T("set_1") : T("set_2"));
  const f = (x: number | null | undefined, p = 3) => fnum(x, dec, p);
  const mvr = Number(st.mv_hi ?? 100) - Number(st.mv_lo ?? 0);
  return (
    <div className="tn-scroll">
      <table className="tn-tbl" data-testid="rob-table" aria-label={T("tun_ui_rob_title")}>
        <thead><tr><th scope="col" /><th scope="col" className="r" title={T("ui_tuning_help_rob")}>Ms</th>
          <th scope="col" className="r" title={T("tun_ui_rob_mt")}>Mt</th><th scope="col" className="r">GM</th>
          <th scope="col" className="r">PM [°]</th><th scope="col" className="r" title={T("tun_ui_rob_worst")}>Ms max</th>
          <th scope="col" className="r" title={T("noise_col", { u: String(st.u_mv || "MV") })}>σ MV</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.name} data-testid={`rob-${r.name}`}><th scope="row">{nm(r.name)}</th>
            {r.stable ? <>
              <td className="r mono">{f(r.Ms)}</td><td className="r mono">{f(r.Mt)}</td><td className="r mono">{f(r.GM)}</td>
              <td className="r mono">{r.PM == null ? "–" : r.PM.toFixed(0)}</td><td className="r mono">{f(r.Ms_worst)}</td>
              <td className="r mono">{r.noise == null ? "–" : f((r.noise * mvr) / 100)}</td></>
              : <td colSpan={6} className="tn-faint">{T("tun_ui_rob_unstable")}</td>}</tr>))}
        </tbody></table>
      {rows.some((r) => r.approximate) && <div className="tn-note">{T("tun_ui_rob_approx")}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- export pro řídicí systém
const EXT: Record<string, string> = { csv: "csv", pcs7: "txt", tia: "scl", deltav: "tsv" };

export function ExportBox({ formats }: { formats: string[] }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const [open, setOpen] = useState(false);
  const [fmt, setFmt] = useState(formats[0] ?? "csv");
  const [n, setN] = useState(2);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    try {
      const buf = await bytes("GET", `/workspaces/${wid}/tuning/export?fmt=${fmt}&n=${n}`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob(["﻿", buf], { type: "text/plain;charset=utf-8" }));
      a.download = `tuning_set${n}_${fmt}.${EXT[fmt] ?? "txt"}`;
      a.click();
      URL.revokeObjectURL(a.href);
      setErr(null);
    } catch (e) { setErr(String((e as Error).message)); }
  };
  return (
    <div className="tn-export">
      <button type="button" className="tn-btn" aria-expanded={open} data-testid="export-open" title={T("tun_ui_exp_help")}
        onClick={() => setOpen(!open)}>{T("tun_ui_exp_btn")}</button>
      {open && (
        <div className="tn-exp-box" data-testid="export-box">
          <div className="tn-note">{T("tun_ui_exp_help")}</div>
          <label className="trow"><span>{T("tun_ui_exp_fmt")}</span>
            <select value={fmt} data-testid="export-fmt" title={T("tun_ui_exp_help")} aria-label={T("tun_ui_exp_fmt")} onChange={(e) => setFmt(e.target.value)}>
              {formats.map((x) => <option key={x} value={x}>{T("tun_ui_exp_" + x)}</option>)}</select></label>
          <label className="trow"><span>{T("tun_ui_exp_set")}</span>
            <select value={n} data-testid="export-set" title={T("tun_ui_exp_help")} aria-label={T("tun_ui_exp_set")} onChange={(e) => setN(+e.target.value)}>
              {[1, 2].map((x) => <option key={x} value={x}>{T("set_" + x)}</option>)}</select></label>
          <button type="button" className="tn-btn sug" data-testid="export-go" title={T("tun_ui_exp_help")} onClick={() => void go()}>{T("tun_ui_exp_go")}</button>
          {err && <div className="err small">{err}</div>}
        </div>)}
    </div>
  );
}
