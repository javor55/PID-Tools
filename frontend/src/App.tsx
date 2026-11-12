import { useEffect } from "react";
import { api, ApiError, setLang } from "./api/client";
import { Header } from "./components/Header";
import { StatusBar } from "./components/StatusBar";
import { useT } from "./i18n";
import { ApcMain, ApcSide } from "./tabs/ApcTab";
import { ContextRow } from "./components/ContextRow";
import { DataMain, DataSide } from "./tabs/DataTab";
import { DiagMain, DiagSide } from "./tabs/DiagTab";
import { LiveMain } from "./tabs/LiveTab";
import { TriageMain, TriageSide } from "./tabs/TriageTab";
import { ProjectMain, ProjectSide, usePendingOpen } from "./tabs/ProjectTab";
import { ModelMain, ModelSide } from "./tabs/ModelTab";
import { TuningMain, TuningSide } from "./tabs/TuningTab";
import { SourcesMain, SourcesSide } from "./tabs/data/SourcesView";
import { TrendsMain, TrendsSide } from "./tabs/data/TrendsView";
import { SettingsPage } from "./settings/SettingsPage";
import { useSettingsUi } from "./settings/settingsStore";
import { useAppSettingsSync } from "./settings/appSettings";
import { StartScreen } from "./start/StartScreen";
import { useAutosave } from "./start/project";
import { useWs } from "./data";
import { type TabId, TABS, useUi } from "./store";

const CONTEXT_TABS: TabId[] = ["model", "tuning", "apc", "live"];

function useTheme() {
  const theme = useUi((s) => s.theme);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && !!mq?.matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    mq?.addEventListener?.("change", apply);
    return () => mq?.removeEventListener?.("change", apply);
  }, [theme]);
}

function useWorkspace() {
  const { wid, setWid } = useUi();
  useEffect(() => {
    if (wid) {          // uložené ID z minula – po restartu serveru už neplatí → nový prostor
      api.workspace(wid).catch((e) => { if (e instanceof ApiError && e.status === 404) setWid(null); });
      return;
    }
    api.createWorkspace().then((w) => setWid(w.id)).catch(() => setWid(null));
  }, [wid, setWid]);
}

export default function App() {
  const T = useT();
  const lang = useUi((s) => s.lang);
  const tab = useUi((s) => s.tab);
  const sub = useUi((s) => s.dataSub);
  const sideAll = useUi((s) => s.sideAll);
  useEffect(() => { setLang(lang); document.documentElement.lang = lang; }, [lang]);
  useTheme();
  useWorkspace();
  usePendingOpen();
  useAppSettingsSync();
  useAutosave();
  const ws = useWs();
  const settingsOpen = useSettingsUi((s) => s.open);
  // Start: bez dat v pohledech, které jinak nemají co ukázat (Data › Zdroje a smyčky, Model, Ladění, APC);
  // Data › Trendy / Kvalita / Diagnostika a Živá simulace si prázdný stav řeší samy.
  const cur = TABS.find((t) => t.id === tab) ?? TABS[0];
  const showStart = !!ws.data && !ws.data.has_data && (cur.id === "model" || cur.id === "tuning" || cur.id === "apc" || (cur.id === "data" && sub === "sources"));
  // Data má podzáložky; Diagnostika zůstává ve starých pohledech (E5 je přepracuje).
  const dataView = sub === "sources" ? [<SourcesMain />, <SourcesSide />] : sub === "trends" ? [<TrendsMain />, <TrendsSide />]
    : sub === "diag-all" ? [<TriageMain />, <TriageSide />] : sub === "diag-detail" ? [<DiagMain />, <DiagSide />]
    : [<DataMain />, <DataSide />];
  return (
    <div className="shell">
      <Header />
      {settingsOpen ? <SettingsPage /> : showStart ? <StartScreen /> : <>
      {CONTEXT_TABS.includes(cur.id) && <ContextRow />}
      <div className={cur.id === "live" ? "body body-wide" : "body"}>
        <main className="main" data-testid={`tab-${cur.id}`} data-dsub={cur.id === "data" ? sub : undefined}>
          {cur.id === "data" ? dataView[0] : cur.id === "model" ? <ModelMain /> : cur.id === "tuning" ? <TuningMain />
            : cur.id === "live" ? <LiveMain /> : cur.id === "apc" ? <ApcMain />
            : <ProjectMain />}
        </main>
        {cur.id !== "live" && <aside className="side" aria-label={T("ui_settings")}>
          <div className="side-all">
            <button type="button" className="link" onClick={() => sideAll(true)} data-testid="side-expand">{T("side_expand_all")}</button>
            <button type="button" className="link" onClick={() => sideAll(false)} data-testid="side-collapse">{T("side_collapse_all")}</button>
          </div>
          {cur.id === "data" ? dataView[1] : cur.id === "model" ? <ModelSide /> : cur.id === "tuning" ? <TuningSide />
            : cur.id === "apc" ? <ApcSide />
            : <ProjectSide />}
        </aside>}
      </div>
      </>}
      <StatusBar />
    </div>
  );
}
