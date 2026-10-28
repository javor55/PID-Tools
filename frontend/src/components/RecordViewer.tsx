// Prohlížeč záznamu – sdílený modul dnešního webu (pidtools/ui/static/viewer.js) ve stránce Reactu.
// Data: binární balík z /signals (vloží se do mezipaměti, kterou viewer.js čte), role a barvy signálů smyčky,
// texty vw_* z /i18n. Rozložení (panely, kurzory, měřítka) se ukládá do nastavení „dview“ (projekt).
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { binary, request } from "../api/client";
import { unframe } from "../api/signals";
import mountViewer from "../../../pidtools/ui/static/viewer.js";
import PIDViewAn from "../../../pidtools/ui/static/viewer_an.js";
import "../../../pidtools/ui/static/viewer.css";
import { useSettings, useWs } from "../data";
import { useUi } from "../store";

const OTHER = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea",
  "#ea580c", "#0f766e", "#b91c1c", "#4f46e5", "#a16207"];
const DIST = ["#0d9488", "#8b5cf6", "#ca8a04", "#64748b"];

// analýza je prostý skript (UMD): při sestavení se z něj stane modul, viewer.js ho čte z window.PIDViewAn
(window as unknown as { PIDViewAn?: unknown }).PIDViewAn ??= PIDViewAn;

declare global { interface Window { __pidViewData?: Record<string, { buf: ArrayBuffer; sigs: Record<string, unknown> }> } }

export function RecordViewer({ texts }: { texts: Record<string, string> }) {
  const box = useRef<HTMLDivElement>(null);
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const dark = useUi((s) => s.theme) === "dark" || document.documentElement.dataset.theme === "dark";
  const ws = useWs().data;
  const settings = useSettings();
  const pack = useQuery({
    queryKey: ["ws", wid, "rawsignals", ws?.fname, ws?.n, ws?.layout],
    enabled: !!wid && !!ws?.has_data,
    staleTime: Infinity,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/signals`)),
  });

  useEffect(() => {
    if (!box.current || !pack.data || !ws) return;
    const { meta, blob } = pack.data;
    const roles: Record<string, [string, string, string]> = {};
    const st = settings.data ?? {};
    if (ws.pv) roles[ws.pv] = ["PV", "#1f5fa8", String(st.u_pv ?? "")];
    if (ws.sp) roles[ws.sp] = ["SP", "#9aa5b1", String(st.u_pv ?? "")];
    if (ws.mv) roles[ws.mv] = ["MV", "#c2410c", String(st.u_mv ?? "")];
    (ws.dists ?? []).forEach((d, j) => { roles[d] ??= ["DV", DIST[j % DIST.length], ""]; });
    if (ws.pos) roles[ws.pos] ??= ["POS", "#7c3aed", "%"];
    let k = 0;
    const sigs = meta.sigs.map((s) => {
      const [role, color, unit] = roles[s.name] ?? ["", OTHER[k++ % OTHER.length], ""];
      return { ...s, role, color, unit };
    });
    window.__pidViewData = { [meta.hash]: { buf: blob, sigs: {} } };
    const clock = ws.origin ? Date.parse(ws.origin.replace(" ", "T") + "Z") + meta.tmin * 1000 : null;
    const txt = Object.fromEntries(Object.entries(texts).filter(([kk]) => kk.startsWith("vw_")).map(([kk, v]) => [kk.slice(3), v]));
    const lay = typeof st.dview === "string" ? st.dview : null;
    const data = {
      key: "data_view", view_key: `${ws.fname}|${meta.hash}`, sigs, times: meta.times, T: meta.T, decim: meta.decim,
      hash: meta.hash, clock: Number.isFinite(clock) ? clock : null, tunit: "auto", dec: lang === "cs" ? "," : ".",
      dark, txt, fname: ws.fname, layout: lay, b64: null as string | null, url: null as string | null,
    };
    const sig = `${meta.hash}|${lang}|${dark}|${JSON.stringify(sigs.map((s) => [s.name, s.role, s.color, s.unit]))}`;
    mountViewer({
      data: { ...data, sig }, parentElement: box.current,
      setStateValue: (key, value) => {
        // viewer.js posílá rozložení až po 1,5 s klidu
        if (key === "layout" && typeof value === "string" && value.length <= 65536) {
          void request("PATCH", `/workspaces/${wid}/settings`, { dview: value });
        }
      },
    });
  }, [pack.data, ws, settings.data, texts, lang, dark, wid]);

  return <div ref={box} className="viewer-host" data-testid="record-viewer" />;
}
