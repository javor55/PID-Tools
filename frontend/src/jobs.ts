// Úlohy (identifikace, dofitování, nejistota …): spuštění, sledování průběhu (SSE) ve stavovém řádku, po dokončení
// znovu načíst dotazy prostoru.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { type JobInfo, request, watchJob } from "./api/client";
import { useUi } from "./store";

export function useJobRunner() {
  const qc = useQueryClient();
  const { wid, putJob, dropJob } = useUi();
  return useCallback(async (path: string, body?: unknown, label?: string): Promise<JobInfo> => {
    const j = await request<JobInfo>("POST", `/workspaces/${wid}${path}`, body);
    const show = (x: JobInfo) => putJob({ ...x, text: x.text || label || "" });
    show(j);
    return new Promise((resolve) => {
      const finish = (x: JobInfo) => {
        dropJob(x.id);
        void qc.invalidateQueries({ queryKey: ["ws", wid] });
        resolve(x);
      };
      if (j.state === "done" || j.state === "error" || j.state === "cancelled" || j.state === "timeout") return finish(j);
      const stop = watchJob(j.id, (x) => {
        show(x);
        if (x.state !== "queued" && x.state !== "running") { stop(); finish(x); }
      });
    });
  }, [wid, putJob, dropJob, qc]);
}
