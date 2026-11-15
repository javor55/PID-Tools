// Trendy – čisté pomocné funkce (bez Reactu): popis signálů, strom, rozvržení panelů, zředění, výpočty, CSV.

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

export const ROLE_COLOR: Record<string, string> = {
  PV: "#1f5fa8", SP: "#6d28d9", MV: "#c2410c", DV: "#0d9488", POS: "#9a3412", MODE: "#64748b",
};
export const ROLE_DASH: Record<string, string | null> = { SP: "6 4" };
const OTHER = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea",
  "#ea580c", "#0f766e", "#b91c1c", "#4f46e5", "#a16207"];
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
