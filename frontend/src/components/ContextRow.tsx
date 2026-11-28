// Řádek „Pracujete na: TAG · popis · data … · model … · regulátor …“ pod hlavičkou záložek Model, Ladění, APC a Živá simulace
// (návrh v2). „Změnit data / smyčku…“ vede do Data › Zdroje a smyčky.
import type { components } from "../api/schema";
import { useSettings, useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";
import { runGuideAction } from "./Guide";
import { LabelHelp } from "./Ui";

type Loops = components["schemas"]["Loops"];
type Mapping = components["schemas"]["LoopMapping"];
type GuideStatus = components["schemas"]["GuideStatus"];
type ModelState = components["schemas"]["ModelState"];

export function ContextRow() {
  const T = useT();
  const setDataSub = useUi((s) => s.setDataSub);
  const ws = useWs().data;
  const loops = useWsQuery<Loops>("loops", "/loops").data;
  const maps = useWsQuery<Mapping[]>("mappings", "/loops/mappings").data;
  const model = useWsQuery<ModelState>("model", "/model").data;
  const set = useSettings().data;
  const next = useWsQuery<GuideStatus>("guide-status", "/guide/status").data?.next;
  if (!ws?.has_data || !loops) return null;
  const l = loops.loops.find((x) => x.index === loops.active);
  const m = maps?.find((x) => x.index === loops.active);
  const tag = m?.tag || l?.name || T("loop_n", { n: loops.active + 1 });
  const code = model?.current?.code as string | undefined;
  const g = Number(set?.set1_gain), ti = Number(set?.set1_ti), td = Number(set?.set1_td);
  const reg = Number.isFinite(g) && !(g === 1 && ti === 100 && td === 0);        // výchozí zástupné hodnoty = nenastaveno
  const dot = <span className="sep" aria-hidden="true">·</span>;
  return (
    <div className="ctx" data-testid="context-row">
      <span>{T("ui_ctx_work")} <b data-testid="ctx-loop">{tag}{m?.description ? ` · ${m.description}` : ""}</b></span>{dot}
      <span>{T("ui_ctx_data", { f: ws.fname })}</span>{dot}
      <span>{T("ui_ctx_roles", { pv: ws.pv ?? "–", mv: ws.mv ?? "–" })}</span>{dot}
      <span data-testid="ctx-model">{code ? T("ui_ctx_model", { m: code }) : T("ui_ctx_nomodel")}</span>{dot}
      <span data-testid="ctx-reg">{reg ? T("ui_ctx_reg", { k: +g.toPrecision(3), ti: +ti.toPrecision(3) }) : T("ui_ctx_noreg")}</span>
      <LabelHelp text="h_ctx" />
      {next && (
        <span className="next" data-testid="next-step" title={T("nav_next", { t: next.text })}>
          <span className="next-text">{T("nav_next", { t: next.text })}</span>
          <button type="button" className="hbtn small" data-testid="next-open" title={T("nav_open_h")}
            onClick={() => runGuideAction(next.action ?? { tab: next.tab })}>{T("nav_open")}</button>
        </span>
      )}
      <button type="button" className="link" title={T("h_ctx_change")} onClick={() => setDataSub("sources")}
        data-testid="ctx-change">{T("ui_ctx_change")}</button>
    </div>
  );
}
