// Graf průběhů s úseky – sdílený modul dnešního webu (frontend/src/legacy/trend.js) ve stránce Reactu.
import { useEffect, useRef } from "react";
import mountTrend from "../legacy/trend.js";
import "../legacy/trend.css";

function hash(s: string): string {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(36) + ":" + s.length;
}

export interface TrendHandlers {
  onWins?: (w: { mode: string; wins: Record<string, [number, number][]>; common: [number, number];
    ab?: { a: [number, number]; b: [number, number] | null } }) => void;
  onMode?: (mode: string) => void;
}

export function Trend({ data, onWins, onMode, testid }: TrendHandlers & { data: Record<string, unknown>; testid?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const h = useRef<TrendHandlers>({});
  const destroy = useRef<(() => void) | null>(null);   // odpojení trend.js; volá se jen při odchodu komponenty
  useEffect(() => { h.current = { onWins, onMode }; }, [onWins, onMode]);
  useEffect(() => {
    if (!box.current) return;
    const sig = hash(JSON.stringify(data));          // stejný otisk = trend.js nic nepřekresluje
    destroy.current = mountTrend({
      data: { ...data, sig }, parentElement: box.current,
      setStateValue: (k, v) => { if (k === "wins") h.current.onWins?.(v as never); },
      setTriggerValue: (k, v) => { if (k === "mode") h.current.onMode?.(String(v)); },
    });
  }, [data]);
  // ne v úklidu efektu výše (ten běží při každé změně dat): odpojit až s komponentou
  useEffect(() => () => { destroy.current?.(); destroy.current = null; }, []);
  return <div ref={box} className="trend-host" data-testid={testid} />;
}
