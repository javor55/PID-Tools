// Trendy – čisté pomocné funkce (bez Reactu): popis signálů, strom, rozvržení panelů, zředění, výpočty, CSV.
import PIDViewAn from "../../../../../pidtools/ui/static/viewer_an.js";

export type Role = "PV" | "SP" | "MV" | "DV" | "POS" | "MODE" | "";
export type LayoutMode = "one" | "loop" | "unit";

export interface SourceLite { id: string; name: string; columns: string[] }
export interface RefLite { source: string; column: string }
export interface LoopLite {
  index: number; tag: string;
  roles: { pv?: RefLite | null; sp?: RefLite | null; mv?: RefLite | null; pos?: RefLite | null; mode?: RefLite | null; dv?: RefLite[] };
}

export interface SigInfo {
  ref: string; source: string; sourceName: string; column: string;
  loop: string | null; loopIndex: number | null; role: Role;
  label: string;                 // název ve stromu (role, jinak sloupec)
  color: string; dash: string | null; quantity: string; unit: string;
}

export interface Series { ref: string; t: ArrayLike<number>; v: ArrayLike<number> }

export const ROLE_COLOR: Record<string, string> = {
  PV: "#1f5fa8", SP: "#6d28d9", MV: "#c2410c", DV: "#0d9488", POS: "#9a3412", MODE: "#64748b",
};
export const ROLE_DASH: Record<string, string | null> = { SP: "6 4" };
const OTHER = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea",
  "#ea580c", "#0f766e", "#b91c1c", "#4f46e5", "#a16207"];
export const CALC_COLORS = ["#be123c", "#1d4ed8", "#4d7c0f", "#b45309", "#9333ea", "#0f766e"];
const ISA: Record<string, string> = { T: "T", F: "F", L: "L", P: "P", Q: "Q", A: "A", W: "W", S: "S", D: "D" };

export const refOf = (r: RefLite) => `${r.source}:${r.column}`;

/** Jednotka z názvu sloupce: „… [°C]“ nebo „… (bar)“ na konci. */
export function unitFromName(name: string): string {
  const m = /[[(]([^\])[(]{1,12})[\])]\s*$/.exec(name);
  return m ? m[1].trim() : "";
}

/** Název sloupce bez jednotky na konci („FIC205.PV [t/h]“ → „FIC205.PV“). */
export const stripUnit = (name: string) => name.replace(/\s*[[(][^\])[(]{1,12}[\])]\s*$/, "") || name;

/** Veličina signálu (klíč pro „panel na veličinu“ a sdílenou osu): jednotka v názvu, MV / poloha = %, jinak podle ISA písmene. */
export function quantityOf(column: string, role: Role, tag: string | null): { key: string; unit: string } {
  const u = unitFromName(column);
  if (u) return { key: `u:${u}`, unit: u };
  if (role === "MV" || role === "POS") return { key: "u:%", unit: "%" };
  const src = role === "DV" || !tag ? column : tag;
  const m = /^\s*([A-Za-z])[A-Za-z]{0,3}[\s_-]?\d/.exec(src) ?? /^\s*([A-Za-z])[A-Za-z]{0,3}[\s_-]?\d/.exec(column);
  const k = m ? (ISA[m[1].toUpperCase()] ?? m[1].toUpperCase()) : "";
  return { key: k ? `q:${k}` : "q:", unit: "" };
}

/** Všechny sloupce všech zdrojů se smyčkou a rolí (první smyčka, která sloupec používá, vyhrává). */
export function describeSignals(sources: SourceLite[], loops: LoopLite[]): SigInfo[] {
  const byRef = new Map<string, { loop: LoopLite; role: Role }>();
  for (const lp of loops) {
    const r = lp.roles;
    const add = (x: RefLite | null | undefined, role: Role) => {
      if (x && !byRef.has(refOf(x))) byRef.set(refOf(x), { loop: lp, role });
    };
    add(r.pv, "PV"); add(r.sp, "SP"); add(r.mv, "MV"); add(r.pos, "POS"); add(r.mode, "MODE");
    (r.dv ?? []).forEach((d) => add(d, "DV"));
  }
  const out: SigInfo[] = [];
  let k = 0;
  for (const s of sources) {
    for (const c of s.columns) {
      const ref = `${s.id}:${c}`;
      const own = byRef.get(ref);
      const role = own?.role ?? "";
      const q = quantityOf(c, role, own?.loop.tag ?? null);
      out.push({
        ref, source: s.id, sourceName: s.name, column: c, loop: own?.loop.tag ?? null, loopIndex: own?.loop.index ?? null, role,
        label: role && role !== "DV" ? role : c,
        color: role ? ROLE_COLOR[role] : OTHER[k++ % OTHER.length], dash: ROLE_DASH[role] ?? null, quantity: q.key, unit: q.unit,
      });
    }
  }
  return out;
}

/** Výchozí výběr: PV, SP a MV smyček (nejvýše `max` signálů), jinak první sloupce. */
export function defaultSelection(sigs: SigInfo[], max = 6): string[] {
  const roles = sigs.filter((s) => s.role === "PV" || s.role === "SP" || s.role === "MV");
  return (roles.length ? roles : sigs).slice(0, max).map((s) => s.ref);
}

export interface TreeGroup { key: string; title: string; items: SigInfo[] }

/** Strom signálů: podle smyček (smyčka → role, zbylé sloupce ve skupině „Bez smyčky“) nebo podle zdrojů; hledání ve jménu. */
export function treeGroups(sigs: SigInfo[], by: "loop" | "source", query: string, onlyLoop: string | null, none = "–"): TreeGroup[] {
  const q = query.trim().toLowerCase();
  const keep = sigs.filter((s) => (!q || `${s.ref} ${s.column} ${s.loop ?? ""} ${s.sourceName}`.toLowerCase().includes(q))
    && (!onlyLoop || s.loop === onlyLoop));
  const map = new Map<string, TreeGroup>();
  for (const s of keep) {
    const key = by === "loop" ? (s.loop ?? "") : s.source;
    const title = by === "loop" ? (s.loop ?? none) : s.sourceName;
    if (!map.has(key)) map.set(key, { key, title, items: [] });
    map.get(key)!.items.push(s);
  }
  const arr = [...map.values()];
  if (by === "loop") arr.sort((a, b) => (a.key === "" ? 1 : 0) - (b.key === "" ? 1 : 0));
  return arr;
}

export interface Panel { id: string; title: string; refs: string[] }

/** Rozvržení vybraných signálů do panelů: všechny v jednom / panel na smyčku / panel na veličinu (jednotku). */
export function layoutPanels(sigs: SigInfo[], mode: LayoutMode, titles: { one: string; none: string }): Panel[] {
  if (!sigs.length) return [];
  if (mode === "one") return [{ id: "all", title: titles.one, refs: sigs.map((s) => s.ref) }];
  const map = new Map<string, Panel>();
  for (const s of sigs) {
    let id: string, title: string;
    if (mode === "loop") {
      id = s.loop ? `l:${s.loop}` : `s:${s.source}`;
      title = s.loop ?? s.sourceName;
    } else {
      id = s.quantity;
      title = s.unit ? `[${s.unit}]` : s.quantity.startsWith("q:") && s.quantity.length > 2 ? s.quantity.slice(2) : titles.none;
    }
    if (!map.has(id)) map.set(id, { id, title, refs: [] });
    map.get(id)!.refs.push(s.ref);
  }
  return [...map.values()];
}

export interface Axis { key: string; refs: string[]; lo: number; hi: number; unit: string }

/** Osy panelu: sdílená osa = všechny signály na jedné ose, jinak jedna osa na veličinu (PV a SP spolu, MV zvlášť). Rozsah z dat v okně [a, b]. */
export function panelAxes(series: Series[], info: Map<string, SigInfo>, shared: boolean, a: number, b: number): Axis[] {
  const groups = new Map<string, Axis>();
  for (const s of series) {
    const i = info.get(s.ref);
    const key = shared ? "all" : (i?.quantity ?? s.ref);
    let lo = Infinity, hi = -Infinity;
    for (let k = 0; k < s.t.length; k++) {
      if (s.t[k] < a || s.t[k] > b) continue;
      const y = s.v[k];
      if (y < lo) lo = y;
      if (y > hi) hi = y;
    }
    const g = groups.get(key) ?? { key, refs: [], lo: Infinity, hi: -Infinity, unit: i?.unit ?? "" };
    g.refs.push(s.ref);
    g.lo = Math.min(g.lo, lo); g.hi = Math.max(g.hi, hi);
    groups.set(key, g);
  }
  return [...groups.values()].filter((g) => Number.isFinite(g.lo)).map((g) => {
    const span = g.hi - g.lo || Math.max(Math.abs(g.hi) * 0.1, 1);
    const pad = span * 0.06;
    return { ...g, lo: g.lo - pad, hi: g.hi + pad };
  });
}

/** Hezká dělení osy: [hodnota…] po „pěkném“ kroku. */
export function niceTicks(lo: number, hi: number, n = 4): number[] {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / n, e = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * e >= raw * (1 - 1e-9)) ?? 10) * e;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

export function fmtNum(v: number | null | undefined, d = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const s = Math.abs(v) >= 1000 ? v.toFixed(0) : String(+v.toPrecision(d));
  return s;
}

/** Zředění řady (min / max po skupinách) v úseku [a, b] na nejvýše ~2n bodů; pro vypočtené signály a přehled. */
export function minmaxDecimate(t: ArrayLike<number>, v: ArrayLike<number>, a: number, b: number, n: number): Series["t"][] {
  const ti: number[] = [], vi: number[] = [];
  for (let i = 0; i < t.length; i++) if (t[i] >= a && t[i] <= b && Number.isFinite(v[i])) { ti.push(t[i]); vi.push(v[i]); }
  if (ti.length <= 2 * n) return [ti, vi];
  const g = Math.ceil(ti.length / n), ot: number[] = [], ov: number[] = [];
  for (let s = 0; s < ti.length; s += g) {
    const e = Math.min(ti.length, s + g);
    let imin = s, imax = s;
    for (let i = s; i < e; i++) { if (vi[i] < vi[imin]) imin = i; if (vi[i] > vi[imax]) imax = i; }
    const [p, q] = imin < imax ? [imin, imax] : [imax, imin];
    ot.push(ti[p]); ov.push(vi[p]);
    if (q !== p) { ot.push(ti[q]); ov.push(vi[q]); }
  }
  return [ot, ov];
}

/** Hodnota řady v čase x (lineární interpolace; mimo záznam null; mezera větší než gap → null). */
export function valueAt(s: Series, x: number, gap = Infinity): number | null {
  const n = s.t.length;
  if (!n || x < s.t[0] || x > s.t[n - 1]) return null;
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (s.t[m] <= x) lo = m; else hi = m; }
  if (s.t[hi] === x) return s.v[hi];
  const dt = s.t[hi] - s.t[lo];
  if (dt > gap) return null;
  return s.v[lo] + ((s.v[hi] - s.v[lo]) * (x - s.t[lo])) / dt;
}

export interface Stat { min: number | null; max: number | null; mean: number | null; std: number | null }
export function statsOf(s: Series, a: number, b: number): Stat {
  let n = 0, sum = 0, sq = 0, mn = Infinity, mx = -Infinity;
  for (let i = 0; i < s.t.length; i++) {
    if (s.t[i] < a || s.t[i] > b || !Number.isFinite(s.v[i])) continue;
    const y = s.v[i];
    n++; sum += y; sq += y * y;
    if (y < mn) mn = y;
    if (y > mx) mx = y;
  }
  if (!n) return { min: null, max: null, mean: null, std: null };
  const mean = sum / n;
  return { min: mn, max: mx, mean, std: Math.sqrt(Math.max(0, sq / n - mean * mean)) };
}

// ---------------------------------------------------------------- vypočtené signály (vzorce z viewer_an.js)
export interface Calc { id: string; name: string; expr: string; unit: string }
interface AN {
  parse: (s: string, names: string[]) => { ast: unknown; refs: string[] };
  evaluate: (ast: unknown, ctx: { t: Float64Array; n: number; sig: (n: string) => Float64Array }) => Float64Array | number;
  zoh: (s: { t: ArrayLike<number>; v: ArrayLike<number>; n: number }, tq: ArrayLike<number>) => Float64Array;
}
const An = PIDViewAn as unknown as AN & { ExprError: new (...a: unknown[]) => Error & { msg?: string; pos?: number } };

/** Jména ve vzorcích: celý odkaz `zdroj:sloupec` v [] a jednoznačný název sloupce. */
export function formulaNames(sigs: SigInfo[]): Map<string, string> {
  const out = new Map<string, string>();
  const cnt = new Map<string, number>();
  for (const s of sigs) cnt.set(s.column, (cnt.get(s.column) ?? 0) + 1);
  for (const s of sigs) { out.set(s.ref, s.ref); if (cnt.get(s.column) === 1) out.set(s.column, s.ref); }
  return out;
}

/** Odkazy na signály ve vzorci (jen kontrola a závislosti); chyba = text. */
export function calcRefs(expr: string, names: Map<string, string>): { refs: string[]; error: string | null } {
  try {
    const p = An.parse(expr, [...names.keys()]);
    return { refs: [...new Set(p.refs.map((r) => names.get(r) ?? r))], error: null };
  } catch (e) {
    const x = e as { msg?: string; pos?: number; arg?: unknown; message?: string };
    return { refs: [], error: x.msg ? `${x.msg}${x.arg !== undefined ? ` (${String(x.arg)})` : ""} @${(x.pos ?? 0) + 1}` : String(x.message ?? e) };
  }
}

/** Vypočte signál na časech nejhustší z použitých řad (ostatní: poslední známá hodnota). */
export function computeCalc(c: Calc, names: Map<string, string>, data: Map<string, Series>): { series: Series | null; error: string | null } {
  const { refs, error } = calcRefs(c.expr, names);
  if (error) return { series: null, error };
  const have = refs.map((r) => data.get(r));
  if (!refs.length || have.some((x) => !x || !x.t.length)) return { series: null, error: null };
  const base = have.reduce((p, x) => (x!.t.length > p!.t.length ? x : p))!;
  const t = Float64Array.from(base.t);
  const cache = new Map<string, Float64Array>();
  const sig = (nm: string) => {
    const ref = names.get(nm) ?? nm;
    if (!cache.has(ref)) {
      const s = data.get(ref)!;
      cache.set(ref, s === base ? Float64Array.from(s.v) : An.zoh({ t: s.t, v: s.v, n: s.t.length }, t));
    }
    return cache.get(ref)!;
  };
  try {
    const p = An.parse(c.expr, [...names.keys()]);
    const y = An.evaluate(p.ast, { t, n: t.length, sig });
    const ts: number[] = [], vs: number[] = [];
    for (let i = 0; i < t.length; i++) {
      const v = typeof y === "number" ? y : y[i];
      if (Number.isFinite(v)) { ts.push(t[i]); vs.push(v); }
    }
    return { series: { ref: `calc:${c.id}`, t: ts, v: vs }, error: null };
  } catch (e) {
    return { series: null, error: String((e as Error).message ?? e) };
  }
}

// ---------------------------------------------------------------- čas a CSV
export function fmtClock(origin: string | null, t: number, withDate = false, sec = true): string {
  if (!origin) return `${fmtNum(t, 5)} s`;
  const d = new Date(Date.parse(origin.length > 19 ? origin : origin + "Z") + t * 1000);
  const p = (x: number) => String(x).padStart(2, "0");
  const hm = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}${sec ? ":" + p(d.getUTCSeconds()) : ""}`;
  return withDate ? `${d.getUTCDate()}.${d.getUTCMonth() + 1}. ${hm}` : hm;
}

export function fmtDur(s: number): string {
  if (!Number.isFinite(s)) return "–";
  if (s < 90) return `${+s.toFixed(1)} s`;
  if (s < 5400) return `${Math.round(s / 6) / 10} min`;
  return `${Math.round(s / 360) / 10} h`;
}

/** CSV viditelného okna: čas [s], čas hodin (je-li), sloupce; řádky = sjednocení časů, prázdné buňky tam, kde signál nemá vzorek. */
export function toCsv(series: { name: string; t: ArrayLike<number>; v: ArrayLike<number> }[], origin: string | null,
  a: number, b: number, sep = ";"): string {
  const times = new Set<number>();
  for (const s of series) for (let i = 0; i < s.t.length; i++) if (s.t[i] >= a && s.t[i] <= b) times.add(s.t[i]);
  const ts = [...times].sort((x, y) => x - y);
  const idx = series.map(() => 0);
  const q = (x: string) => (/[;"\n,]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x);
  const head = ["t [s]", ...(origin ? ["clock"] : []), ...series.map((s) => q(s.name))];
  const lines = [head.join(sep)];
  for (const t of ts) {
    const row: string[] = [String(+t.toFixed(6))];
    if (origin) row.push(new Date(Date.parse(origin.length > 19 ? origin : origin + "Z") + t * 1000).toISOString().replace("T", " ").slice(0, 23));
    series.forEach((s, k) => {
      while (idx[k] < s.t.length && s.t[idx[k]] < t) idx[k]++;
      row.push(idx[k] < s.t.length && s.t[idx[k]] === t && Number.isFinite(s.v[idx[k]]) ? String(+s.v[idx[k]].toPrecision(9)) : "");
    });
    lines.push(row.join(sep));
  }
  return lines.join("\n");
}
