// Graf průběhů s úseky – sdílený modul dnešního webu (pidtools/ui/static/trend.js) ve stránce Reactu.
import { useEffect, useRef } from "react";
import mountTrend from "../../../pidtools/ui/static/trend.js";
import "../../../pidtools/ui/static/trend.css";

function hash(s: string): string {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(36) + ":" + s.length;
}

export interface TrendHandlers {
  onWins?: (w: { mode: string; wins: Record<string, [number, number][]>; common: [number, number] }) => void;
  onMode?: (mode: string) => void;
}

export function Trend({ data, onWins, onMode, testid }: TrendHandlers & { data: Record<string, unknown>; testid?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const h = useRef<TrendHandlers>({});
  useEffect(() => { h.current = { onWins, onMode }; }, [onWins, onMode]);
  useEffect(() => {
    if (!box.current) return;
    const sig = hash(JSON.stringify(data));          // stejný otisk = trend.js nic nepřekresluje
    mountTrend({
      data: { ...data, sig }, parentElement: box.current,
      setStateValue: (k, v) => { if (k === "wins") h.current.onWins?.(v as never); },
      setTriggerValue: (k, v) => { if (k === "mode") h.current.onMode?.(String(v)); },
    });
  }, [data]);
  return <div ref={box} className="trend-host" data-testid={testid} />;
}
