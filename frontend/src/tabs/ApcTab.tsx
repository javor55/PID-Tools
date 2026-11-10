// Záložka APC (M19) podle návrhu Apc.dc.html: doporučení se štítky stavu, záložky struktur (11 technik z `tabs/apc/`),
// v ploše ověření / výsledek / hodnoty do PCS 7, v pravém panelu karty Průvodce a nastavení zvolené techniky.
import "../styles/apc.css";
import type { components } from "../api/schema";
import { Placeholder } from "../components/Placeholder";
import { Help, Md, SideCard } from "../components/Ui";
import { useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";
import { Bold, useApc } from "./apc/common";
import { useGuideSlot, useOthers } from "./apc/parts";
import { technique, TECHNIQUES } from "./apc";

type Recommendation = components["schemas"]["Recommendation"];
type Loops = components["schemas"]["Loops"];

/** Struktury, které potřebují druhou smyčku projektu. */
const NEED2 = ["cascade", "decouple", "override", "vpc", "split", "ratio", "rga"];

function useLoopName() {
  const T = useT();
  const loops = useWsQuery<Loops>("loops", "/loops").data;
  const l = loops?.loops.find((x) => x.index === loops.active);
  return l ? (l.name || T("loop_n", { n: l.index + 1 })) : "";
}

function RecoCard() {
  const T = useT();
  const setTech = useUi((s) => s.setApcTech);
  const cur = useUi((s) => s.apcTech);
  const name = useLoopName();
  const { loops, pending } = useOthers();
  const q = useApc<Recommendation[]>("reco", "/apc/recommend");
  return (
    <section className="card apc-card" data-testid="apc-reco" aria-label={T("dk_sec_reco")}>
      <div className="apc-card-h"><h2>{T("g_reco_for", { n: name })}<Help text={T("h_g_reco")} /></h2></div>
      {q.isError ? <div className="muted small">{T("need_model")}</div>
        : !q.data ? <div className="muted small">…</div>
        : (
          <>
            {!q.data.length && <div className="muted small" data-testid="apc-reco-none">{T("g_reco_none")}</div>}
            <ul className="apc-reco">{q.data.map((r) => (
              <li key={`${r.kind}-${r.other ?? ""}`} data-testid={`apc-reco-${r.kind}`}>
                <span className="apc-tag ok">✓ {T("g_st_rec")}</span>
                <span><b>{T("apc_" + r.kind)}</b> – {r.text}{" "}
                  {cur !== r.kind && (
                    <button type="button" className="link" onClick={() => setTech(r.kind)}>{T("g_open_short")}</button>)}</span>
              </li>))}</ul>
            {!pending && !loops.length && (
              <div className="apc-reco-row" data-testid="apc-reco-need2">
                <span className="apc-tag info">i {T("g_st_need2")}</span>
                <span><Bold text={T("g_reco_need2", { k: NEED2.map((k) => T("apc_" + k)).join(", ") })} /></span>
              </div>)}
          </>
        )}
    </section>
  );
}

/** Záložky struktur (podtržení): ✓ = doporučeno, štítek „2. smyčka“ = potřebuje další smyčku projektu. */
function Tabs({ rec }: { rec: Set<string> }) {
  const T = useT();
  const id = useUi((s) => s.apcTech);
  const setTech = useUi((s) => s.setApcTech);
  const { loops, pending } = useOthers();
  const one = !pending && !loops.length;
  return (
    <div className="apc-tabs" role="tablist" aria-label={T("apc_kind")} data-testid="apc-techs">
      {TECHNIQUES.map((t) => (
        <button key={t.id} role="tab" type="button" aria-selected={t.id === id} data-testid={`apc-tech-${t.id}`}
          className={t.id === id ? "on" : undefined} onClick={() => setTech(t.id)}>
          {rec.has(t.id) ? "✓ " : ""}{T(t.label)}
          {one && NEED2.includes(t.id) && <span className="apc-pill">{T("g_st_need2")}</span>}
        </button>))}
    </div>
  );
}

export function ApcMain() {
  const T = useT();
  const ws = useWs().data;
  const id = useUi((s) => s.apcTech);
  const reco = useApc<Recommendation[]>("reco", "/apc/recommend");
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  const tech = technique(id);
  const Main = tech.Main;
  return (
    <div className="stack apc-main">
      <RecoCard />
      <Tabs rec={new Set((reco.data ?? []).map((r) => r.kind))} />
      {tech.intro && tech.id !== "cascade" && <p className="apc-intro small muted"><Bold text={T(tech.intro)} /></p>}
      <div className="stack" data-testid={`apc-${tech.id}`}>
        {Main ? <Main /> : <Placeholder milestone="M19" />}
      </div>
    </div>
  );
}

export function ApcSide() {
  const T = useT();
  const id = useUi((s) => s.apcTech);
  const setSlot = useGuideSlot((s) => s.set);
  const tech = technique(id);
  const Side = tech.Side;
  const has = (k: string) => T(k) !== k;
  return (
    <>
      <SideCard title={T("g_side_title", { m: T(tech.label) })} testid="apc-guide">
        {has(`g_${id}_when`) && <Md text={T(`g_${id}_when`)} />}
        {has(`g_${id}_examples`) && <Md text={T(`g_${id}_examples`)} />}
        <div ref={setSlot} className="apc-guide-slot" />
      </SideCard>
      {Side && <Side />}
    </>
  );
}
