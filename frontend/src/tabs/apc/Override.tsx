// APC › Override: hlavní a omezující regulátor na jednom ventilu, výběr MIN / MAX. Druhá smyčka projektu se volí ve
// výběru (?loop=); skok SP a mez jsou parametry simulace (chybějící = výchozí scénář z API).
import { create } from "zustand";
import type { components } from "../../api/schema";
import { type Band, LineChart } from "../../components/LineChart";
import { series } from "../../api/signals";
import { SideCard } from "../../components/Ui";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { type Curves, type CurveDef, curveSeries, NumInput, useApc } from "./common";
import { ACard, Checks, Impl, LoopSelect, PairError, qs, usePair, useSim, VariantTable } from "./parts";

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
    <>
      <SideCard title={T("apc_override_b")} testid="override-side">
        <LoopSelect kind="override" label={T("apc_override_b")} current={d?.loop ?? loop} />
      </SideCard>
      <SideCard title={T("ov_select")}>
        <label className="field" title={T("h_ov_select")}><span>{T("ov_select")}</span>
          <select value={sel} data-testid="ov-sel" onChange={(e) => set({ sel: e.target.value as Sel, step: undefined, lim: undefined })}>
            {SELS.map((s) => <option key={s} value={s}>{T("ov_" + s)}</option>)}</select></label>
        {d && (
          <>
            <label className="field" title={T("h_ov_step")}><span>{T("dk_ov_step")}</span>
              <NumInput value={step ?? d.defaults.step} testid="ov-step" onCommit={(x) => set({ step: x })} /></label>
            <label className="field" title={T("h_ov_limit")}><span>{T("dk_ov_limit")}</span>
              <NumInput value={lim ?? d.defaults.lim} testid="ov-lim" onCommit={(x) => set({ lim: x })} /></label>
          </>
        )}
        <button className="btn" data-testid="ov-reset" disabled={step === undefined && lim === undefined} title={T("h_apc_reset")}
          onClick={() => set({ step: undefined, lim: undefined })}>{T("apc_reset")}</button>
      </SideCard>
    </>
  );
}

/** Souvislé úseky, kde je signál `act` = 1 (pásma řízení omezujícím regulátorem). */
function actBands(c: Curves | undefined): Band[] {
  const a = c ? series(c.meta, c.blob, "act") : null;
  if (!a) return [];
  const out: Band[] = [];
  let from: number | null = null;
  for (let i = 0; i < a.t.length; i++) {
    const on = a.v[i] > 0.5;
    if (on && from === null) from = a.t[i];
    if (!on && from !== null) { out.push({ from, to: a.t[i], color: "#dc2626" }); from = null; }
  }
  if (from !== null) out.push({ from, to: a.t[a.t.length - 1], color: "#dc2626" });
  return out.slice(0, 200);
}

function SimCard({ d, loop }: { d: OvInfo; loop?: number }) {
  const T = useT();
  const { sel, step, lim } = useOv();
  const body = { sel, step, lim };
  const { cv } = useSim<OvSim>(["ov-sim", loop, body, d.defaults], "/apc/override/simulate", qs({ loop }), body);
  const without = T("ov_without");
  const pva: CurveDef[] = [{ name: "SP", key: "sp_a", color: "#9aa5b1", dash: "5 4" }, { name: without, key: "pv_a_without", color: "#64748b", dash: "2 3" },
    { name: d.a, key: "pv_a", color: "#1f5fa8" }];
  const pvb: CurveDef[] = [{ name: T("ov_limit_short"), key: "lim_b", color: "#dc2626", dash: "5 4" },
    { name: without, key: "pv_b_without", color: "#64748b", dash: "2 3" }, { name: d.b, key: "pv_b", color: "#7c3aed" }];
  const mv: CurveDef[] = [{ name: T("ov_out", { n: d.a }), key: "u_a", color: "#1f5fa8", dash: "5 4" },
    { name: T("ov_out", { n: d.b }), key: "u_b", color: "#7c3aed", dash: "5 4" }, { name: "MV", key: "mv", color: "#15803d" }];
  // pásma = doba, kdy řídí omezující regulátor (signál act = 1)
  const bands = actBands(cv.data);
  return (
    <ACard title={T("ui_apc_verify")} testid="ov-sim">
      <LineChart series={curveSeries(cv.data, pva)} height={200} yLabel={`PV ${d.a}`} xLabel={T("time_s")} testid="ov-pv-a" bands={bands} />
      <LineChart series={curveSeries(cv.data, pvb)} height={200} yLabel={`PV ${d.b}`} xLabel={T("time_s")} testid="ov-pv-b" bands={bands} />
      <LineChart series={curveSeries(cv.data, mv)} height={140} yLabel="MV" xLabel={T("time_s")} testid="ov-mv" bands={bands} />
      <p className="small muted" title={T("apc_ui_ov_bands_h")}>{T("ov_sim_help", { b: d.b })}{" "}
        <span className="apc-bandkey" data-testid="ov-bands-key"><i />{T("apc_ui_ov_bands")}: {T("apc_ui_ov_band_legend")}</span></p>
    </ACard>
  );
}

function KpiTable({ d, loop }: { d: OvInfo; loop?: number }) {
  const T = useT();
  const { sel, step, lim } = useOv();
  const { sim } = useSim<OvSim>(["ov-sim", loop, { sel, step, lim }, d.defaults], "/apc/override/simulate", qs({ loop }), { sel, step, lim });
  if (!sim.data) return null;
  const k = sim.data.kpis;
  return (
    <VariantTable testid="ov-kpis" cols={[{ key: "without", label: T("ov_without") }, { key: "with", label: T("apc_override") }]} rows={[
      { key: "peak", label: T("ov_peak", { n: d.b }), best: "min", values: [k.peak_without, k.peak], ids: ["ov-peak-without", "ov-peak"] },
      { key: "share", label: `${T("ov_time_b")} [%]`, values: [null, (100 * k.share).toFixed(0)], ids: [undefined, "ov-share"] },
      { key: "switches", label: T("ov_switches"), values: [null, k.switches], ids: [undefined, "ov-switches"], fmt: String }]} />
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
      <SimCard d={d} loop={loop} />
      <ACard title={T("ui_apc_result")} testid="ov-result">
        {d.mv_differs && (
          <div className="warn small" data-testid="ov-mv-differs">⚠ <b>{T("ov_mv_differs", { a: d.a, b: d.b, mva: d.mv_a, mvb: d.mv_b })}</b></div>)}
        <KpiTable d={d} loop={loop} />
      </ACard>
      <Impl text={d.impl_text} testid="ov-impl" />
      <Checks items={d.checks} />
    </div>
  );
}
