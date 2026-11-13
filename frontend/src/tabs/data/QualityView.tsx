// Data › Kvalita dat: je záznam vybrané smyčky vhodný pro identifikaci a ladění? Přepínač smyček (= aktivní smyčka),
// verdikt celého záznamu s kontrolami (q_*, text obsahuje i radu), jednoduchý graf smyčky (viewer.js s pevnými panely),
// události (klik = graf se posune), navržené úseky („Použít v Modelu“ nastaví úsek identifikace) a kontroly dat (dq_*).
import { useQueryClient } from "@tanstack/react-query";
import { request } from "../../api/client";
import type { components } from "../../api/schema";
import { Card } from "../../components/Card";
import { RecordViewer } from "../../components/RecordViewer";
import { useWs, useWsQuery } from "../../data";
import { useDec, useT, useTexts } from "../../i18n";
import { dur } from "../../lib/format";
import { useUi } from "../../store";
import { DataQualityCard } from "../DataQuality";
import "../../styles/quality.css";

type Summary = components["schemas"]["DqSummary"];
type Loops = components["schemas"]["Loops"];
const LEVEL = ["ok", "warn", "err"] as const;

const goto = (t: number) =>
  (window as unknown as { __pidView?: Record<string, { goto?: (t: number) => void }> }).__pidView?.quality_view?.goto?.(t);

function LoopSwitch() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const lp = useWsQuery<Loops>("loops", "/loops").data;
  if (!lp || lp.loops.length < 2) return null;
  const pick = async (i: number) => {
    await request("PUT", `/workspaces/${wid}/loops/active`, { index: i });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  return (
    <div className="dq-loops" role="group" aria-label={T("dq_loop_title")} data-testid="dq-loops">
      <span className="lbl">{T("dq_loop_title")}</span>
      {lp.loops.map((l, i) => (
        <button key={i} type="button" className="dq-loop" aria-pressed={i === lp.active} data-testid={`dq-loop-${i}`}
          title={T("dq_loop_switch_h")} onClick={() => void pick(i)}><b>{l.name}</b><span className="small muted">{l.pv}</span></button>))}
      <span className="small muted">{T("dq_loop_switch_note")}</span>
    </div>
  );
}

export function QualityMain() {
  const T = useT();
  const texts = useTexts();
  const dec = useDec();
  const wid = useUi((s) => s.wid);
  const setTab = useUi((s) => s.setTab);
  const qc = useQueryClient();
  const ws = useWs().data;
  const s = useWsQuery<Summary>("dqsummary", "/dataquality/summary").data;
  const applySeg = async (a: number, b: number) => {
    await request("PUT", `/workspaces/${wid}/range`, { a, b });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
    setTab("model");
  };
  const cnt = (lv: number) => s?.checks.filter((c) => c.level === lv).length ?? 0;
  const t = (x: number) => dur(x, dec);
  return (
    <div className="stack" data-testid="quality-main">
      <LoopSwitch />
      {s && (
        <div className={`dq-verdict ${LEVEL[s.level]}`} data-testid="dq-verdict" data-level={s.level}>
          <span className="dq-big" aria-hidden="true">{["✓", "!", "×"][s.level]}</span>
          <div>
            <h3>{T("dq_verdict", { n: ws?.pv ?? "", v: T(`q_level${s.level}`) })}</h3>
            <div className="small muted">{T("dq_verdict_sub", { d: t(ws?.duration ?? 0), n: s.segments.length })}</div>
          </div>
          <span className="dq-counts"><span className="ltag ok">{T("dq_n_ok", { n: cnt(0) })}</span>
            {cnt(1) > 0 && <span className="ltag warn">{T("dq_n_warn", { n: cnt(1) })}</span>}
            {cnt(2) > 0 && <span className="ltag err">{T("dq_n_err", { n: cnt(2) })}</span>}</span>
        </div>)}
      {s && (
        <Card title={T("dq_checks")} help="dq_checks_h" testid="dq-checks">
          <ul className="dq-list">
            {s.checks.map((c, i) => (
              <li key={i} className={`dq-chk ${LEVEL[c.level]}`} data-key={c.key}>
                <span className="dq-ic" aria-hidden="true">{["✓", "!", "×"][c.level]}</span>{T(c.key, c.args as Record<string, unknown>)}</li>))}
          </ul>
        </Card>)}
      <Card title={T("dq_chart")} help="dq_chart_h" testid="dq-chart">
        {texts && <RecordViewer texts={texts} simple />}
      </Card>
      {s && (
        <div className="dq-two">
          <Card title={T("dq_events")} help="dq_events_h" testid="dq-events">
            {!s.events.length ? <p className="small muted">{T("dq_events_none")}</p> : (
              <div className="dq-scroll"><table className="ltbl compact">
                <thead><tr><th>{T("dq_ev_time")}</th><th>{T("dq_ev_kind")}</th><th className="r">{T("dq_ev_size")}</th></tr></thead>
                <tbody>{s.events.map((e, i) => (
                  <tr key={i} className="pick" data-testid="dq-event" title={T("dq_events_h")} onClick={() => goto(e.t)}>
                    <td className="mono">{t(e.t)}</td>
                    <td>{T(`dq_ev_${e.kind}`, { m: e.text ?? "" })}{e.size != null ? (e.size > 0 ? " ↑" : " ↓") : ""}</td>
                    <td className="r mono">{e.size != null ? (+e.size.toPrecision(3)).toLocaleString() : ""}</td></tr>))}</tbody>
              </table></div>)}
          </Card>
          <Card title={T("dq_segs")} help="dq_segs_h" testid="dq-segs">
            {!s.segments.length ? <p className="small muted">{T("dq_segs_none")}</p> : (
              <table className="ltbl compact">
                <thead><tr><th>{T("dq_seg")}</th><th>{T("dq_seg_why")}</th><th /></tr></thead>
                <tbody>{s.segments.map((g, i) => (
                  <tr key={i} data-testid="dq-seg">
                    <td className="mono">{t(g.a)} – {t(g.b)}</td>
                    <td><span className={`ltag ${LEVEL[g.level]}`}>{T(`q_level${g.level}`)}</span>{" "}
                      <span className="small muted">{T("dq_seg_steps", { n: g.n_mv + g.n_sp })}</span></td>
                    <td className="r"><button type="button" className={"btn small" + (i === 0 ? " primary" : "")} data-testid={`dq-use-${i}`}
                      title={T("dq_use_h")} onClick={() => void applySeg(g.a, g.b)}>{T("dq_use")}</button></td>
                  </tr>))}</tbody>
              </table>)}
          </Card>
        </div>)}
      <DataQualityCard />
    </div>
  );
}
