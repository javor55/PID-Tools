// Model 2 (M15): rezidua modelu – průběh v čase (z /model/curves), ACF a CCF s mezemi (z /model/validation) a hodnocení
// bělosti reziduí stejnými texty jako desktop.
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { binary } from "../api/client";
import type { components } from "../api/schema";
import { series, unframe } from "../api/signals";
import { BarChart } from "../components/BarChart";
import { LineChart } from "../components/LineChart";
import { useWsQuery } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";

type ModelState = components["schemas"]["ModelState"];
type Validation = components["schemas"]["Validation"];

interface Metrics { acf: number[]; ccf: number[]; bound: number; lag_step: number; frac_acf: number; frac_ccf: number; status: number }

export function ModelResiduals({ model }: { model: ModelState }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const ok = !!model.current && !model.stale;
  const val = useWsQuery<Validation>("validation", "/model/validation", ok);
  const curves = useQuery({
    queryKey: ["ws", wid, "curves", model.current, model.selected], enabled: !!wid && ok,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/model/curves`)),
  });
  const res = useMemo(() => (curves.data ? series(curves.data.meta, curves.data.blob, "residual") : null), [curves.data]);
  const resid = useMemo(() => {
    if (!res) return null;
    let n = 0;
    for (let i = 0; i < res.v.length; i++) if (Number.isFinite(res.v[i])) n++;
    return { n, s: [{ name: T("resid"), x: res.t, y: res.v, color: "#dc2626", width: 1.2 }] };
  }, [res, T]);
  const m = val.data?.metrics as Metrics | undefined;
  if (!ok) return null;
  const msgs = m ? [T("eval_st_" + m.status), m.frac_ccf > 0.2 ? T("eval_ccf_bad") : m.frac_acf > 0.5 ? T("eval_acf_bad") : T("eval_res_ok")] : [];
  const lags = (n: number, start: number) => Array.from({ length: n }, (_, i) => (i + start) * m!.lag_step);
  return (
    <div className="card" data-testid="residuals">
      <h3>{T("resid")}</h3>
      {resid && <div data-testid="resid-chart" data-n={resid.n}><LineChart series={resid.s} height={180} xLabel="t [s]" /></div>}
      {m && (
        <div className="grid2">
          <div><div className="small">{T("eval_acf_t")}</div>
            <BarChart testid="acf-chart" lags={lags(m.acf.length, 1)} values={m.acf} bound={m.bound} xLabel={T("lag_s")} /></div>
          <div><div className="small">{T("eval_ccf_t")}</div>
            <BarChart testid="ccf-chart" lags={lags(m.ccf.length, 0)} values={m.ccf} bound={m.bound} xLabel={T("lag_s")} /></div>
        </div>
      )}
      <div className="small" data-testid="resid-verdict">{msgs.map((s, i) => <div key={i}>{s.replace(/\*\*/g, "")}</div>)}</div>
    </div>
  );
}
