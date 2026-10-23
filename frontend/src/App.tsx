import { useEffect } from "react";
import { api, setLang } from "./api/client";
import { Header } from "./components/Header";
import { Placeholder } from "./components/Placeholder";
import { StatusBar } from "./components/StatusBar";
import { useT } from "./i18n";
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
    if (wid) return;
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
  const cur = TABS.find((t) => t.id === tab) ?? TABS[0];
  return (
    <div className="shell">
      <Header />
      <div className="body">
        <main className="main" data-testid={`tab-${cur.id}`}>
          <Placeholder milestone={cur.milestone} />
        </main>
        <aside className="side">
          <h2>{T("ui_settings")}</h2>
          <div className="muted">{T(cur.label)}</div>
        </aside>
      </div>
      <StatusBar />
    </div>
  );
}
