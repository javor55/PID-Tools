// Společné prvky technik APC: dotaz na API (klíč pod prostorem → obnoví se jako ostatní), číselné pole s potvrzením,
// text s **tučným** a výběr křivek z binárního balíku.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { type ComponentType, Fragment, useState } from "react";
import { request } from "../../api/client";
import { type PackMeta, series } from "../../api/signals";
import type { Series } from "../../components/LineChart";
import { useWs } from "../../data";
import { useUi } from "../../store";

/** Technika APC: registrace v `tabs/apc/index.ts` (nová technika = nový soubor + řádek v seznamu). */
export interface Technique {
  id: string;                      // druh z /apc/recommend (kind)
  label: string;                   // klíč textu názvu
  intro?: string;                  // klíč úvodního textu („O této struktuře“)
  Main?: ComponentType;            // chybí = zatím bez API → zástupný text
  Side?: ComponentType;            // nastavení v postranním panelu
}

/** GET technik APC – klíč ["ws", wid, "apc", část] (zneplatní ho každá změna prostoru), bez blikání při přepočtu. */
export function useApc<T>(part: string, path: string) {
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  return useQuery({
    queryKey: ["ws", wid, "apc", part], enabled: !!wid && !!ws?.has_data, placeholderData: keepPreviousData, retry: false,
    queryFn: () => request<T>("GET", `/workspaces/${wid}${path}`),
  });
}

/** Číselné pole: hodnota se potvrdí opuštěním pole nebo Enterem; do té doby se drží rozepsaný text. */
export function NumInput({ value, onCommit, testid, min, disabled }: { value: number; onCommit: (x: number) => void;
  testid?: string; min?: number; disabled?: boolean }) {
  const [v, setV] = useState<string | null>(null);
  return (
    <input type="number" step="any" min={min} disabled={disabled} data-testid={testid}
      value={v ?? +value.toPrecision(6)} onChange={(e) => setV(e.target.value)}
      onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v) && +v !== value) onCommit(+v); setV(null); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

/** Text z překladů s **tučným** (stejné označení jako v desktopu a ve Streamlitu). */
export function Bold({ text }: { text: string }) {
  return <>{text.split("**").map((p, i) => <Fragment key={i}>{i % 2 ? <b>{p}</b> : p}</Fragment>)}</>;
}

export interface Curves { meta: PackMeta; blob: ArrayBuffer }
export interface CurveDef { name: string; key: string; color: string; dash?: string }

/** Křivky z binárního balíku podle seznamu (chybějící signál se vynechá). */
export function curveSeries(c: Curves | undefined, defs: CurveDef[]): Series[] {
  if (!c) return [];
  return defs.flatMap((d) => {
    const x = series(c.meta, c.blob, d.key);
    return x ? [{ name: d.name, x: x.t, y: x.v, color: d.color, dash: d.dash }] : [];
  });
}

/** Číslo pro tabulky: 4 platné číslice, nekonečno a chybějící hodnota čitelně. */
export function num(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return Number.isFinite(x) ? String(+x.toPrecision(4)) : "∞";
}
