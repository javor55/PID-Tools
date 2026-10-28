// Záložka Živá simulace (M18): sdílené moduly dnešního webu (live_engine.js = jádro simulace, live_ui.js = rozhraní
// a graf) ve stránce Reactu. Konfigurace z GET /live (texty v jazyce rozhraní); „zapsat do sady 2“ (trigger apply)
// jde přes PUT /tuning/sets/2. Panel nastavení nemá: live_ui.js si kreslí vlastní postranní sloupec.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { request } from "../api/client";
import mountLive from "../../../pidtools/ui/static/live_ui.js";
import PIDLive from "../../../pidtools/ui/static/live_engine.js";
import "../../../pidtools/ui/static/live.css";
import { useWs } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";

// jádro je prostý skript (UMD): při sestavení se z něj stane modul, live_ui.js ho čte z window.PIDLive
(window as unknown as { PIDLive?: unknown }).PIDLive ??= PIDLive;

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
    const cleanup = mountLive({
      data: JSON.parse(json), parentElement: host,
      setTriggerValue: (name, value) => {
        if (name !== "apply") return;
        const v = value as { Gain: number; TI: number | null; TD: number | null };
        void request("PUT", `/workspaces/${wid}/tuning/sets/2`,
          { Kc: v.Gain, Ti: v.TI ?? 0, Td: v.TD ?? 0, log: { method: "live" } })
          .then(() => qc.invalidateQueries({ queryKey: ["ws", wid] }));
      },
    });
    return () => { if (typeof cleanup === "function") cleanup(); host.replaceChildren(); };
  }, [json, wid, qc, theme]);

  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (cfg.isError) return <div className="card muted">{T("need_model")}</div>;
  return <div ref={box} className="live-host" data-testid="live-sim" />;
}
