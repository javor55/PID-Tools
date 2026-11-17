// Čisté funkce nástrojů grafu `LineChart` (FEATURE-004): nejbližší vzorek, sjednocení řad pro export, TSV / CSV, PNG.
// Bez Reactu; jen `svgToPngBlob` a `downloadBlob` sahají na DOM.

/** Souřadnice x tak, jak ji graf kreslí: u `logX` dekadický logaritmus (mimo kladné hodnoty se ořízne jako v grafu). */
export const txOf = (log?: boolean) => (log ? (v: number) => Math.log10(Math.max(v, 1e-12)) : (v: number) => v);

/** Vzorek řady pro export a odečet (jen to, co nástroje potřebují z `Series`). */
export interface Sample { name: string; x: ArrayLike<number>; y: ArrayLike<number> }

const sortedCache = new WeakMap<object, boolean>();
/** Je `x` konečné a neklesající? (jen pak jde hledat půlením; výsledek se pamatuje pro dané pole) */
function isSorted(x: ArrayLike<number>): boolean {
  const hit = sortedCache.get(x);
  if (hit !== undefined) return hit;
  let ok = true;
  for (let i = 0; i < x.length && ok; i++) if (!Number.isFinite(x[i]) || (i > 0 && x[i] < x[i - 1])) ok = false;
  sortedCache.set(x, ok);
  return ok;
}

/**
 * Index vzorku nejblíže `target` (v jednotkách dat; u `log` se porovnává v logaritmu). Řada seřazená podle x se hledá
 * půlením (O(log n)); řada s NaN nebo neseřazená (fázové grafy) lineárně. Vrací −1, když není žádný konečný x.
 */
export function nearestIndex(x: ArrayLike<number>, target: number, log = false): number {
  const n = x.length;
  if (!n || !Number.isFinite(target)) return -1;
  const tx = txOf(log), t = tx(target);
  if (!isSorted(x)) {
    let best = -1, bd = Infinity;
    for (let i = 0; i < n; i++) {
      const v = tx(x[i]);
      if (!Number.isFinite(v)) continue;
      const d = Math.abs(v - t);
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  }
  let lo = 0, hi = n - 1;                       // první index s tx(x) ≥ t
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (tx(x[mid]) < t) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(tx(x[lo - 1]) - t) <= Math.abs(tx(x[lo]) - t)) return lo - 1;
  return lo;
}

/** Rozsah x řady [min, max] (konečné hodnoty); null, když žádná není. */
export function xRange(x: ArrayLike<number>): [number, number] | null {
  if (isSorted(x)) return x.length ? [x[0], x[x.length - 1]] : null;
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < x.length; i++) if (Number.isFinite(x[i])) { if (x[i] < lo) lo = x[i]; if (x[i] > hi) hi = x[i]; }
  return lo <= hi ? [lo, hi] : null;
}

/** Nejvyšší počet řádků exportu; nad ním se použije osa x první řady (viz `unionRows`). */
export const MAX_EXPORT_ROWS = 100_000;

export interface ExportTable { header: string[]; rows: (number | null)[][]; mode: "union" | "first" }

/**
 * Tabulka pro export: sloupec x + sloupec za každou řadu. Řady mívají různé x, proto se řádky sjednotí přes všechna
 * konečná x (seřazená); kde řada v daném x nemá vzorek, je buňka prázdná (null) – nic se nevymýšlí.
 * Kdyby sjednocení dalo víc než `max` řádků (řady s odlišnou mřížkou po tisících bodů), použije se jen osa x první
 * řady a ostatním řadám se přiřadí nejbližší vzorek (v rámci rozsahu jejich x; mimo něj prázdno).
 */
export function unionRows(series: Sample[], xName: string, max = MAX_EXPORT_ROWS): ExportTable {
  const header = [xName, ...series.map((s) => s.name)];
  const xs = new Set<number>();
  let tooMany = false;
  for (const s of series) {
    for (let i = 0; i < s.x.length; i++) if (Number.isFinite(s.x[i])) xs.add(s.x[i]);
    if (xs.size > max) { tooMany = true; break; }
  }
  if (!tooMany) {
    const grid = [...xs].sort((a, b) => a - b);
    const maps = series.map((s) => {
      const m = new Map<number, number>();
      for (let i = 0; i < s.x.length; i++) if (Number.isFinite(s.x[i]) && Number.isFinite(s.y[i])) m.set(s.x[i], s.y[i]);
      return m;
    });
    return { header, mode: "union", rows: grid.map((x) => [x, ...maps.map((m) => m.get(x) ?? null)]) };
  }
  const ref = series[0], rows: (number | null)[][] = [];
  const ranges = series.map((s) => xRange(s.x));
  for (let i = 0; i < ref.x.length; i++) {
    const x = ref.x[i];
    if (!Number.isFinite(x)) continue;
    rows.push([x, ...series.map((s, k) => {
      if (k === 0) return Number.isFinite(s.y[i]) ? s.y[i] : null;
      const r = ranges[k];
      if (!r || x < r[0] || x > r[1]) return null;
      const j = nearestIndex(s.x, x);
      return j >= 0 && Number.isFinite(s.y[j]) ? s.y[j] : null;
    })]);
    if (rows.length >= max) break;
  }
  return { header, rows, mode: "first" };
}

/** Číslo jako text s desetinným oddělovačem `dec` (12 platných číslic – bez šumu zaokrouhlení typu 0,30000000000000004). */
export const numText = (v: number | null, dec = "."): string => (v === null || !Number.isFinite(v) ? "" : String(+v.toPrecision(12)).replace(".", dec));

/** Hodnota pro zobrazení v tabulce odečtu (p platných číslic, „–“ pro chybějící). */
export const showNum = (v: number | null | undefined, dec: string, p = 4): string =>
  v === null || v === undefined || !Number.isFinite(v) ? "–" : String(+v.toPrecision(p)).replace(".", dec);

/** TSV (tabulátor, desetinný oddělovač jazyka) – vloží se do Excelu po buňkách. */
export function toTsv(t: ExportTable, dec: string): string {
  const clean = (s: string) => s.replace(/[\t\r\n]+/g, " ");
  return [t.header.map(clean).join("\t"), ...t.rows.map((r) => r.map((v) => numText(v, dec)).join("\t"))].join("\n");
}

/** CSV strojově čitelné: oddělovač „,“, desetinná tečka, hodnoty s čárkou / uvozovkou / koncem řádku v uvozovkách. */
export function toCsv(t: ExportTable): string {
  const q = (s: string) => (/[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  return [t.header.map(q).join(","), ...t.rows.map((r) => r.map((v) => numText(v)).join(","))].join("\r\n") + "\r\n";
}

/** Stažení souboru přes `<a download>` (stejný vzor jako export v Ladění). */
export function downloadBlob(blob: Blob, name: string): void {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

// Vlastnosti stylu, které se do PNG kopírují z vypočtených hodnot (PNG se kreslí bez CSS stránky).
const STYLE_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "opacity", "font-family", "font-size",
  "font-weight", "text-anchor"];

/** Pozadí prvku: nejbližší neprůhledná barva pozadí nahoru po stromu (jinak bílá). */
function backgroundOf(el: Element): string {
  for (let e: Element | null = el; e; e = e.parentElement) {
    const c = getComputedStyle(e).backgroundColor;
    if (c && c !== "transparent" && !/rgba\(.*,\s*0\)$/.test(c)) return c;
  }
  return "#ffffff";
}

export interface LegendItem { name: string; color: string }

/**
 * SVG grafu → PNG (2× rozlišení). Kopie SVG dostane styl každého prvku z vypočtených hodnot originálu, pozadí a legendu
 * pod grafem; obrázek se načte přes `Image` (data URL) a nakreslí do canvasu.
 */
export async function svgToPngBlob(svg: SVGSVGElement, w: number, h: number, legend: LegendItem[], scale = 2): Promise<Blob> {
  const NS = "http://www.w3.org/2000/svg";
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const src = [svg, ...Array.from(svg.querySelectorAll("*"))], dst = [clone, ...Array.from(clone.querySelectorAll("*"))];
  src.forEach((s, i) => {
    const cs = getComputedStyle(s);
    dst[i].setAttribute("style", STYLE_PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";"));
  });
  const font = getComputedStyle(svg).getPropertyValue("font-family") || "sans-serif";
  const rowH = 16;
  // legenda: položky se zalamují do řádků podle odhadnuté šířky textu
  const rows: LegendItem[][] = [[]];
  let used = 8;
  for (const it of legend) {
    const wi = 24 + it.name.length * 6 + 12;
    if (used + wi > w && rows[rows.length - 1].length) { rows.push([]); used = 8; }
    rows[rows.length - 1].push(it); used += wi;
  }
  const extra = legend.length ? rows.length * rowH + 6 : 0, total = h + extra;
  clone.setAttribute("xmlns", NS);
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(total));
  clone.setAttribute("viewBox", `0 0 ${w} ${total}`);
  clone.setAttribute("preserveAspectRatio", "xMinYMin meet");
  const inner = document.createElementNS(NS, "g");
  while (clone.firstChild) inner.appendChild(clone.firstChild);
  const bg = document.createElementNS(NS, "rect");
  for (const [k, v] of Object.entries({ x: "0", y: "0", width: String(w), height: String(total), fill: backgroundOf(svg) })) bg.setAttribute(k, v);
  clone.appendChild(bg);
  clone.appendChild(inner);
  const firstText = svg.querySelector("text");
  const muted = firstText ? getComputedStyle(firstText).getPropertyValue("fill") : "currentColor";
  rows.forEach((row, r) => {
    let x = 8;
    for (const it of row) {
      const sw = document.createElementNS(NS, "rect");
      for (const [k, v] of Object.entries({ x: String(x), y: String(h + 6 + r * rowH + 4), width: "14", height: "3", fill: it.color })) sw.setAttribute(k, v);
      const tx = document.createElementNS(NS, "text");
      tx.setAttribute("x", String(x + 20)); tx.setAttribute("y", String(h + 6 + r * rowH + 9));
      tx.setAttribute("style", `font-family:${font};font-size:11px;fill:${muted}`);
      tx.textContent = it.name;
      clone.appendChild(sw); clone.appendChild(tx);
      x += 24 + it.name.length * 6 + 12;
    }
  });
  const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(clone));
  const img = new Image();
  await new Promise<void>((ok, bad) => { img.onload = () => ok(); img.onerror = () => bad(new Error("PNG: SVG image failed to load")); img.src = url; });
  const cv = document.createElement("canvas");
  cv.width = Math.round(w * scale); cv.height = Math.round(total * scale);
  const g = cv.getContext("2d");
  if (!g) throw new Error("PNG: canvas unavailable");
  g.scale(scale, scale);
  g.drawImage(img, 0, 0, w, total);
  return new Promise<Blob>((ok, bad) => cv.toBlob((b) => (b ? ok(b) : bad(new Error("PNG: export failed"))), "image/png"));
}
