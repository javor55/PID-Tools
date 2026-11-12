// Hlavička podle návrhu: název, aktivní smyčka a „+ Další smyčka“, souhrn dat; vpravo Projekt a report, Nastavení a „?“.
// Pod ní řádek záložek s podtržením (Projekt a report není záložka, otevírá se tlačítkem).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { type DataSub, isDiagSub, NAV_TABS, type Theme, useUi } from "../store";
import { HelpButton } from "./Guide";
import { Seg } from "./Ui";

type LoopsT = components["schemas"]["Loops"];
type Loop = components["schemas"]["Loop"];
type Mapping = components["schemas"]["LoopMapping"];
type Sources = components["schemas"]["Sources"];

/** Délka záznamu stručně: 45 s, 12 min, 2 h, 1,5 h. */
export function fmtDuration(s: number | null | undefined, lang: string) {
  if (!s || !Number.isFinite(s)) return "";
  const nf = (v: number) => v.toLocaleString(lang, { maximumFractionDigits: v < 10 ? 1 : 0 });
  if (s < 120) return `${nf(s)} s`;
  if (s < 7200) return `${nf(s / 60)} min`;
  return `${nf(s / 3600)} h`;
}

/** Skupiny výběru smyčky. Seskupení je na jednom místě – E5 sem doplní verdikty z diagnostiky. */
export type LoopGroup = "work" | "nomodel" | "incomplete";
export const LOOP_GROUPS: LoopGroup[] = ["work", "nomodel", "incomplete"];
export function loopGroup(l: Loop, m?: Mapping): LoopGroup {
  if (m ? !m.has_data || !m.roles.pv || !m.roles.mv : !l.pv || !l.mv) return "incomplete";
  return l.has_model ? "work" : "nomodel";
}
const loopLabel = (l: Loop, m: Mapping | undefined, T: ReturnType<typeof useT>) => {
  const tag = m?.tag || l.name || T("loop_n", { n: l.index + 1 });
  return m?.description ? `${tag} · ${m.description}` : tag;
};

/** Aktivní smyčka (výběr s hlavičkami skupin, stav) a „+ Smyčka“ (otevře Data › Zdroje a smyčky). */
function Loops() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const setDataSub = useUi((s) => s.setDataSub);
  const ws = useWs().data;
  const qc = useQueryClient();
  const loops = useWsQuery<LoopsT>("loops", "/loops").data;
  const maps = useWsQuery<Mapping[]>("mappings", "/loops/mappings").data;
  const pick = async (index: number) => {
    await request("PUT", `/workspaces/${wid}/loops/active`, { index });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  if (!ws?.has_data || !loops) return null;
  const mapOf = (l: Loop) => maps?.find((m) => m.index === l.index);
  const act = loops.loops.find((l) => l.index === loops.active);
  const stText = (g: LoopGroup) => T(`ui_loop_st_${g}`);
  const pill = act ? loopGroup(act, mapOf(act)) : null;
  return (
    <div className="hloops" role="group" aria-label={T("ui_loops_group")}>
      <select aria-label={T("dk_loop")} title={T("h_loop_sel")} value={loops.active} data-testid="loop-select"
        onChange={(e) => void pick(+e.target.value)}>
        {LOOP_GROUPS.map((g) => {
          const ls = loops.loops.filter((l) => loopGroup(l, mapOf(l)) === g);
          return ls.length > 0 && (
            <optgroup key={g} label={T(`ui_loop_grp_${g}`)}>
              {ls.map((l) => <option key={l.index} value={l.index}>{loopLabel(l, mapOf(l), T)} — {stText(g)}</option>)}
            </optgroup>
          );
        })}
      </select>
      {pill && <span className={`hpill ${pill}`} data-testid="loop-status" title={T("ui_loop_st_pill", { s: stText(pill) })}>{stText(pill)}</span>}
      <button type="button" className="hbtn small" onClick={() => setDataSub("sources")} title={T("ui_loop_add_go")}
        data-testid="loop-add-head">{T("ui_loop_add_short")}</button>
    </div>
  );
}

/** „3 soubory“ – tvar podle počtu (český tvar 1 | 2–4 | 5+ je v textu oddělený svislítkem). */
export function plural(T: ReturnType<typeof useT>, key: string, n: number) {
  const forms = T(key).split("|");
  const f = n === 1 ? forms[0] : n >= 2 && n <= 4 ? forms[1] : forms[2] ?? forms[1] ?? forms[0];
  return (f ?? "").replace("{n}", String(n));
}

/** Souhrn projektu: „3 soubory · 9 smyček · stav z 10:32“. */
function Summary() {
  const T = useT();
  const q = useWs();
  const ws = q.data;
  const src = useWsQuery<Sources>("sources", "/sources").data;
  const loops = useWsQuery<LoopsT>("loops", "/loops").data;
  const lang = useUi((s) => s.lang);
  if (!ws?.has_data) return null;
  const nf = src?.sources.length ?? 1;
  const t = new Date(q.dataUpdatedAt).toLocaleTimeString(lang === "cs" ? "cs-CZ" : "en-GB", { hour: "2-digit", minute: "2-digit" });
  const sum = T("ui_hsum", { f: plural(T, "ui_n_files", nf), l: plural(T, "ui_n_loops", loops?.loops.length ?? 1), t });
  return <span className="hsum" data-testid="data-sum" title={T("h_hsum")}>{sum}</span>;
}

/** Nastavení (jazyk, vzhled) jako rozbalovací panel pod tlačítkem. */
function Settings() {
  const T = useT();
  const { lang, setLang, theme, setTheme } = useUi();
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current?.open && !ref.current.contains(e.target as Node)) ref.current.open = false;
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <details className="pop" ref={ref} data-testid="settings">
      <summary className="hbtn">{T("tb_settings")}</summary>
      <div className="pop-body">
        <label className="field">
          <span>{T("ui_lang")}</span>
          <select aria-label={T("ui_lang")} value={lang} onChange={(e) => setLang(e.target.value as "cs" | "en")}>
            <option value="cs">Čeština</option>
            <option value="en">English</option>
          </select>
        </label>
        <label className="field">
          <span>{T("ui_theme")}</span>
          <select aria-label="theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
            <option value="system">{T("ui_theme_system")}</option>
            <option value="light">{T("ui_theme_light")}</option>
            <option value="dark">{T("ui_theme_dark")}</option>
          </select>
        </label>
      </div>
    </details>
  );
}

export function Header() {
  const T = useT();
  const { tab, setTab } = useUi();
  return (
    <header className="header">
      <div className="hrow">
        <div className="hleft">
          <h1>PID Tools</h1>
          <Loops />
          <Summary />
        </div>
        <div className="hright">
          <button type="button" className="hbtn" aria-pressed={tab === "project"} data-tab="project"
            onClick={() => setTab("project")}>{T("tab_project")}</button>
          <Settings />
          <HelpButton />
        </div>
      </div>
      <nav className="tabs" role="tablist" aria-label={T("ui_tabs")}>
        {NAV_TABS.map((t) => (
          <button key={t.id} role="tab" className="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            data-tab={t.id}>
            {T(t.label)}
          </button>
        ))}
      </nav>
      {tab === "data" && <DataSubNav />}
    </header>
  );
}

/** Podzáložky Data (Zdroje a smyčky · Trendy · Kvalita dat · Diagnostika) + u Diagnostiky přepínač Všechny smyčky / Detail. */
function DataSubNav() {
  const T = useT();
  const { dataSub, setDataSub } = useUi();
  const items: { id: string; to: DataSub; label: string; help: string; on: boolean }[] = [
    { id: "sources", to: "sources", label: "ui_dsub_sources", help: "h_dsub_sources", on: dataSub === "sources" },
    { id: "trends", to: "trends", label: "ui_dsub_trends", help: "h_dsub_trends", on: dataSub === "trends" },
    { id: "quality", to: "quality", label: "ui_dsub_quality", help: "h_dsub_quality", on: dataSub === "quality" },
    { id: "diag", to: isDiagSub(dataSub) ? dataSub : "diag-all", label: "ui_dsub_diag", help: "h_dsub_diag", on: isDiagSub(dataSub) },
  ];
  return (
    <nav className="subtabs" role="tablist" aria-label={T("ui_dsubs")} data-testid="data-subtabs">
      {items.map((t) => (
        <button key={t.label} role="tab" className="subtab" aria-selected={t.on} title={T(t.help)} data-sub={t.id}
          onClick={() => setDataSub(t.to)}>{T(t.label)}</button>
      ))}
      {isDiagSub(dataSub) && (
        <Seg value={dataSub} options={["diag-all", "diag-detail"] as const} label={T("ui_dsub_diag")} small testid="diag-sub"
          fmt={(v) => T(v === "diag-all" ? "ui_dsub_diag_all" : "ui_dsub_diag_detail")}
          titles={(v) => T(v === "diag-all" ? "h_dsub_diag_all" : "h_dsub_diag_detail")} help="h_dsub_diag" onChange={setDataSub} />
      )}
    </nav>
  );
}
