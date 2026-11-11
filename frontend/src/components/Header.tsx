// Hlavička podle návrhu: název, aktivní smyčka a „+ Další smyčka“, souhrn dat; vpravo Projekt a report, Nastavení a „?“.
// Pod ní řádek záložek s podtržením (Projekt a report není záložka, otevírá se tlačítkem).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { NAV_TABS, type Theme, useUi } from "../store";
import { HelpButton } from "./Guide";

type Loops = components["schemas"]["Loops"];

/** Délka záznamu stručně: 45 s, 12 min, 2 h, 1,5 h. */
export function fmtDuration(s: number | null | undefined, lang: string) {
  if (!s || !Number.isFinite(s)) return "";
  const nf = (v: number) => v.toLocaleString(lang, { maximumFractionDigits: v < 10 ? 1 : 0 });
  if (s < 120) return `${nf(s)} s`;
  if (s < 7200) return `${nf(s / 60)} min`;
  return `${nf(s / 3600)} h`;
}

/** Aktivní smyčka (výběr) a přidání další smyčky ze stejného souboru. */
function Loops() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  const qc = useQueryClient();
  const loops = useWsQuery<Loops>("loops", "/loops").data;
  const [busy, setBusy] = useState(false);
  const pick = async (index: number) => {
    await request("PUT", `/workspaces/${wid}/loops/active`, { index });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const add = async () => {
    setBusy(true);
    try {
      const r = await request<Loops>("POST", `/workspaces/${wid}/loops`, {});
      await request("PUT", `/workspaces/${wid}/loops/active`, { index: r.loops.length - 1 });
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
    } finally { setBusy(false); }
  };
  if (!ws?.has_data || !loops) return null;
  return (
    <div className="hloops" role="group" aria-label={T("ui_loops_group")}>
      <select aria-label={T("dk_loop")} title={T("h_loop_sel")} value={loops.active} data-testid="loop-select"
        onChange={(e) => void pick(+e.target.value)}>
        {loops.loops.map((l) => <option key={l.index} value={l.index}>{l.name || T("loop_n", { n: l.index + 1 })}</option>)}
      </select>
      <button type="button" className="hbtn small" onClick={() => void add()} disabled={busy} title={T("ui_loop_add_h")}
        data-testid="loop-add-head">+ {T("loop_add")}</button>
    </div>
  );
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
  const { tab, setTab, lang } = useUi();
  const ws = useWs().data;
  const sum = ws?.has_data ? T("ui_file_sum", {
    f: ws.fname, n: (ws.n ?? 0).toLocaleString(lang), ts: +(ws.Ts ?? 0).toPrecision(3), d: fmtDuration(ws.duration, lang),
  }) : "";
  return (
    <header className="header">
      <div className="hrow">
        <div className="hleft">
          <h1>PID Tools</h1>
          <Loops />
          {sum && <span className="hsum" data-testid="data-sum">{sum}</span>}
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
    </header>
  );
}
