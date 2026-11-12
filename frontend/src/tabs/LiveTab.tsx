// Záložka Živá simulace (M18): sdílené moduly dnešního webu (live_engine.js = jádro simulace, live_ui.js = rozhraní
// a graf) ve stránce Reactu. Konfigurace z GET /live (texty v jazyce rozhraní); „zapsat do sady 2“ (trigger apply)
// jde přes PUT /tuning/sets/2. Panel nastavení nemá: live_ui.js si kreslí vlastní postranní sloupec.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { request } from "../api/client";
import mountLive from "../../../pidtools/ui/static/live_ui.js";
import PIDLive from "../../../pidtools/ui/static/live_engine.js";
import CtrlEngine from "../../../pidtools/ui/static/ctrl_engine.js";
import "../../../pidtools/ui/static/live.css";
import "../styles/live.css";
import { useWs } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";

// jádro je prostý skript (UMD): při sestavení se z něj stane modul, live_ui.js ho čte z window.PIDLive
(window as unknown as { PIDLive?: unknown; CtrlEngine?: unknown }).PIDLive ??= PIDLive;
// regulátor živé simulace běží na obecném interpretu profilu (E9-B), stejném jako v Pythonu
(window as unknown as { CtrlEngine?: unknown }).CtrlEngine ??= CtrlEngine;

/** Souhrn běhu zapsaný do projektu (nastavení `live_runs`), než bude deník ladění (E10). */
export const LIVE_RUNS_KEEP = 20;

export function LiveMain() {
  const T = useT();
  const box = useRef<HTMLDivElement>(null);
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const theme = useUi((s) => s.theme);
  const qc = useQueryClient();
  const ws = useWs().data;
  const cfg = useQuery({
    queryKey: ["ws", wid, "live", lang, ws?.pv, ws?.mv, ws?.n, ws?.rng],
    enabled: !!wid && !!ws?.has_data, retry: false,
    queryFn: () => request<Record<string, unknown>>("GET", `/workspaces/${wid}/live`),
  });
  // stejný obsah = žádné odpojení komponenty (po zápisu sady se dotaz načte znovu)
  const json = useMemo(() => (cfg.data ? JSON.stringify(cfg.data) : null), [cfg.data]);

  useEffect(() => {
    const host = box.current;
    if (!host || !json) return;
    // texty nového vzhledu (karty, poruchy, ukazatele) z i18n; ostatní přicházejí v konfiguraci z API
    const data = JSON.parse(json) as { labels: Record<string, string> };
    for (const [k, v] of [["now", "now"], ["kpi_change", "change"], ["same", "same"], ["sec_dist", "sec_dist"],
      ["dist_shape", "shape"], ["dist_where", "where"], ["dist_size", "size"], ["dist_period", "period"],
      ["period_hint", "period_hint"], ["noise_pv", "noise_pv"], ["mv_man", "mv_man"], ["run_dist", "run_dist"],
      ["mode_hint", "mode_hint"], ["sets_note", "sets_note"], ["dist_note", "dist_note"], ["h_mode", "h_mode"],
      ["h_sets", "h_sets"], ["h_dist", "h_dist"], ["h_kpi", "h_kpi"], ["set1", "set1"], ["set2", "set2"],
      ["reset", "reset"]] as const) data.labels[k] = T(`ui_live_${v}`);
    const cleanup = mountLive({
      data, parentElement: host,
      setTriggerValue: (name, value) => {
        if (name === "journal") {
          // E10 (deník ladění) převezme: zatím souhrn do nastavení projektu, zobrazí se v záložce Projekt
          const old = qc.getQueryData<Record<string, unknown>>(["ws", wid, "settings"])?.live_runs;
          const runs = [...(Array.isArray(old) ? old : []), { when: new Date().toISOString(), ...(value as object) }].slice(-LIVE_RUNS_KEEP);
          void request("PATCH", `/workspaces/${wid}/settings`, { live_runs: runs })
            .then(() => qc.invalidateQueries({ queryKey: ["ws", wid, "settings"] }));
          return;
        }
        if (name !== "apply") return;
        const v = value as { Gain: number; TI: number | null; TD: number | null };
        void request("PUT", `/workspaces/${wid}/tuning/sets/2`,
          { Kc: v.Gain, Ti: v.TI ?? 0, Td: v.TD ?? 0, log: { method: "live" } })
          .then(() => qc.invalidateQueries({ queryKey: ["ws", wid] }));
      },
    });
    // „Rozbalit vše / Sbalit vše“ nad kartami panelu (modul si je nekreslí; jen přepíná jeho <details>)
    const side = host.querySelector(".lvs");
    if (side) {
      const bar = document.createElement("div");
      bar.className = "lvs-all";
      for (const [open, key, tid] of [[true, "side_expand_all", "live-expand"], [false, "side_collapse_all", "live-collapse"]] as const) {
        const b = document.createElement("button");
        b.type = "button"; b.className = "link"; b.textContent = T(key); b.dataset.testid = tid;
        b.onclick = () => side.querySelectorAll("details").forEach((d) => { d.open = open; });
        bar.append(b);
      }
      side.prepend(bar);
    }
    return () => { if (typeof cleanup === "function") cleanup(); host.replaceChildren(); };
  }, [json, wid, qc, theme, T]);

  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (cfg.isError) return <div className="card muted">{T("need_model")}</div>;
  return <div ref={box} className="live-host" data-testid="live-sim" />;
}
