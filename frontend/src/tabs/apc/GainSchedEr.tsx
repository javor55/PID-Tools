// APC › Gain scheduling podle regulační odchylky (ER): práh, násobek zesílení, skok SP a porucha (klíče gs_er_*), hodnoty
// pro blok GainSched a ověření jedna sada / scheduling podle ER / řídicí pásmo ConZone.
import type { components } from "../../api/schema";
import { NumSetting } from "../../components/Fields";
import { LineChart } from "../../components/LineChart";
import { SideCard } from "../../components/Ui";
import { useSettings, useWs } from "../../data";
import { useT } from "../../i18n";
import { type CurveDef, curveSeries, num, useApc } from "./common";
import { ACard, Checks, Impl, PointTable, usePost, useSim, VariantTable } from "./parts";

type GsErInfo = components["schemas"]["GsErInfo"];
type GsErSim = components["schemas"]["GsErSim"];

const useEr = () => useApc<GsErInfo>("gainsched_er", "/apc/gainsched_er");
const NAMES: Record<string, string> = { fixed: "gs_fixed", sched: "gs_er_sched", zone: "gs_er_cz" };
const COLORS: Record<string, string> = { fixed: "#9aa5b1", sched: "#15803d", zone: "#7c3aed" };

export function GainSchedErSide() {
  const T = useT();
  const post = usePost();
  const u = String(useSettings().data?.u_pv ?? "PV");
  const q = useEr();
  if (!q.data) return null;
  const { inputs: inp, integ } = q.data;
  if (integ) return <SideCard title={T("gs_x_er")}><div className="warn small" data-testid="er-side-integ">⚠ {T("gs_integ")}</div></SideCard>;
  return (
    <>
      <SideCard title={T("gs_x_er")} testid="er-side">
        <NumSetting k="gs_er_E" label={T("dk_gser_E", { u })} def={inp.E_default} min={0} />
        <NumSetting k="gs_er_k" label={T("dk_gser_k")} def={inp.k_default} min={0.1} />
        <NumSetting k="gs_er_spstep" label={T("dk_gser_sp", { u })} def={inp.spstep_default} />
        <NumSetting k="gs_er_d" label={T("dk_gser_d")} def={inp.d_default} />
        <button className="btn" data-testid="er-reset" disabled={!inp.edited} title={T("h_apc_reset")}
          onClick={() => void post("/apc/gainsched_er/reset")}>{T("apc_reset")}</button>
      </SideCard>
    </>
  );
}

function SimCard({ d }: { d: GsErInfo }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const { sim, cv } = useSim<GsErSim>(["er-sim", d.inputs, d.base], "/apc/gainsched_er/simulate", "", {}, !d.integ);
  if (d.integ) return null;
  const names = sim.data?.kpis.map((k) => k.name) ?? ["fixed", "sched"];
  const pv: CurveDef[] = [{ name: "SP", key: "sp", color: "#64748b", dash: "2 3" },
    ...names.map((n) => ({ name: T(NAMES[n]), key: `pv_${n}`, color: COLORS[n], dash: n === "sched" ? undefined : "5 4" }))];
  const mv = names.map((n) => ({ name: T(NAMES[n]), key: `mv_${n}`, color: COLORS[n], dash: n === "sched" ? undefined : "5 4" }));
  const gain = ["fixed", "sched"].map((n) => ({ name: T(NAMES[n]), key: `gain_${n}`, color: COLORS[n], dash: n === "sched" ? undefined : "5 4" }));
  return (
    <ACard title={T("gs_er_sim")} testid="er-sim">
      <LineChart series={curveSeries(cv.data, pv)} height={220} yLabel={`PV ${String(st.u_pv ?? "")}`} xLabel={T("time_s")} testid="er-pv" />
      <LineChart series={curveSeries(cv.data, mv)} height={140} yLabel={`MV ${String(st.u_mv ?? "")}`} xLabel={T("time_s")} testid="er-mv" />
      <LineChart series={curveSeries(cv.data, gain)} height={120} yLabel="Gain" xLabel={T("time_s")} testid="er-gain" />
      <p className="small muted">{T("gs_er_sim_help")}</p>
    </ACard>
  );
}

function KpiBlock({ d }: { d: GsErInfo }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const { sim } = useSim<GsErSim>(["er-sim", d.inputs, d.base], "/apc/gainsched_er/simulate", "", {}, !d.integ);
  if (d.integ || !sim.data) return null;
  const ks = sim.data.kpis;
  return (
    <>
      <VariantTable testid="er-kpis" cols={ks.map((k) => ({ key: k.name, label: T(NAMES[k.name]) }))} rows={[
        { key: "iae_sp", label: T("iae_sp"), best: "min", values: ks.map((k) => k.iae_sp) },
        { key: "iae_d", label: T("iae_load"), best: "min", values: ks.map((k) => k.iae_d) },
        { key: "maxdev", label: T("gs_er_maxdev"), best: "min", values: ks.map((k) => k.maxdev) },
        { key: "sat", label: T("gs_er_sat"), values: ks.map((k) => `${(100 * k.sat).toFixed(0)} %`) },
        { key: "settled", label: T("gs_er_settled"), values: ks.map((k) => (k.settled ? "✓" : "✗")) }]} />
      <div className="small" data-testid="er-zone">{sim.data.zone != null
        ? T("gs_er_cz_best", { w: num(sim.data.zone), u: String(st.u_pv ?? "PV") }) : T("gs_er_cz_none")}</div>
      <div className="small muted">{T("gs_er_cz_help")}</div>
      {sim.data.scan.length > 0 && (
        <div className="apc-tblwrap"><table className="apc-vt" data-testid="er-scan">
          <thead><tr><th>{T("gs_er_cz_scan")}</th><th className="r">{T("iae_sp")}</th><th className="r">{T("gs_er_settled")}</th></tr></thead>
          <tbody>{sim.data.scan.map((s, i) => <tr key={i}><td className="mono">{num(s.width)}</td><td className="mono r">{num(s.iae)}</td>
            <td className="r">{s.settled ? "✓" : "✗"}</td></tr>)}</tbody>
        </table></div>
      )}
    </>
  );
}

export function GainSchedErMain() {
  const T = useT();
  const ws = useWs().data;
  const q = useEr();
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const d = q.data;
  if (d.integ) {
    return <div className="stack"><div className="card warn" data-testid="er-integ">⚠ {T("gs_integ")}</div><Checks items={d.checks} /></div>;
  }
  const kmax = d.k_max ?? 0;
  const bad = d.ms_k == null || d.ms_k > 2;
  return (
    <div className="stack">
      <SimCard d={d} />
      <ACard title={T("ui_apc_result")} testid="er-result">
        <div className="stack" data-testid="er-base">
          {d.base && <div className="small" data-testid="er-kmax">{T("gs_er_kmax", { g: num(d.base.Kc), ti: num(d.base.Ti), k: num(kmax) })}</div>}
          <div className="small">{T("gs_er_ms")}: <b className="mono" data-testid="er-ms">{d.ms_k == null ? "∞" : num(d.ms_k)}</b></div>
          {kmax <= 0 && <div className="warn small" data-testid="er-base-bad">⚠ {T("gs_er_base_bad")}</div>}
          {kmax > 0 && bad && <div className="warn small" data-testid="er-unstable">⚠ {T("gs_er_unstable", { k: num(d.inputs.k), m: num(kmax) })}</div>}
        </div>
        <KpiBlock d={d} />
      </ACard>
      <ACard title={T("gs_tab_title")} help={T("ui_apc_pcs_h")} testid="er-table-card">
        <PointTable rows={d.table} testid="er-table" />
      </ACard>
      <Impl text={d.impl_text} testid="er-impl" />
      <Checks items={d.checks} />
    </div>
  );
}
