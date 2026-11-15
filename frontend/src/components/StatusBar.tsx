import { useIsFetching, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useEffect, useState } from "react";
import { useT } from "../i18n";
import { useUi } from "../store";

// Text přepočtu až po 300 ms trvání (komponenta se při konci přepočtu odpojí, tím se stav vynuluje)
function Recalc() {
  const T = useT();
  const [on, setOn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setOn(true), 300); return () => clearTimeout(t); }, []);
  return on ? <span className="recalc" role="status" data-testid="recalc">{T("qs_recalc")}</span> : null;
}

export function StatusBar() {
  const T = useT();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000, retry: false });
  const jobs = Object.values(useUi((s) => s.jobs)).filter((j) => j.state === "queued" || j.state === "running");
  // pravidelně obnovovaný dotaz save-state (5 s) není přepočet – vyloučit
  const running = useIsFetching({ queryKey: ["ws"], predicate: (q) => q.queryKey[2] !== "save-state" });
  return (
    <footer className="status">
      {health.isSuccess ? (
        <span className="ok" data-testid="api-ok">{T("ui_connected", { v: health.data.version })}</span>
      ) : health.isError ? (
        <span className="err">{T("ui_offline")}</span>
      ) : null}
      {running > 0 && <Recalc />}
      <div className="jobs" aria-label={T("ui_jobs")}>
        {jobs.map((j) => (
          <span className="job" key={j.id}>
            <span>{j.text || j.id}</span>
            <progress max={1} value={j.progress} />
            <button title={T("ui_cancel")} onClick={() => api.cancelJob(j.id)}>✕</button>
          </span>
        ))}
      </div>
    </footer>
  );
}
