import { useT } from "../i18n";
import { TABS, type Theme, useUi } from "../store";

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
