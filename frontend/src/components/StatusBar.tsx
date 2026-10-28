import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useT } from "../i18n";
import { useUi } from "../store";

export function StatusBar() {
  const T = useT();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000, retry: false });
  const jobs = Object.values(useUi((s) => s.jobs)).filter((j) => j.state === "queued" || j.state === "running");
  return (
    <footer className="status">
      {health.isSuccess ? (
        <span className="ok" data-testid="api-ok">{T("ui_connected", { v: health.data.version })}</span>
      ) : health.isError ? (
        <span className="err">{T("ui_offline")}</span>
      ) : null}
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
