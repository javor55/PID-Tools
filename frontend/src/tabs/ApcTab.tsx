// Záložka APC (M19): doporučení struktur pro aktivní smyčku, přepínač technik a panel zvolené techniky. Techniky jsou
// v `tabs/apc/` (seznam v index.ts); ty bez API zatím ukazují zástupný text.
import type { components } from "../api/schema";
import { Placeholder } from "../components/Placeholder";
import { useWs } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";
import { Bold, useApc } from "./apc/common";
import { technique, TECHNIQUES } from "./apc";

type Recommendation = components["schemas"]["Recommendation"];

function RecoCard() {
  const T = useT();
  const setTech = useUi((s) => s.setApcTech);
  const q = useApc<Recommendation[]>("reco", "/apc/recommend");
  return (
    <div className="card stack" data-testid="apc-reco">
      <h3>{T("dk_sec_reco")}</h3>
      {q.isError ? <div className="muted small">{T("need_model")}</div>
        : !q.data ? <div className="muted small">…</div>
        : !q.data.length ? <div className="muted small" data-testid="apc-reco-none">{T("dk_apc_none")}</div>
        : (
          <ul className="reco">{q.data.map((r) => (
            <li key={`${r.kind}-${r.other ?? ""}`} className="small" data-testid={`apc-reco-${r.kind}`}>💡 {r.text} —{" "}
              <button className="btn" onClick={() => setTech(r.kind)}>{T("g_open", { m: T("apc_" + r.kind) })}</button></li>))}
          </ul>
        )}
    </div>
  );
}

export function ApcMain() {
  const T = useT();
  const ws = useWs().data;
  const id = useUi((s) => s.apcTech);
  const setTech = useUi((s) => s.setApcTech);
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  const tech = technique(id);
  const Main = tech.Main;
  return (
    <div className="stack">
      <RecoCard />
      <div className="row" role="tablist" aria-label="APC" data-testid="apc-techs">
        {TECHNIQUES.map((t) => (
          <button key={t.id} role="tab" aria-selected={t.id === tech.id} className={t.id === tech.id ? "btn primary" : "btn"}
            data-testid={`apc-tech-${t.id}`} onClick={() => setTech(t.id)}>{T(t.label)}</button>))}
      </div>
      {tech.intro && (
        <details className="card small"><summary>{T("dk_sec_about")}</summary><Bold text={T(tech.intro)} /></details>)}
      <div className="stack" data-testid={`apc-${tech.id}`}>
        {Main ? <Main /> : <Placeholder milestone="M19" />}
      </div>
    </div>
  );
}

export function ApcSide() {
  const T = useT();
  const id = useUi((s) => s.apcTech);
  const Side = technique(id).Side;
  return Side ? <Side /> : <div className="muted">{T(technique(id).label)}</div>;
}
