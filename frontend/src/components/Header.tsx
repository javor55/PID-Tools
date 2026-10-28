import { useQueryClient } from "@tanstack/react-query";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { useWsQuery } from "../data";
import { useT } from "../i18n";
import { TABS, type Theme, useUi } from "../store";

type Loops = components["schemas"]["Loops"];

/** Aktivní smyčka projektu: výběr se ukáže, až má projekt víc smyček (správa smyček je na záložce Přehled smyček). */
function LoopSwitch() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const loops = useWsQuery<Loops>("loops", "/loops").data;
  if (!loops || loops.loops.length < 2) return null;
  const pick = async (index: number) => {
    await request("PUT", `/workspaces/${wid}/loops/active`, { index });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  return (
    <select aria-label={T("dk_loop")} title={T("dk_loop")} value={loops.active} data-testid="loop-select"
      onChange={(e) => void pick(+e.target.value)}>
      {loops.loops.map((l) => <option key={l.index} value={l.index}>{T("loop_n", { n: l.index + 1 })} · {l.name}</option>)}
    </select>
  );
}

export function Header() {
  const T = useT();
  const { tab, setTab, lang, setLang, theme, setTheme } = useUi();
  return (
    <header className="header">
      <h1>PID Tools</h1>
      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" className="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            data-tab={t.id}>
            {T(t.label)}
          </button>
        ))}
      </nav>
      <div className="tools">
        <LoopSwitch />
        <select aria-label={T("ui_lang")} value={lang} onChange={(e) => setLang(e.target.value as "cs" | "en")}>
          <option value="cs">CS</option>
          <option value="en">EN</option>
        </select>
        <select aria-label="theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
          <option value="system">{T("ui_theme_system")}</option>
          <option value="light">{T("ui_theme_light")}</option>
          <option value="dark">{T("ui_theme_dark")}</option>
        </select>
      </div>
    </header>
  );
}
