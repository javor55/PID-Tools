import { useEffect } from "react";
import { setLang } from "./api/client";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Toasts } from "./components/Toasts";
import { Header } from "./components/Header";
import { StatusBar } from "./components/StatusBar";
import { useT } from "./i18n";
import { ContextRow } from "./components/ContextRow";
import { DataMain, DataSide } from "./tabs/DataTab";
import { usePendingOpen } from "./tabs/project/pendingOpen";
import {
  ApcMain, ApcSide, DiagMain, DiagSide, Lazy, LiveMain, ModelMain, ModelSide, ProjectMain, ProjectSide, SettingsPage,
  TriageMain, TriageSide, TrendsMain, TrendsSide, TuningMain, TuningSide,
} from "./lazy";
import { SourcesMain, SourcesSide } from "./tabs/data/SourcesView";
import { useSettingsUi } from "./settings/settingsStore";
import { useAppSettingsSync } from "./settings/appSettings";
import { StartScreen } from "./start/StartScreen";
import { useAutosave } from "./start/project";
import { useWorkspace } from "./workspace";
import { useShortcuts } from "./shortcuts";
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
  useShortcuts();
  const ws = useWs();
  const settingsOpen = useSettingsUi((s) => s.open);
  // Start: bez dat v pohledech, které jinak nemají co ukázat (Data › Zdroje a smyčky, Model, Ladění, APC);
  // Data › Trendy / Kvalita / Diagnostika a Živá simulace si prázdný stav řeší samy.
  const cur = TABS.find((t) => t.id === tab) ?? TABS[0];
  const showStart = !!ws.data && !ws.data.has_data && (cur.id === "model" || cur.id === "tuning" || cur.id === "apc" || (cur.id === "data" && sub === "sources"));
  // Data má podzáložky; Diagnostika zůstává ve starých pohledech (E5 je přepracuje).
  const dataView = sub === "sources" ? [<SourcesMain />, <SourcesSide />] : sub === "trends" ? [<Lazy><TrendsMain /></Lazy>, <Lazy><TrendsSide /></Lazy>]
    : sub === "diag-all" ? [<Lazy><TriageMain /></Lazy>, <Lazy><TriageSide /></Lazy>] : sub === "diag-detail" ? [<Lazy><DiagMain /></Lazy>, <Lazy><DiagSide /></Lazy>]
    : [<DataMain />, <DataSide />];
  return (
    <div className="shell">
      <Header />
      {settingsOpen ? <ErrorBoundary resetKey="settings"><Lazy><SettingsPage /></Lazy></ErrorBoundary> : showStart ? <StartScreen compact={cur.id === "data"} /> : <>
      {CONTEXT_TABS.includes(cur.id) && <ContextRow />}
      <div className={cur.id === "live" ? "body body-wide" : "body"}>
        <ErrorBoundary resetKey={tab + sub}>
        <main className="main" data-testid={`tab-${cur.id}`} data-dsub={cur.id === "data" ? sub : undefined}>
          {cur.id === "data" ? dataView[0] : cur.id === "model" ? <Lazy><ModelMain /></Lazy> : cur.id === "tuning" ? <Lazy><TuningMain /></Lazy>
            : cur.id === "live" ? <Lazy><LiveMain /></Lazy> : cur.id === "apc" ? <Lazy><ApcMain /></Lazy>
            : <Lazy><ProjectMain /></Lazy>}
        </main>
        </ErrorBoundary>
        {cur.id !== "live" && <aside className="side" aria-label={T("ui_settings")}>
          <ErrorBoundary resetKey={tab + sub}>
          <div className="side-all">
            <button type="button" className="link" onClick={() => sideAll(true)} data-testid="side-expand">{T("side_expand_all")}</button>
            <button type="button" className="link" onClick={() => sideAll(false)} data-testid="side-collapse">{T("side_collapse_all")}</button>
          </div>
          {cur.id === "data" ? dataView[1] : cur.id === "model" ? <Lazy><ModelSide /></Lazy> : cur.id === "tuning" ? <Lazy><TuningSide /></Lazy>
            : cur.id === "apc" ? <Lazy><ApcSide /></Lazy>
            : <Lazy><ProjectSide /></Lazy>}
          </ErrorBoundary>
        </aside>}
      </div>
      </>}
      <StatusBar />
      <Toasts />
    </div>
  );
}
