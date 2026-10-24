// APC › Interakce N×N (RGA): matice zesílení, relativní zisková matice, Niederlinskiho index a doporučené párování ze
// smyček projektu; s jednou smyčkou kontrolní seznam, co chybí. Bez vlastních vstupů.
import type { components } from "../../api/schema";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { Bold, num, useApc } from "./common";
import { Checks, g } from "./moreCommon";

type RgaInfo = components["schemas"]["RgaInfo"];

function Matrix({ d, m, testid, title, mark }: { d: RgaInfo; m: (number | null)[][]; testid: string; title: string; mark?: boolean }) {
  const T = useT();
  return (
    <div className="card stack">
      <div className="small"><b>{title}</b></div>
      <table className="tbl" data-testid={testid}>
        <thead><tr><th></th>{d.mvs.map((mv) => <th key={mv}>{T("rga_mv")} {mv}</th>)}</tr></thead>
        <tbody>{d.names.map((n, i) => (
          <tr key={n}><td>{n}</td>{m[i].map((x, j) => (
            <td key={j} className="mono" data-testid={`${testid}-${i}-${j}`}>{mark && !d.known[i][j] ? "? " : ""}{num(x)}</td>))}</tr>))}</tbody>
      </table>
    </div>
  );
}

export function RgaMain() {
  const T = useT();
  const ws = useWs().data;
  const q = useApc<RgaInfo>("rga", "/apc/rga");
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const d = q.data;
  if (!d.ready) {
    return (
      <div className="card stack" data-testid="rga-notready">
        <div className="warn small">⚠️ {T("apc_need_loop")}</div>
        <Checks items={d.checks} testid="rga-checks" />
      </div>
    );
  }
  const args = { a: d.names[0], b: d.names[1], mva: d.mvs[0], mvb: d.mvs[1] };
  return (
    <div className="stack">
      <div className="card stack" data-testid="rga-result">
        {d.NI != null && <div className="small"><b>NI = <span data-testid="rga-ni">{g(d.NI)}</span></b></div>}
        {d.pairing && (
          <div className="small" data-testid="rga-pairing">{T("rga_pairing")}: {d.names.map((n, i) => `${n} ← ${d.mvs[d.pairing![i]]}`).join(", ")}</div>)}
        {d.advice.map((n) => <div key={n.key} className="small"><Bold text={T(n.key, { ...args, ...(n.args as Record<string, unknown>) })} /></div>)}
      </div>
      <Matrix d={d} m={d.K} testid="rga-k" title={T("rga_k")} mark />
      <Matrix d={d} m={d.L} testid="rga-l" title={T("rga_l")} />
      <div className="card stack"><Checks items={d.checks} testid="rga-checks" /></div>
    </div>
  );
}
