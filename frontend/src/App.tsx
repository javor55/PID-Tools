import { useEffect } from "react";
import { api, ApiError, setLang } from "./api/client";
import { Header } from "./components/Header";
import { StatusBar } from "./components/StatusBar";
import { useT } from "./i18n";
import { ApcMain, ApcSide } from "./tabs/ApcTab";
import { DataMain, DataSide } from "./tabs/DataTab";
import { DiagMain, DiagSide } from "./tabs/DiagTab";
import { LiveMain } from "./tabs/LiveTab";
import { LoopsMain, LoopsSide } from "./tabs/LoopsTab";
import { ProjectMain, ProjectSide, usePendingOpen } from "./tabs/ProjectTab";
import { ModelMain, ModelSide } from "./tabs/ModelTab";
import { TuningMain, TuningSide } from "./tabs/TuningTab";
import { TABS, useUi } from "./store";

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
  useEffect(() => { setLang(lang); document.documentElement.lang = lang; }, [lang]);
  useTheme();
  useWorkspace();
  usePendingOpen();
  const cur = TABS.find((t) => t.id === tab) ?? TABS[0];
  return (
    <div className="shell">
      <Header />
      <div className={cur.id === "live" ? "body body-wide" : "body"}>
        <main className="main" data-testid={`tab-${cur.id}`}>
          {cur.id === "data" ? <DataMain /> : cur.id === "model" ? <ModelMain /> : cur.id === "tuning" ? <TuningMain />
            : cur.id === "live" ? <LiveMain /> : cur.id === "apc" ? <ApcMain />
            : cur.id === "diag" ? <DiagMain /> : cur.id === "loops" ? <LoopsMain />
            : <ProjectMain />}
        </main>
        {cur.id !== "live" && <aside className="side">
          <h2>{T("ui_settings")}</h2>
          {cur.id === "data" ? <DataSide /> : cur.id === "model" ? <ModelSide /> : cur.id === "tuning" ? <TuningSide />
            : cur.id === "apc" ? <ApcSide /> : cur.id === "diag" ? <DiagSide /> : cur.id === "loops" ? <LoopsSide />
            : <ProjectSide />}
        </aside>}
      </div>
      <StatusBar />
    </div>
  );
}
