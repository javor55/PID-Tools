// Nastavení aplikace na celou stránku (návrh Settings / RegLibrary): vlevo oddíly, vpravo obsah. Oddíl Regulátory
// (knihovna, editor, test použitelnosti) je hotový, Obecné = jazyk a vzhled; ostatní oddíly návrhu přijdou s dalšími etapami.
import { LabelHelp } from "../components/Ui";
import { useT } from "../i18n";
import { type Theme, useUi } from "../store";
import { RegEditor } from "./RegEditor";
import { RegLibrary } from "./RegLibrary";
import { RegTest } from "./RegTest";
import { type Section, useSettingsUi } from "./settingsStore";
import "./settings.css";

const SECTIONS: Section[] = ["general", "controllers"];

function General() {
  const T = useT();
  const { lang, setLang, theme, setTheme } = useUi();
  return (
    <section className="card rg-sec rg-general" data-testid="settings-general">
      <h2>{T("rg_ui_sec_general")}</h2>
      <label className="field">
        <span className="lbl"><span>{T("ui_lang")}</span><LabelHelp text="rg_ui_lang_h" /></span>
        <select value={lang} onChange={(e) => setLang(e.target.value as "cs" | "en")}>
          <option value="cs">Čeština</option><option value="en">English</option>
        </select>
      </label>
      <label className="field">
        <span className="lbl"><span>{T("ui_theme")}</span><LabelHelp text="rg_ui_theme_h" /></span>
        <select value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
          <option value="system">{T("ui_theme_system")}</option><option value="light">{T("ui_theme_light")}</option>
          <option value="dark">{T("ui_theme_dark")}</option>
        </select>
      </label>
      <p className="rg-note">{T("rg_ui_more_soon")}</p>
    </section>
  );
}

export function SettingsPage() {
  const T = useT();
  const { section, setSection, view, close } = useSettingsUi();
  return (
    <div className="settings-page" data-testid="settings-page">
      <div className="settings-top">
        <button type="button" className="btn" data-testid="settings-back" title={T("rg_ui_back_project_h")} onClick={close}>{T("rg_ui_back_project")}</button>
        <h1>{T("rg_ui_settings_title")}</h1>
        <span className="rg-note">{T("rg_ui_settings_sub")}</span>
      </div>
      <div className="settings-grid">
        <nav className="card settings-nav" aria-label={T("rg_ui_settings_title")}>
          {SECTIONS.map((s) => (
            <button key={s} type="button" className="settings-nav-i" aria-current={section === s} data-testid={`settings-nav-${s}`}
              title={T(`rg_ui_nav_${s}_h`)} onClick={() => setSection(s)}>
              <b>{T(`rg_ui_nav_${s}`)}</b><span>{T(`rg_ui_nav_${s}_sub`)}</span>
            </button>))}
        </nav>
        <div className="settings-body">
          {section === "general" ? <General />
            : view === "editor" ? <RegEditor /> : view === "test" ? <RegTest /> : <RegLibrary />}
        </div>
      </div>
    </div>
  );
}
