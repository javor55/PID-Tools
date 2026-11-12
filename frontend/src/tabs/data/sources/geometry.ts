// Čisté pomocné funkce obrazovky Zdroje a smyčky: geometrie časových pruhů, stav mapování smyčky, odkazy na sloupce,
// minigrafy. Bez Reactu, aby šly testovat samostatně (frontend/tests/sources.test.ts).
import type { components } from "../../../api/schema";

export type SourceInfo = components["schemas"]["SourceInfo"];
export type LoopMapping = components["schemas"]["LoopMapping"];
export type RolesBody = components["schemas"]["RolesBody"];
export type Ref = components["schemas"]["Ref"];

/** Typ přetahovaných dat (sloupec z panelu → buňka role smyčky). */
export const COL_MIME = "application/x-pid-column";

export const ROLES = ["pv", "sp", "mv", "pos", "mode"] as const;
export type Role = (typeof ROLES)[number] | "dv";
export type GridMode = "overlap" | "union";

// ---- odkazy na sloupce
const SEP = "\u001f";
export const refKey = (r: Ref) => `${r.source}${SEP}${r.column}`;
export const parseKey = (k: string): Ref | null => {
  const i = k.indexOf(SEP);
  return i < 0 ? null : { source: k.slice(0, i), column: k.slice(i + 1) };
};
export const sameRef = (a: Ref | null | undefined, b: Ref | null | undefined) =>
  !!a && !!b && a.source === b.source && a.column === b.column;

export const stripExt = (n: string) => n.replace(/\.[A-Za-z0-9]{1,5}$/, "");

/** „soubor › sloupec“ (název souboru bez přípony jako v návrhu); neznámý zdroj ukáže jeho id. */
export function refLabel(r: Ref | null | undefined, sources: readonly { id: string; name: string }[]): string {
  if (!r) return "";
  const s = sources.find((x) => x.id === r.source);
  return `${stripExt(s?.name ?? r.source)} › ${r.column}`;
}

// ---- stav mapování
export type StatusKind = "complete" | "no_sp" | "only_pv" | "no_pv" | "no_mv" | "no_data";
export interface MapStatus { kind: StatusKind; level: "ok" | "warn" | "err" }

/** Úplná smyčka má PV i MV (SP je doporučený, bez něj upozornění); bez PV / MV je neúplná; bez dat upozornění. */
export function mappingStatus(m: Pick<LoopMapping, "roles" | "has_data">): MapStatus {
  const r = m.roles;
  if (!r.pv) return { kind: "no_pv", level: "err" };
  if (!r.mv) return { kind: r.sp ? "no_mv" : "only_pv", level: "err" };
  if (m.has_data === false) return { kind: "no_data", level: "warn" };
  if (!r.sp) return { kind: "no_sp", level: "warn" };
  return { kind: "complete", level: "ok" };
}

/** Mapování bez polí jen z odpovědi (index, sources, has_data) – tělo pro PUT. */
export function mappingBody(m: LoopMapping): Omit<LoopMapping, "has_data" | "sources" | "index"> {
  return { tag: m.tag, description: m.description, roles: m.roles, norm_pv: m.norm_pv ?? null, norm_mv: m.norm_mv ?? null,
    cascade_to: m.cascade_to ?? null };
}

/** Role nastavená na sloupec (nebo vyprázdněná); u DV se sloupec přidá (bez duplicit). */
export function withRole(m: LoopMapping, role: Role, ref: Ref | null): LoopMapping {
  if (role === "dv") {
    const dv = m.roles.dv ?? [];
    if (!ref || dv.some((d) => sameRef(d, ref))) return m;
    return { ...m, roles: { ...m.roles, dv: [...dv, ref] } };
  }
  return { ...m, roles: { ...m.roles, [role]: ref } };
}

export function withoutDv(m: LoopMapping, i: number): LoopMapping {
  return { ...m, roles: { ...m.roles, dv: (m.roles.dv ?? []).filter((_, j) => j !== i) } };
}

/** Kde se sloupec používá: klíč sloupce → [{ loop (od 0), role }] (podle mapování všech smyček). */
export function usageOf(maps: readonly LoopMapping[]): Map<string, { loop: number; role: string }[]> {
  const out = new Map<string, { loop: number; role: string }[]>();
  const add = (r: Ref | null | undefined, loop: number, role: string) => {
    if (!r) return;
    const k = refKey(r);
    out.set(k, [...(out.get(k) ?? []), { loop, role }]);
  };
  maps.forEach((m, i) => {
    for (const role of ROLES) add(m.roles[role], i, role);
    (m.roles.dv ?? []).forEach((d) => add(d, i, "dv"));
  });
  return out;
}

/** Název smyčky v seznamu: tag, jinak „Smyčka N“. */
export const loopName = (m: Pick<LoopMapping, "tag">, i: number, fallback: string) => m.tag?.trim() || `${fallback} ${i + 1}`;

// ---- časová osa
export interface Bar { left: number; width: number }          // v procentech šířky osy
export interface Timeline { lo: number; hi: number; bars: (Bar | null)[]; common: Bar | null }

const bar = (a: number, b: number, lo: number, hi: number): Bar => {
  const w = hi - lo;
  return { left: ((a - lo) / w) * 100, width: Math.max(((b - a) / w) * 100, 0.4) };       // i velmi krátký zdroj je vidět
};

/**
 * Pruhy zdrojů na společné ose. Osa jde od nejdřívějšího začátku po nejpozdější konec; zvýrazněný úsek je společný
 * (překryv) nebo celé sjednocení (union). Zdroj bez dat (start / end null) pruh nemá.
 */
export function timeline(spans: readonly { start?: number | null; end?: number | null }[], mode: GridMode,
  common: { start: number; end: number } | null): Timeline | null {
  const ok = spans.filter((s): s is { start: number; end: number } => s.start != null && s.end != null);
  if (!ok.length) return null;
  const lo = Math.min(...ok.map((s) => s.start));
  let hi = Math.max(...ok.map((s) => s.end));
  if (!(hi > lo)) hi = lo + 1;
  const bars = spans.map((s) => (s.start != null && s.end != null ? bar(s.start, s.end, lo, hi) : null));
  const c = mode === "union" ? { start: lo, end: hi } : common;
  return { lo, hi, bars, common: c && c.end > c.start ? bar(c.start, c.end, lo, hi) : null };
}

/** „Hezký“ krok osy [s] pro daný rozsah a přibližný počet dílků. */
export function niceStep(span: number, target = 5): number {
  const raw = span / Math.max(target, 1);
  const steps = [0.1, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800];
  return steps.find((s) => s >= raw) ?? Math.ceil(raw / 86400) * 86400;
}

/** Značky osy: časy [s] v rozsahu <lo, hi> po „hezkém“ kroku zarovnaném na hodiny (podle počátku), pokud ho známe. */
export function ticks(lo: number, hi: number, origin: string | null, target = 5): number[] {
  const step = niceStep(hi - lo, target);
  const o = origin ? Date.parse(origin + "Z") / 1000 : 0;
  const first = Math.ceil((lo + o) / step - 1e-9) * step - o;
  const out: number[] = [];
  for (let t = first; t <= hi + 1e-9; t += step) out.push(t);
  return out;
}

const p2 = (n: number) => String(n).padStart(2, "0");
const utc = (origin: string, t: number) => new Date(Date.parse(origin + "Z") + t * 1000);

/** Čas na ose [s od počátku] jako „H:MM“ (s datem „D.M. H:MM“); bez hodin v souboru doba. */
export function fmtClock(t: number, origin: string | null, withDate = false): string {
  if (!origin) return fmtDur(t);
  const d = utc(origin, t);
  const hm = `${d.getUTCHours()}:${p2(d.getUTCMinutes())}` + (d.getUTCSeconds() ? `:${p2(d.getUTCSeconds())}` : "");
  return withDate ? `${d.getUTCDate()}.${d.getUTCMonth() + 1}. ${hm}` : hm;
}

/** Rozsah zdroje: „8.10. 6:00–14:00“ (jeden den) / „8.10. 6:00 – 9.10. 2:00“; bez hodin „0 s – 4 h“. */
export function fmtRange(start: number | null | undefined, end: number | null | undefined, origin: string | null): string {
  if (start == null || end == null) return "–";
  if (!origin) return `${fmtDur(start)} – ${fmtDur(end)}`;
  const a = utc(origin, start), b = utc(origin, end);
  const sameDay = a.getUTCFullYear() === b.getUTCFullYear() && a.getUTCMonth() === b.getUTCMonth() && a.getUTCDate() === b.getUTCDate();
  return sameDay ? `${fmtClock(start, origin, true)}–${fmtClock(end, origin)}` : `${fmtClock(start, origin, true)} – ${fmtClock(end, origin, true)}`;
}

/** Doba / čas v sekundách čitelně: 0,5 s · 90 s → 1,5 min · 3 600 → 1 h. */
export function fmtDur(s: number): string {
  const a = Math.abs(s);
  const num = (x: number) => String(+x.toPrecision(3)).replace(".", ",");
  if (a < 120) return `${num(s)} s`;
  if (a < 3600) return `${num(s / 60)} min`;
  if (a < 172800) return `${num(s / 3600)} h`;
  return `${num(s / 86400)} d`;
}

/** Perioda vzorkování [s] jako text („1 s“, „500 ms“); chybějící „–“. */
export function fmtPeriod(s: number | null | undefined): string {
  if (s == null || !(s > 0)) return "–";
  if (s < 1) return `${+(s * 1000).toPrecision(3)} ms`.replace(".", ",");
  return fmtDur(s);
}

// ---- minigraf
/** Cesta SVG `M x,y L …` pro řadu (t, v) v rámečku w × h (svislá osa podle min / max řady, vodorovná podle času). */
export function sparkPath(t: readonly number[], v: readonly number[], w = 60, h = 18, pad = 1.5): string {
  const n = Math.min(t.length, v.length);
  if (n < 2) return "";
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < n; i++) { if (v[i] < lo) lo = v[i]; if (v[i] > hi) hi = v[i]; }
  const t0 = t[0], dt = t[n - 1] - t0 || 1, dv = hi - lo;
  const pts: string[] = [];
  for (let i = 0; i < n; i++) {
    const x = ((t[i] - t0) / dt) * w;
    const y = dv > 0 ? pad + (1 - (v[i] - lo) / dv) * (h - 2 * pad) : h / 2;
    pts.push(`${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(" ");
}

/** Posun času: hodiny ⇄ sekundy (zaokrouhleno na milisekundy). */
export const hoursToSec = (h: number) => Math.round(h * 3600 * 1000) / 1000;
export const secToHours = (s: number) => +(s / 3600).toPrecision(6);
