// Nastavení aplikace na celou stránku (návrh Settings / RegLibrary): vlevo oddíly, vpravo obsah. Oddíly globálního nastavení
// jsou v AppSections.tsx (ukládají se na server), Regulátory (knihovna, editor, test použitelnosti) jsou samostatné.
import { useT } from "../i18n";
import { AppSection } from "./AppSections";
import { RegEditor } from "./RegEditor";
import { RegLibrary } from "./RegLibrary";
import { RegTest } from "./RegTest";
import { SECTIONS, useSettingsUi } from "./settingsStore";
import "./settings.css";

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
              title={T(`app_nav_${s}_h`)} onClick={() => setSection(s)}>
              <b>{T(`app_nav_${s}`)}</b><span>{T(`app_nav_${s}_sub`)}</span>
            </button>))}
        </nav>
        <div className="settings-body">
          {section !== "controllers" ? <AppSection id={section} />
            : view === "editor" ? <RegEditor /> : view === "test" ? <RegTest /> : <RegLibrary />}
        </div>
      </div>
    </div>
  );
}
