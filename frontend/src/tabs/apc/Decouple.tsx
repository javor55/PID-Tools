// APC › Rozvazbení 2×2 s druhou smyčkou projektu: RGA, parametry decouplerů pro PCS 7 a simulace bez rozvazbení /
// se statickými / s dynamickými decoupler (vstupy simulace – typ a amplitudy SP – jsou parametry, ne nastavení projektu).
import { create } from "zustand";
import type { components } from "../../api/schema";
import { LineChart } from "../../components/LineChart";
import { SideCard } from "../../components/Ui";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { Bold, type CurveDef, curveSeries, NumInput, num, useApc } from "./common";
import { ACard, Checks, Impl, LoopSelect, PairError, qs, usePair, useSim, VariantTable } from "./parts";

type DecInfo = components["schemas"]["DecInfo"];
type DecSim = components["schemas"]["DecSim"];

const DTYPES = ["static", "dyn"] as const;
type DType = (typeof DTYPES)[number];

/** Vstupy simulace (sdílí je postranní panel a hlavní plocha). */
const useDec = create<{ dtype: DType; ampA: number; ampB: number; set: (p: Partial<{ dtype: DType; ampA: number; ampB: number }>) => void }>((set) => ({
  dtype: "dyn", ampA: 5, ampB: 5, set: (p) => set(p),
}));

const useInfo = () => {
  const loop = usePair((s) => s.loops.decouple);
  return { loop, q: useApc<DecInfo>(`decouple${loop ?? ""}`, `/apc/decouple${qs({ loop })}`) };
};

export function DecoupleSide() {
  const T = useT();
  const { loop, q } = useInfo();
  const { dtype, ampA, ampB, set } = useDec();
  return (
    <>
      <SideCard title={T("apc_decouple_b")} testid="decouple-side">
        <LoopSelect kind="decouple" label={T("apc_decouple_b")} current={q.data?.loop ?? loop} />
      </SideCard>
      <SideCard title={T("dec_type")}>
        <label className="field"><span>{T("dec_type")}</span>
          <select value={dtype} data-testid="dec-dtype" onChange={(e) => set({ dtype: e.target.value as DType })}>
            {DTYPES.map((t) => <option key={t} value={t}>{T("dec_" + t)}</option>)}</select></label>
        <label className="field"><span>SP A [%]</span>
          <NumInput value={ampA} testid="dec-amp-a" onCommit={(x) => set({ ampA: Math.max(-100, Math.min(100, x)) })} /></label>
        <label className="field"><span>SP B [%]</span>
          <NumInput value={ampB} testid="dec-amp-b" onCommit={(x) => set({ ampB: Math.max(-100, Math.min(100, x)) })} /></label>
        <button className="btn" data-testid="dec-reset" disabled={dtype === "dyn" && ampA === 5 && ampB === 5} title={T("h_apc_reset")}
          onClick={() => set({ dtype: "dyn", ampA: 5, ampB: 5 })}>{T("apc_reset")}</button>
      </SideCard>
    </>
  );
}

function SimCard({ d, loop }: { d: DecInfo; loop?: number }) {
  const T = useT();
  const { dtype, ampA, ampB } = useDec();
  const body = { dtype, amp_a: ampA, amp_b: ampB };
  const { cv } = useSim<DecSim>(["dec-sim", loop, d.params, body], "/apc/decouple/simulate", qs({ loop }), body, d.ok);
  if (!d.ok) return null;
  const chart = (sp: string, none: string, pv: string, name: string, color: string): CurveDef[] => [
    { name: "SP", key: sp, color: "#9aa5b1", dash: "5 4" }, { name: T("dec_without"), key: none, color: "#64748b", dash: "2 3" },
    { name: name, key: pv, color }];
  const mv: CurveDef[] = [{ name: `MV ${d.a}`, key: "mv_a", color: "#1f5fa8" }, { name: `MV ${d.b}`, key: "mv_b", color: "#7c3aed" }];
  return (
    <ACard title={T("ui_apc_verify")} testid="dec-sim">
      <LineChart series={curveSeries(cv.data, chart("sp_a", "pv_a_none", "pv_a", d.a, "#1f5fa8"))} height={200} yLabel={`PV ${d.a}`}
        xLabel={T("time_s")} testid="dec-pv-a" />
      <LineChart series={curveSeries(cv.data, chart("sp_b", "pv_b_none", "pv_b", d.b, "#7c3aed"))} height={200} yLabel={`PV ${d.b}`}
        xLabel={T("time_s")} testid="dec-pv-b" />
      <LineChart series={curveSeries(cv.data, mv)} height={140} yLabel="MV" xLabel={T("time_s")} testid="dec-mv" />
      <p className="small muted">{T("dec_sim_help")}</p>
    </ACard>
  );
}

function KpiTable({ d, loop }: { d: DecInfo; loop?: number }) {
  const T = useT();
  const { dtype, ampA, ampB } = useDec();
  const body = { dtype, amp_a: ampA, amp_b: ampB };
  const { sim } = useSim<DecSim>(["dec-sim", loop, d.params, body], "/apc/decouple/simulate", qs({ loop }), body, d.ok);
  if (!d.ok || !sim.data) return null;
  const ks = sim.data.kpis;
  return (
    <VariantTable testid="dec-kpis" cols={ks.map((k) => ({ key: k.variant, label: T("dec_" + k.variant) }))} rows={[
      { key: "a", label: `IAE ${d.a}`, best: "min", values: ks.map((k) => k.iae_a) },
      { key: "b", label: `IAE ${d.b}`, best: "min", values: ks.map((k) => k.iae_b) }]} />
  );
}

export function DecoupleMain() {
  const T = useT();
  const ws = useWs().data;
  const { loop, q } = useInfo();
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (q.isError) return <PairError err={q.error} loop={loop} />;
  if (!q.data) return <div className="card muted">…</div>;
  const d = q.data;
  return (
    <div className="stack">
      <SimCard d={d} loop={loop} />
      <ACard title={T("ui_apc_result")} testid="dec-result">
        <div className="stack" data-testid="dec-rga">
          {d.ok ? <div className="small"><b>RGA λ₁₁ = <span className="mono" data-testid="dec-lam">{num(d.lam)}</span></b></div>
            : <div className="warn small" data-testid="dec-need-cross">⚠ <Bold text={d.advice ?? ""} /></div>}
          {d.ok && d.advice && <div className="small" data-testid="dec-advice"><Bold text={d.advice} /></div>}
        </div>
        <KpiTable d={d} loop={loop} />
      </ACard>
      {d.ok && (
        <ACard title={T("dec_params")} help={T("ui_apc_pcs_h")} testid="dec-params">
          <div className="apc-tblwrap"><table className="apc-vt"><thead><tr><th>{T("dec_path")}</th><th className="r">{T("dec_gain_pct")}</th>
            <th className="r">{T("dec_gain_eng")}</th><th className="r">Lead [s]</th><th className="r">Lag [s]</th><th className="r">{T("ff_delay")}</th></tr></thead>
            <tbody>{d.params.map((p, i) => (
              <tr key={i} data-testid={`dec-param-${i}`}><th scope="row">{p.source_mv} → MV {p.target}</th><td className="mono r">{num(p.gain)}</td>
                <td className="mono r">{num(p.gain_eng)}</td><td className="mono r">{num(p.lead)}</td><td className="mono r">{num(p.lag)}</td>
                <td className="mono r">{num(p.delay)}</td></tr>))}</tbody></table></div>
          <p className="small muted">{T("dec_params_help")}</p>
        </ACard>
      )}
      <Impl text={d.impl_text} testid="dec-impl" />
      <Checks items={d.checks} />
    </div>
  );
}
