// Prohlížeč záznamu – sdílený modul dnešního webu (frontend/src/legacy/viewer.js) ve stránce Reactu.
// Data: binární balík z /signals (vloží se do mezipaměti, kterou viewer.js čte), role a barvy signálů smyčky,
// texty vw_* z /i18n. Rozložení (panely, kurzory, měřítka) se ukládá do nastavení „dview“ (projekt).
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { binary, request } from "../api/client";
import { unframe } from "../api/signals";
import mountViewer, { type ViewerData } from "../legacy/viewer.js";
import PIDViewAn from "../legacy/viewer_an.js";
import "../legacy/viewer.css";
import { useSettings, useWs } from "../data";
import { decOf } from "../i18n";
import { usePalette } from "../lib/palette";
import { useUi } from "../store";

// analýza je prostý skript (UMD): při sestavení se z něj stane modul, viewer.js ho čte z window.PIDViewAn
(window as unknown as { PIDViewAn?: unknown }).PIDViewAn ??= PIDViewAn;

declare global { interface Window { __pidViewData?: Record<string, { buf: ArrayBuffer; sigs: Record<string, unknown> }> } }

/** simple = jednoduchý graf smyčky (Kvalita dat): pevné panely SP + PV / MV / DV, bez seznamu signálů, rozložení se neukládá. */
export function RecordViewer({ texts, simple }: { texts: Record<string, string>; simple?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const destroy = useRef<(() => void) | null>(null);   // odpojení viewer.js; volá se jen při odchodu komponenty
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const dark = useUi((s) => s.theme) === "dark" || document.documentElement.dataset.theme === "dark";
  const pal = usePalette();                             // barvy z proměnných CSS; mění se s data-theme
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
    if (ws.pv) roles[ws.pv] = ["PV", pal.pv, String(st.u_pv ?? "")];
    if (ws.sp) roles[ws.sp] = ["SP", pal.sp, String(st.u_pv ?? "")];
    if (ws.mv) roles[ws.mv] = ["MV", pal.mv, String(st.u_mv ?? "")];
    (ws.dists ?? []).forEach((d, j) => { roles[d] ??= ["DV", pal.dist[j % pal.dist.length], ""]; });
    if (ws.pos) roles[ws.pos] ??= ["POS", pal.pos, "%"];
    let k = 0;
    const sigs = meta.sigs.map((s) => {
      const [role, color, unit] = roles[s.name] ?? ["", pal.series[k++ % pal.series.length], ""];
      return { ...s, role, color, unit, axis: role === "PV" || role === "SP" ? "pv" : role === "MV" || role === "POS" ? "mv" : null };
    });
    window.__pidViewData = { [meta.hash]: { buf: blob, sigs: {} } };
    const clock = ws.origin ? Date.parse(ws.origin.replace(" ", "T") + "Z") + meta.tmin * 1000 : null;
    const txt = Object.fromEntries(Object.entries(texts).filter(([kk]) => kk.startsWith("vw_")).map(([kk, v]) => [kk.slice(3), v]));
    const fixed = simple ? JSON.stringify({ list: false, panels: [
      { sigs: [ws.pv, ws.sp].filter(Boolean), h: 210 }, { sigs: [ws.mv, ws.pos].filter(Boolean), h: 140 },
      ...((ws.dists ?? []).length ? [{ sigs: ws.dists ?? [], h: 120 }] : [])] }) : null;
    const lay = simple ? fixed : typeof st.dview === "string" ? st.dview : null;
    const data: Omit<ViewerData, "sig"> = {
      key: simple ? "quality_view" : "data_view", view_key: `${simple ? "q|" : ""}${ws.fname}|${meta.hash}|${ws.pv}`, sigs, times: meta.times, T: meta.T, decim: meta.decim,
      hash: meta.hash, clock: Number.isFinite(clock) ? clock : null, tunit: "auto", dec: decOf(lang),
      dark, txt, fname: ws.fname, layout: lay, b64: null, url: null,
    };
    const sig = `${meta.hash}|${lang}|${dark}|${JSON.stringify(sigs.map((s) => [s.name, s.role, s.color, s.unit]))}`;
    destroy.current = mountViewer({
      data: { ...data, sig }, parentElement: box.current,
      setStateValue: (key, value) => {
        // viewer.js posílá rozložení až po 1,5 s klidu
        if (!simple && key === "layout" && typeof value === "string" && value.length <= 65536) {
          void request("PATCH", `/workspaces/${wid}/settings`, { dview: value });
        }
      },
    });
  }, [pack.data, ws, settings.data, texts, lang, dark, pal, wid, simple]);

  // ne v úklidu efektu výše (ten běží při každé změně dat a modul by ztratil zoom): odpojit až s komponentou
  useEffect(() => () => { destroy.current?.(); destroy.current = null; }, []);

  return <div ref={box} className="viewer-host" data-testid="record-viewer" />;
}
