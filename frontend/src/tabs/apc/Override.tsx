// APC › Override: hlavní a omezující regulátor na jednom ventilu, výběr MIN / MAX. Druhá smyčka projektu se volí ve
// výběru (?loop=); skok SP a mez jsou parametry simulace (chybějící = výchozí scénář z API).
import { create } from "zustand";
import type { components } from "../../api/schema";
import { LineChart } from "../../components/LineChart";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { type CurveDef, curveSeries, NumInput, num, useApc } from "./common";
import { Checks, Impl, LoopSelect, PairError, qs, usePair, useSim } from "./parts";

type OvInfo = components["schemas"]["OvInfo"];
type OvSim = components["schemas"]["OvSim"];

const SELS = ["min", "max"] as const;
type Sel = (typeof SELS)[number];

interface OvState { sel: Sel; step?: number; lim?: number; set: (p: Partial<Omit<OvState, "set">>) => void }
const useOv = create<OvState>((set) => ({ sel: "min", set: (p) => set(p) }));

const useInfo = () => {
  const loop = usePair((s) => s.loops.override);
  const sel = useOv((s) => s.sel);
  return { loop, sel, q: useApc<OvInfo>(`override${loop ?? ""}-${sel}`, `/apc/override${qs({ loop, sel })}`) };
};

export function OverrideSide() {
  const T = useT();
  const { loop, sel, q } = useInfo();
  const { step, lim, set } = useOv();
  const d = q.data;
  return (
    <div className="stack" data-testid="override-side">
      <section>
        <h3>{T("apc_override_b")}</h3>
        <LoopSelect kind="override" label={T("apc_override_b")} current={d?.loop ?? loop} />
      </section>
      <section>
        <h3>{T("ov_select")}</h3>
        <label className="field"><span>{T("ov_select")}</span>
          <select value={sel} data-testid="ov-sel" onChange={(e) => set({ sel: e.target.value as Sel, step: undefined, lim: undefined })}>
            {SELS.map((s) => <option key={s} value={s}>{T("ov_" + s)}</option>)}</select></label>
        {d && (
          <>
            <label className="field"><span>{T("dk_ov_step")}</span>
              <NumInput value={step ?? d.defaults.step} testid="ov-step" onCommit={(x) => set({ step: x })} /></label>
            <label className="field"><span>{T("dk_ov_limit")}</span>
              <NumInput value={lim ?? d.defaults.lim} testid="ov-lim" onCommit={(x) => set({ lim: x })} /></label>
          </>
        )}
        <button className="btn" data-testid="ov-reset" disabled={step === undefined && lim === undefined} title={T("h_apc_reset")}
          onClick={() => set({ step: undefined, lim: undefined })}>{T("apc_reset")}</button>
      </section>
    </div>
  );
}

function SimCard({ d, loop }: { d: OvInfo; loop?: number }) {
  const T = useT();
  const { sel, step, lim } = useOv();
  const body = { sel, step, lim };
  const { sim, cv } = useSim<OvSim>(["ov-sim", loop, body, d.defaults], "/apc/override/simulate", qs({ loop }), body);
  const without = T("ov_without");
  const pva: CurveDef[] = [{ name: "SP", key: "sp_a", color: "#9aa5b1", dash: "5 4" }, { name: without, key: "pv_a_without", color: "#64748b", dash: "2 3" },
    { name: d.a, key: "pv_a", color: "#1f5fa8" }];
  const pvb: CurveDef[] = [{ name: T("ov_limit_short"), key: "lim_b", color: "#dc2626", dash: "5 4" },
    { name: without, key: "pv_b_without", color: "#64748b", dash: "2 3" }, { name: d.b, key: "pv_b", color: "#7c3aed" }];
  const mv: CurveDef[] = [{ name: T("ov_out", { n: d.a }), key: "u_a", color: "#1f5fa8", dash: "5 4" },
    { name: T("ov_out", { n: d.b }), key: "u_b", color: "#7c3aed", dash: "5 4" }, { name: "MV", key: "mv", color: "#15803d" }];
  return (
    <div className="card stack" data-testid="ov-sim">
      <div className="small muted">{T("ov_sim_help", { b: d.b })}</div>
      <LineChart series={curveSeries(cv.data, pva)} height={200} yLabel={`PV ${d.a}`} xLabel={T("time_s")} testid="ov-pv-a" />
      <LineChart series={curveSeries(cv.data, pvb)} height={200} yLabel={`PV ${d.b}`} xLabel={T("time_s")} testid="ov-pv-b" />
      <LineChart series={curveSeries(cv.data, mv)} height={140} yLabel="MV" xLabel={T("time_s")} testid="ov-mv" />
      {sim.data && (
        <table className="tbl" data-testid="ov-kpis"><tbody>
          <tr><td>{T("ov_peak", { n: d.b })}</td><td className="mono" data-testid="ov-peak">{num(sim.data.kpis.peak)}</td></tr>
          <tr><td>{T("ov_peak", { n: d.b })} ({without})</td><td className="mono" data-testid="ov-peak-without">{num(sim.data.kpis.peak_without)}</td></tr>
          <tr><td>{T("ov_time_b")} [%]</td><td className="mono" data-testid="ov-share">{(100 * sim.data.kpis.share).toFixed(0)}</td></tr>
          <tr><td>{T("ov_switches")}</td><td className="mono" data-testid="ov-switches">{sim.data.kpis.switches}</td></tr>
        </tbody></table>
      )}
    </div>
  );
}

export function OverrideMain() {
  const T = useT();
  const ws = useWs().data;
  const { loop, q } = useInfo();
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (q.isError) return <PairError err={q.error} loop={loop} />;
  if (!q.data) return <div className="card muted">…</div>;
  const d = q.data;
  return (
    <div className="stack">
      {d.mv_differs && (
        <div className="card warn small" data-testid="ov-mv-differs">⚠ <b>{T("ov_mv_differs", { a: d.a, b: d.b, mva: d.mv_a, mvb: d.mv_b })}</b></div>)}
      <Impl text={d.impl_text} testid="ov-impl" />
      <Checks items={d.checks} />
      <SimCard d={d} loop={loop} />
    </div>
  );
}
