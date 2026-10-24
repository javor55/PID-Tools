// APC › Smithův prediktor: vstupy v postranním panelu (klíče nastavení apc_sm_*), v hlavní ploše regulátor, pracovní bod,
// hodnoty pro šablonu a simulace PID (sada 2) vs. Smith na procesu s chybou modelu.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { binary, request } from "../../api/client";
import type { components } from "../../api/schema";
import { unframe } from "../../api/signals";
import { NumSetting, SelectSetting } from "../../components/Fields";
import { LineChart } from "../../components/LineChart";
import { usePatchSettings, useSettings, useWs } from "../../data";
import { useT } from "../../i18n";
import { useJobRunner } from "../../jobs";
import { useUi } from "../../store";
import { Bold, type CurveDef, curveSeries, NumInput, num, useApc } from "./common";

type SmithInfo = components["schemas"]["SmithInfo"];
type SmithSim = components["schemas"]["SmithSim"];

const CTYPES = ["PI", "PID"] as const;

function ManualInputs({ inp }: { inp: SmithInfo["inputs"] }) {
  const patch = usePatchSettings();
  const cur = ((useSettings().data ?? {}).apc_sm_man as number[] | undefined) ?? inp.manual;
  const set = (i: number, x: number) => void patch({ apc_sm_man: cur.map((v, k) => (k === i ? x : v)) });
  const lab = ["Gain", "TI [s]", "TD [s]"];
  return (
    <>{lab.map((l, i) => (i < 2 || inp.ctype === "PID") && (
      <label className="field" key={l}><span>{l}</span>
        <NumInput value={cur[i]} min={i ? 0 : undefined} testid={`set-apc_sm_man-${i}`} onCommit={(x) => set(i, x)} /></label>))}</>
  );
}

export function SmithSide() {
  const T = useT();
  const q = useApc<SmithInfo>("smith", "/apc/smith");
  const patch = usePatchSettings();
  const run = useJobRunner();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!q.data) return null;
  const { inputs: inp, integ } = q.data;
  const tcOn = inp.method === "SIMC" || inp.method === "Lambda";
  const optimize = async () => {
    setBusy(true); setErr(null);
    try {
      const j = await run("/apc/smith/optimize", undefined, T("sm_m_OPT"));
      if (j.state !== "done") setErr(j.error ?? j.state);
    } catch (e) { setErr(String((e as Error).message)); }
    setBusy(false);
  };
  return (
    <div className="stack" data-testid="smith-side">
      <section>
        <h3>{T("apc_smith")}</h3>
        <SelectSetting k="apc_sm_method" label={T("sm_method")} options={inp.methods} def={inp.method} title={T("h_sm_method")}
          fmt={(m) => T("sm_m_" + m)} />
        <SelectSetting k="apc_sm_ct" label={T("ctrl_type")} options={CTYPES} def="PI" />
        {tcOn && <NumSetting k={inp.tc_key} label={T("sm_tc")} def={inp.tc_default} min={0.001} title={T("h_sm_tc")} />}
        {tcOn && <button className="btn" data-testid="sm-tc-reset" title={T("h_apc_reset")}
          onClick={() => void patch({ [inp.tc_key]: inp.tc_default })}>{T("apc_reset")}</button>}
        {inp.method === "manual" && <ManualInputs inp={inp} />}
        {inp.method === "OPT" && (
          <>
            <button className="btn primary" disabled={busy} data-testid="sm-opt" onClick={() => void optimize()}>{T("ui_sm_optimize")}</button>
            {err && <div className="err small">{err}</div>}
          </>
        )}
        {integ && <div className="warn small">⚠ {T("sm_integ")}</div>}
      </section>
      <section>
        <h3>{T("sm_err")}</h3>
        <NumSetting k="apc_sm_ek" label={T("sm_err_k") + " [%]"} def={0} step={5} />
        <NumSetting k="apc_sm_et" label={T("sm_err_t") + " [%]"} def={0} step={5} />
        <NumSetting k="apc_sm_eth" label={T("sm_err_th") + " [%]"} def={0} step={5} />
        <button className="btn" data-testid="sm-err-reset" title={T("h_apc_reset")}
          onClick={() => void patch({ apc_sm_ek: 0, apc_sm_et: 0, apc_sm_eth: 0 })}>{T("apc_reset")}</button>
      </section>
    </div>
  );
}

function ValuesCards({ d }: { d: SmithInfo }) {
  const T = useT();
  if (!d.rows || !d.general_rows) return null;
  return (
    <>
      <div className="card stack" data-testid="sm-general">
        <h3>{T("sm_gen_title")}</h3>
        <table className="tbl"><thead><tr><th>{T("sm_gen_par")}</th><th>{T("sm_apl_value")}</th><th>{T("sm_apl_unit")}</th></tr></thead>
          <tbody>{d.general_rows.map((r) => <tr key={r.key}><td>{T(r.key)}</td><td className="mono">{num(r.value)}</td><td>{r.unit}</td></tr>)}</tbody></table>
        <div className="small muted"><Bold text={T("sm_gen_help")} /></div>
      </div>
      <div className="card stack" data-testid="sm-template">
        <h3>{T("sm_apl_title")}</h3>
        <table className="tbl"><thead><tr><th>{T("sm_apl_block")}</th><th>{T("sm_apl_input")}</th><th>{T("sm_apl_value")}</th>
          <th>{T("sm_apl_unit")}</th></tr></thead>
          <tbody>{d.rows.map((r, i) => <tr key={i}><td>{r.block}</td><td>{r.input}</td><td className="mono">{num(r.value)}</td><td>{r.unit}</td></tr>)}</tbody></table>
        <div className="small muted"><Bold text={T("sm_apl_note")} /></div>
      </div>
    </>
  );
}

function SimCard({ d }: { d: SmithInfo }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  // vstupy simulace jsou v nastavení (API je čte samo); klíč je zneplatní při změně zadání i regulátoru
  const key = ["ws", wid, "apc", "smith-sim", d.inputs, d.controller];
  const sim = useQuery({ queryKey: [...key, "kpi"], enabled: d.opt_ready, placeholderData: keepPreviousData, retry: false,
    queryFn: () => request<SmithSim>("POST", `/workspaces/${wid}/apc/smith/simulate`, {}) });
  const cv = useQuery({ queryKey: [...key, "curves"], enabled: d.opt_ready, placeholderData: keepPreviousData, retry: false,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/apc/smith/simulate/curves`, {})) });
  if (!d.opt_ready) return null;
  const pv: CurveDef[] = [{ name: "SP", key: "sp", color: "#9aa5b1", dash: "5 4" },
    { name: T("sm_pid"), key: "pv_pid", color: "#64748b", dash: "5 4" }, { name: T("sm_smith"), key: "pv_smith", color: "#15803d" }];
  const mv: CurveDef[] = [{ name: T("sm_pid"), key: "mv_pid", color: "#64748b", dash: "5 4" },
    { name: T("sm_smith"), key: "mv_smith", color: "#15803d" }];
  return (
    <div className="card stack" data-testid="sm-sim">
      <div className="small muted">{T("sm_help", { m: T("model_" + d.model) })}</div>
      <LineChart series={curveSeries(cv.data, pv)} height={220} yLabel={`PV ${String(st.u_pv ?? "")}`} xLabel={T("time_s")} testid="sm-pv" />
      <LineChart series={curveSeries(cv.data, mv)} height={140} yLabel={`MV ${String(st.u_mv ?? "")}`} xLabel={T("time_s")} testid="sm-mv" />
      {sim.data && (
        <table className="tbl" data-testid="sm-kpis">
          <thead><tr><th>{T("setting")}</th><th>{T("iae_sp")}</th><th>{T("iae_load")}</th></tr></thead>
          <tbody>{(["pid", "smith"] as const).map((k) => (
            <tr key={k} data-testid={`sm-kpi-${k}`}><td>{T("sm_" + k)}</td><td className="mono">{num(sim.data.kpis[k]?.iae_sp)}</td>
              <td className="mono">{num(sim.data.kpis[k]?.iae_load)}</td></tr>))}</tbody>
        </table>
      )}
    </div>
  );
}

export function SmithMain() {
  const T = useT();
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const q = useApc<SmithInfo>("smith", "/apc/smith");
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const d = q.data;
  return (
    <div className="stack">
      <div className="card stack" data-testid="sm-ctrl">
        <div className="small" data-testid="sm-ratio">{T("sm_ratio", { r: d.ratio.toFixed(2) })}</div>
        {d.controller ? (
          <>
            <table className="tbl"><thead><tr><th>Gain</th><th>TI [s]</th><th>TD [s]</th></tr></thead>
              <tbody><tr><td className="mono" data-testid="sm-kc">{num(d.controller.Kc)}</td>
                <td className="mono" data-testid="sm-ti">{num(d.controller.Ti)}</td>
                <td className="mono" data-testid="sm-td">{num(d.controller.Td)}</td></tr></tbody></table>
            {d.controller.notes?.map((n) => <div key={n.key} className="small muted">{T(n.key, n.args as Record<string, unknown>)}</div>)}
          </>
        ) : <div className="muted small" data-testid="sm-need-opt">{T("ui_sm_need_opt")}</div>}
        {d.pv_op != null && d.mv_op != null && (
          <div className="small mono" data-testid="sm-op">PV0 = {num(d.pv_op)} {String(st.u_pv ?? "")} · MV0 = {num(d.mv_op)} {String(st.u_mv ?? "")}</div>
        )}
        {d.basis_text && <div className="small"><Bold text={d.basis_text} /></div>}
      </div>
      <ValuesCards d={d} />
      <SimCard d={d} />
    </div>
  );
}
