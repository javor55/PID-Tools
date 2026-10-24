// APC › Kaskáda: model vnitřní smyčky (jiná smyčka projektu / ručně / z dat), ladění vnitřní a vnější smyčky (klíče cas_*),
// oddělení rychlostí, hodnoty pro šablonu CascadeControl a simulace kaskády. Aktivní smyčka je vnější.
import { useState } from "react";
import type { components } from "../../api/schema";
import { NumSetting, SelectSetting } from "../../components/Fields";
import { LineChart } from "../../components/LineChart";
import { useSettings, useWs } from "../../data";
import { useT } from "../../i18n";
import { useJobRunner } from "../../jobs";
import { type CurveDef, curveSeries, NumInput, num, useApc } from "./common";
import { Checks, Impl, LoopSelect, PairError, PidRow, qs, usePair, usePost, useSim } from "./parts";

type CascadeInfo = components["schemas"]["CascadeInfo"];
type ModelOut = components["schemas"]["ModelOut"];
type CascadeSim = components["schemas"]["CascadeSim"];

const CTYPES = ["PI", "PID"] as const;

const useCascade = () => {
  const loop = usePair((s) => s.loops.cascade);
  return { loop, q: useApc<CascadeInfo>(`cascade${loop ?? ""}`, `/apc/cascade${qs({ loop })}`) };
};

function ManualInputs({ inp }: { inp: CascadeInfo["inputs"] }) {
  const T = useT();
  const post = usePost();
  const loop = usePair((s) => s.loops.cascade);
  const keys = [["cas_k", "K", undefined], ["cas_t1", "T1 [s]", 0.001], ["cas_t2", "T2 [s]", 0], ["cas_th", "θ [s]", 0]] as const;
  return (
    <>
      {keys.map(([k, l, min], i) => <NumSetting key={k} k={k} label={l} def={inp.manual[i]} min={min} />)}
      <button className="btn" data-testid="cas-reset-manual" title={T("h_apc_reset")}
        onClick={() => void post(`/apc/cascade/reset${qs({ loop })}`, { part: "manual" })}>{T("apc_reset")}</button>
    </>
  );
}

function DataInputs({ inp }: { inp: CascadeInfo["inputs"] }) {
  const T = useT();
  const run = useJobRunner();
  const [ipv, setIpv] = useState<string>();
  const [imv, setImv] = useState<string>();
  const [lo, setLo] = useState<number>();
  const [hi, setHi] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const sigs = inp.signals;
  const fit = async () => {
    setBusy(true); setErr(null);
    try {
      const j = await run("/apc/cascade/fit", { ipv: ipv ?? sigs[0], imv: imv ?? sigs[1] ?? sigs[0], ilo: lo, ihi: hi }, T("cas_fit"));
      if (j.state !== "done") setErr(j.error ?? j.state);
    } catch (e) { setErr(String((e as Error).message)); }
    setBusy(false);
  };
  const sel = (label: string, v: string | undefined, def: string, set: (x: string) => void, testid: string) => (
    <label className="field"><span>{label}</span>
      <select value={v ?? def} data-testid={testid} onChange={(e) => set(e.target.value)}>
        {sigs.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>);
  return (
    <>
      {sel(T("cas_ipv"), ipv, sigs[0], setIpv, "cas-ipv")}
      {sel(T("cas_imv"), imv, sigs[1] ?? sigs[0], setImv, "cas-imv")}
      <label className="field"><span>{T("cas_ilo")}</span><NumInput value={lo ?? 0} testid="cas-ilo" onCommit={setLo} /></label>
      <label className="field"><span>{T("cas_ihi")}</span><NumInput value={hi ?? 100} testid="cas-ihi" onCommit={setHi} /></label>
      <button className="btn primary" disabled={busy || !sigs.length} data-testid="cas-fit" onClick={() => void fit()}>{T("cas_fit")}</button>
      {err && <div className="err small">{err}</div>}
    </>
  );
}

export function CascadeSide() {
  const T = useT();
  const post = usePost();
  const { loop, q } = useCascade();
  if (!q.data) return null;
  const inp = q.data.inputs;
  const reset = (part: string) => void post(`/apc/cascade/reset${qs({ loop })}`, { part });
  const sameSamp = Math.abs(inp.samp_i - inp.samp_default) < 1e-9;
  return (
    <div className="stack" data-testid="cascade-side">
      <section>
        <h3>{T("cas_inner")}</h3>
        <SelectSetting k="cas_src" label={T("cas_src")} options={inp.sources} def={inp.source} fmt={(s) => T("cas_src_" + s)} />
        {inp.source === "loop" && <LoopSelect kind="cascade" label={T("cas_iloop")} current={inp.loop ?? undefined} />}
        {inp.source === "manual" && <ManualInputs inp={inp} />}
        {inp.source === "data" && <DataInputs inp={inp} />}
      </section>
      <section>
        <h3>{T("cas_inner_tune")}</h3>
        <SelectSetting k="cas_im" label={T("method")} options={inp.methods} def={inp.inner_method} fmt={(m) => T("m_" + m)} />
        <NumSetting k="cas_samp" label={T("cas_samp")} def={inp.samp_i} min={0.001} />
        {inp.inner_method === "SIMC" && <NumSetting k="cas_tci" label={T("tc")} def={inp.tci_default} min={0.001} title={T("tc_help")} />}
        <button className="btn" data-testid="cas-reset-inner" disabled={!inp.tci_edited && sameSamp} title={T("h_apc_reset")}
          onClick={() => reset("inner")}>{T("apc_reset")}</button>
      </section>
      <section>
        <h3>{T("cas_outer_tune")}</h3>
        <SelectSetting k="cas_om" label={T("method")} options={inp.methods} def={inp.outer_method} fmt={(m) => T("m_" + m)} />
        <SelectSetting k="cas_oct" label={T("ctrl_type")} options={CTYPES} def={inp.outer_ctype} />
        {inp.outer_method === "SIMC" && inp.tco_default != null && (
          <NumSetting k="cas_tco" label={T("tc")} def={inp.tco_default} min={0.001} title={T("tc_help")} />)}
        <button className="btn" data-testid="cas-reset-outer" disabled={!inp.tco_edited} title={T("h_apc_reset")}
          onClick={() => reset("outer")}>{T("apc_reset")}</button>
      </section>
    </div>
  );
}

function ModelLine({ m, label }: { m: ModelOut; label: string }) {
  const T = useT();
  return <div className="small">{label}: {T("model_" + m.code)} · {m.params.map((p) => `${p.name} = ${num(p.value)}`).join(", ")}</div>;
}

const ROW_LABEL: Record<string, string> = { inner: "cas_inner", outer: "ui_cas_outer" };

function ValuesCard({ d }: { d: CascadeInfo }) {
  const T = useT();
  return (
    <div className="card stack" data-testid="cas-values">
      <h3>{T("ui_cas_values")}</h3>
      <table className="tbl"><thead><tr><th>{T("sm_apl_block")}</th><th>{T("sm_gen_par")}</th><th>{T("sm_apl_value")}</th>
        <th>{T("sm_apl_unit")}</th></tr></thead>
        <tbody>{d.rows.map((r) => {
          const [blk, par] = r.param.split(".");
          return <tr key={r.param} data-testid={`cas-row-${r.param}`}><td>{T(ROW_LABEL[blk] ?? blk)}</td><td>{par}</td>
            <td className="mono">{num(r.value)}</td><td>{r.unit}</td></tr>;
        })}</tbody></table>
    </div>
  );
}

const PV_O: CurveDef[] = [{ name: "SP", key: "sp_o", color: "#9aa5b1", dash: "5 4" }, { name: "", key: "pv_o", color: "#1f5fa8" }];

function SimCard({ d, loop }: { d: CascadeInfo; loop?: number }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const query = qs({ loop });
  const { sim, cv } = useSim<CascadeSim>(["cas-sim", loop, d.inputs, d.inner, d.outer, d.inner_model], "/apc/cascade/simulate", query,
    {}, !!d.inner_model);
  if (!d.inner_model) return null;
  const pvo = PV_O.map((c) => (c.key === "pv_o" ? { ...c, name: T("cas_pv_o") } : c));
  const pvi: CurveDef[] = [{ name: T("cas_sp_i"), key: "sp_i", color: "#9aa5b1", dash: "5 4" },
    { name: T("cas_pv_i"), key: "pv_i", color: "#7c3aed" }];
  const valve: CurveDef[] = [{ name: T("cas_valve"), key: "valve", color: "#15803d" }];
  const unstable = sim.data && !sim.data.ok;
  return (
    <div className="card stack" data-testid="cas-sim">
      <div className="small muted">{T("cas_sim_help")}</div>
      {unstable ? <div className="err small" data-testid="cas-unstable">⛔ {T("err_sim_unstable", { n: T("apc_cascade") })}</div> : (
        <>
          <LineChart series={curveSeries(cv.data, pvo)} height={200} yLabel={`PV ${String(st.u_pv ?? "")}`} xLabel={T("time_s")} testid="cas-pv" />
          <LineChart series={curveSeries(cv.data, pvi)} height={140} yLabel={T("cas_inner_pct")} xLabel={T("time_s")} testid="cas-pvi" />
          <LineChart series={curveSeries(cv.data, valve)} height={120} yLabel={T("cas_valve_pct")} xLabel={T("time_s")} testid="cas-valve" />
        </>
      )}
      {sim.data && (
        <table className="tbl" data-testid="cas-kpis"><tbody>
          <tr><td>{T("cas_t63")} [s]</td><td className="mono" data-testid="cas-sim-t63">{num(sim.data.t63)}</td></tr>
          <tr><td>{T("cas_sep")}</td><td className="mono" data-testid="cas-sim-sep">{num(sim.data.separation)}</td></tr>
          {sim.data.ok && <tr><td>{T("iae_sp")} ({T("cas_pv_o")})</td><td className="mono" data-testid="cas-sim-iae">{num(sim.data.iae_outer)}</td></tr>}
        </tbody></table>
      )}
    </div>
  );
}

export function CascadeMain() {
  const T = useT();
  const ws = useWs().data;
  const { loop, q } = useCascade();
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (q.isError) return <PairError err={q.error} loop={loop} />;
  if (!q.data) return <div className="card muted">…</div>;
  const d = q.data;
  const nm = d.inputs.loops.find((l) => l.index === d.inputs.loop)?.name ?? "";
  return (
    <div className="stack">
      <div className="card stack" data-testid="cas-models">
        {d.inner_note && <div className="warn small" data-testid="cas-inner-note">⚠ {d.inner_note}</div>}
        {d.inner_model ? <ModelLine m={d.inner_model} label={d.inputs.source === "loop" ? `${T("cas_inner")} (${nm})` : T("cas_inner")} />
          : !d.inner_note && <div className="muted small" data-testid="cas-need-inner">{T("cas_need_inner")}</div>}
        {d.inner_fit && <div className="small" data-testid="cas-fit-info">{T("cas_inner_fit", { m: T("model_" + d.inner_fit.model.code),
          f: d.inner_fit.fit.toFixed(1), p: d.inner_fit.model.params.map((p) => `${p.name} = ${num(p.value)}`).join(", ") })}</div>}
        {d.outer_model && <div className="small" data-testid="cas-outer-model">{T("cas_outer_model", { m: T("model_" + d.outer_model.code),
          p: d.outer_model.params.map((p) => `${p.name} = ${num(p.value)}`).join(", ") })}</div>}
      </div>
      {d.inner && d.outer && (
        <div className="card stack" data-testid="cas-tuning">
          <h3>{T("cas_inner")}</h3>
          <PidRow c={d.inner} prefix="cas-inner" />
          <div className="small">{T("cas_t63")}: <b className="mono" data-testid="cas-t63">{num(d.t63)}</b> s</div>
          <h3>{T("cas_outer_tune")}</h3>
          <PidRow c={d.outer} prefix="cas-outer" />
          {d.outer.notes?.map((n) => <div key={n.key} className="small muted">{T(n.key, n.args as Record<string, unknown>)}</div>)}
          <div className="small">{T("cas_sep")}: <b className="mono" data-testid="cas-sep">{num(d.separation)}</b>×</div>
          {d.sep_warn && <div className="warn small" data-testid="cas-sep-warn">⚠ {T("cas_sep_warn")}</div>}
        </div>
      )}
      {d.rows.length > 0 && <ValuesCard d={d} />}
      <Impl text={d.impl_text} testid="cas-impl" />
      <Checks items={d.checks} />
      <SimCard d={d} loop={loop} />
    </div>
  );
}
