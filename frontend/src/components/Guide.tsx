// Průvodce záložky (tlačítko „?“ v hlavičce, F1) podle návrhu Guide.dc.html: karty Postup, Kontrolní seznam, Tabulka
// („Která metoda / Který model / Která struktura kdy“) a Slovníček; hledání v průvodci, slovníčku i popisech parametrů.
// Obsah a kontroly dodává API (GET /workspaces/{wid}/guide/{tab}), akce kontrolního seznamu přepnou záložku a skočí na prvek.
import "../styles/guide.css";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, request } from "../api/client";
import type { components } from "../api/schema";
import { useWs, useWsQuery } from "../data";
import { useT, useTexts } from "../i18n";
import { type TabId, useUi } from "../store";
import { LabelHelp, Md } from "./Ui";

export type Guide = components["schemas"]["Guide"];
type Action = NonNullable<components["schemas"]["GuideCheck"]["action"]>;
type Loops = components["schemas"]["Loops"];

const TAB_KEY: Record<TabId, string> = {
  data: "data", model: "model", tuning: "tuning", live: "live", apc: "apc", diag: "diag", loops: "audit", project: "project",
};
const CARDS = ["steps", "checklist", "tables", "glossary"] as const;
type Card = (typeof CARDS)[number];
const MARK = { ok: "✓", warn: "!", todo: "–" } as const;

/** Text bez diakritiky a velkých písmen (hledání „ladeni“ najde „Ladění“). */
const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Přepnutí na prvek záložky (data-testid): rozbalí nadřazené karty, posune, zaostří a krátce zvýrazní. */
export function focusTarget(target: string | null | undefined) {
  if (!target) return;
  const id = target === "add-loop" ? "loop-add-head" : target;
  let tries = 0;
  const tick = () => {
    const el = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    if (!el) { if (++tries < 40) window.setTimeout(tick, 75); return; }
    for (let d = el.closest("details"); d; d = d.parentElement?.closest("details") ?? null) if (!d.open) d.open = true;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.focus({ preventScroll: true });
    el.classList.add("guide-pulse");
    window.setTimeout(() => el.classList.remove("guide-pulse"), 2200);
  };
  window.setTimeout(tick, 120);                 // záložka se přepne a vykreslí až po tomto kliknutí
}

function Steps({ g }: { g: Guide }) {
  const T = useT();
  return (
    <section aria-label={T("ui_guide_steps")} className="g-col">
      <h3>{T("ui_guide_steps")}<LabelHelp text="h_guide_steps" /></h3>
      {g.intro && <Md text={g.intro} />}
      <ol className="g-steps">
        {g.steps.map((s, i) => (
          <li key={i}><span className="g-n" aria-hidden="true">{i + 1}</span>
            <div className="g-txt"><b>{s.title}</b>{s.text && <div className="g-sub"><Md text={s.text} /></div>}</div></li>))}
      </ol>
      {g.tips && <><h3>{T("tg_tab_tips")}</h3><Md text={g.tips} /></>}
    </section>
  );
}

function Checklist({ g, go }: { g: Guide; go: (a: Action) => void }) {
  const T = useT();
  const warn = g.checklist.filter((c) => c.ok === "warn").length;
  return (
    <section aria-label={T("ui_guide_checklist")} className="g-col g-check" data-testid="guide-checklist">
      <h3>{T("ui_guide_checklist")}<LabelHelp text="h_guide_checklist" />
        {warn > 0 && <span className="g-count">{T("ui_guide_warn_n", { n: warn })}</span>}</h3>
      <ul>
        {g.checklist.map((c, i) => (
          <li key={i} className={c.ok} data-ok={c.ok}>
            <span className="g-mark" role="img" aria-label={T("ui_guide_st_" + c.ok)}>{MARK[c.ok]}</span>
            <span className="g-ctext">{c.text}</span>
            {c.action && c.ok !== "ok" && (
              <button type="button" className="btn" title={T("ui_guide_go_h")} data-testid="guide-action"
                onClick={() => go(c.action as Action)}>→ {c.action.label}</button>)}
          </li>))}
      </ul>
    </section>
  );
}

function Tables({ g }: { g: Guide }) {
  const T = useT();
  return (
    <section aria-label={T("ui_guide_tables")} className="g-col" data-testid="guide-tables">
      {g.tables.length === 0 && <p className="muted small">{T("ui_guide_no_tables")}</p>}
      {g.tables.map((t, i) => <div key={i}><h3>{t.title}</h3><Md text={t.md} /></div>)}
    </section>
  );
}

function Glossary({ g, extra }: { g: Guide; extra?: boolean }) {
  const T = useT();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  return (
    <section aria-label={T("ui_guide_glossary")} className="g-col" data-testid="guide-glossary">
      <dl className="g-gloss">
        {g.glossary.map((x, i) => <div key={i}><dt>{x.term}</dt><dd><Md text={x.text} /></dd></div>)}
      </dl>
      {extra && <><h3>{T("about_title")}</h3><Md text={T("about_body", { v: health.data?.version ?? "" })} /></>}
    </section>
  );
}

/** Výsledky hledání: kroky a oddíly průvodce, slovníček a popisy parametrů (klíče h_* a *_help z překladů). */
function Results({ q, g }: { q: string; g: Guide }) {
  const T = useT();
  const texts = useTexts() ?? {};
  const n = norm(q.trim());
  const has = (s: string) => norm(s).includes(n);
  const params = useMemo(
    () => Object.entries(texts).filter(([k, v]) => (k.startsWith("h_") || k.endsWith("_help")) && has(v)).slice(0, 40),
    [texts, n],                       // eslint-disable-line react-hooks/exhaustive-deps
  );
  const steps = g.steps.filter((s) => has(s.title + " " + s.text));
  const tables = g.tables.filter((t) => has(t.title + " " + t.md));
  const gloss = g.glossary.filter((x) => has(x.term + " " + x.text));
  if (!steps.length && !tables.length && !gloss.length && !params.length)
    return <p className="muted" data-testid="guide-none">{T("ui_guide_none", { q })}</p>;
  return (
    <div className="g-results" data-testid="guide-results">
      {steps.length > 0 && <section><h3>{T("ui_guide_steps")}</h3>
        <ul>{steps.map((s, i) => <li key={i}><b>{s.title}</b>{s.text && <> – <Md text={s.text} /></>}</li>)}</ul></section>}
      {tables.length > 0 && <section><h3>{T("ui_guide_tables")}</h3>
        {tables.map((t, i) => <div key={i}><b>{t.title}</b><Md text={t.md} /></div>)}</section>}
      {gloss.length > 0 && <section><h3>{T("ui_guide_glossary")}</h3>
        <dl className="g-gloss">{gloss.map((x, i) => <div key={i}><dt>{x.term}</dt><dd><Md text={x.text} /></dd></div>)}</dl></section>}
      {params.length > 0 && <section><h3>{T("ui_guide_params")}</h3>
        <ul>{params.map(([k, v]) => <li key={k}>{v}</li>)}</ul></section>}
    </div>
  );
}

/** Tlačítko „?“ v hlavičce + dialog průvodce (F1, Esc zavře). */
export function HelpButton() {
  const T = useT();
  const tab0 = useUi((s) => s.tab);
  const sub = useUi((s) => s.dataSub);
  const tab: TabId = tab0 === "data" ? (sub === "diag-all" ? "loops" : sub === "diag-detail" ? "diag" : "data") : tab0;      // průvodce Diagnostiky
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const setTab = useUi((s) => s.setTab);
  const ws = useWs().data;
  const loops = useWsQuery<Loops>("loops", "/loops").data;
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [card, setCard] = useState<Card>("steps");
  const [q, setQ] = useState("");
  const g = useQuery({
    queryKey: ["ws", wid, "guide", tab, lang], enabled: !!wid && open,
    queryFn: () => request<Guide>("GET", `/workspaces/${wid}/guide/${tab}`),
  });
  const show = () => { if (!ref.current?.open) { ref.current?.showModal(); setCard("steps"); } setOpen(true); };
  const hide = () => { ref.current?.close(); };
  useEffect(() => {
    const f1 = (e: KeyboardEvent) => { if (e.key === "F1") { e.preventDefault(); show(); } };
    window.addEventListener("keydown", f1);
    return () => window.removeEventListener("keydown", f1);
  }, []);
  const key = TAB_KEY[tab];
  const name = T(`tg_name_${key}`);
  const loop = loops?.loops.find((l) => l.index === loops.active);
  const loopName = loop ? (loop.name || T("loop_n", { n: loop.index + 1 })) : "";
  const go = (a: Action) => {
    hide();
    setTab(a.tab as TabId);
    focusTarget(a.target);
  };
  const data = g.data;
  return (
    <>
      <button type="button" className="hbtn qbtn" aria-label={T("ui_help_tab")} title={T("h_tb_help")}
        onClick={show} data-testid="help-btn">?</button>
      <dialog ref={ref} className="help guide" data-testid="help-dialog" aria-label={T("ui_guide_title", { m: name })}
        onClose={() => { setOpen(false); setQ(""); }}
        onClick={(e) => { if (e.target === ref.current) hide(); }}>
        <div className="help-head">
          <h2>{T("ui_guide_title", { m: name })}</h2>
          <span className="g-sub">F1{loopName && ws?.has_data ? ` · ${T("ui_guide_loop", { n: loopName })}` : ""}</span>
          <button type="button" className="g-close" aria-label={T("ui_close")} title={T("ui_guide_close_h")} onClick={hide}>×</button>
        </div>
        <nav className="g-tabs" role="tablist" aria-label={T("ui_guide_cards")}>
          {CARDS.map((c) => (
            <button key={c} type="button" role="tab" aria-selected={card === c && !q.trim()} data-testid={`guide-tab-${c}`}
              onClick={() => { setCard(c); setQ(""); }}>
              {c === "tables" ? (data?.tables[0]?.title ?? T("ui_guide_tables")) : T(`ui_guide_${c}`)}
              {c === "checklist" && data && data.checklist.some((x) => x.ok === "warn") && <span className="g-dot" aria-hidden="true" />}
            </button>))}
        </nav>
        <div className="g-body">
          {!data ? <p className="muted">{g.isError ? T("ui_guide_err") : "…"}</p>
            : q.trim() ? <Results q={q} g={data} />
            : card === "steps" ? <Steps g={data} />
            : card === "checklist" ? <Checklist g={data} go={go} />
            : card === "tables" ? <Tables g={data} />
            : <Glossary g={data} extra />}
        </div>
        <div className="g-foot">
          <span className="g-sub">{T("ui_guide_hint")}</span>
          <input type="search" aria-label={T("ui_guide_search")} placeholder={T("ui_guide_search")} title={T("ui_guide_search_h")}
            value={q} onChange={(e) => setQ(e.target.value)} data-testid="guide-search" />
        </div>
      </dialog>
    </>
  );
}
