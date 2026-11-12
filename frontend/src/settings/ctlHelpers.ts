// Čisté pomocné funkce knihovny a editoru regulátorů (seskupení, chyby překladu, rovnice, schéma, skládání částí).
import type { CompileResult, Param, Part, Profile, Summary } from "./ctlApi";

export type GroupId = "siemens" | "other" | "mine";
export interface Group { id: GroupId; items: Summary[] }

/** Seznam knihovny → skupiny Předvolby – Siemens / ostatní a obecné / Moje regulátory (podle hledaného textu; prázdné skupiny se vynechají). */
export function groupControllers(list: Summary[], query = ""): Group[] {
  const q = query.trim().toLowerCase();
  const hit = (c: Summary) => !q || `${c.name} ${c.vendor} ${c.id}`.toLowerCase().includes(q);
  const by = (f: (c: Summary) => boolean) => list.filter((c) => hit(c) && f(c));
  const groups: Group[] = [
    { id: "siemens", items: by((c) => c.tag !== "custom" && c.vendor.toLowerCase().includes("siemens")) },
    { id: "other", items: by((c) => c.tag !== "custom" && !c.vendor.toLowerCase().includes("siemens")) },
    { id: "mine", items: by((c) => c.tag === "custom") },
  ];
  return groups.filter((g) => g.items.length > 0);
}

export type Tag = "verified" | "unverified" | "custom";
export const tagsOf = (c: Summary): Tag[] => [c.verified ? "verified" : "unverified", ...(c.tag === "custom" ? ["custom" as const] : [])];

export interface Marker { line: number; col: number; message: string; kind: "error" | "warning" }

/** Chyby a varování překladu → značky po řádcích (chyba přebíjí varování; řádek mimo zdroj se ořízne). */
export function markersByLine(source: string, res: Pick<CompileResult, "errors" | "warnings"> | null): Map<number, Marker> {
  const out = new Map<number, Marker>();
  if (!res) return out;
  const n = Math.max(1, source.split("\n").length);
  const add = (list: CompileResult["errors"], kind: Marker["kind"]) => {
    for (const i of list) {
      const line = Math.min(Math.max(1, i.line), n);
      const old = out.get(line);
      if (!old || (old.kind === "warning" && kind === "error")) out.set(line, { line, col: i.col, message: i.message, kind });
    }
  };
  add(res.warnings, "warning");
  add(res.errors, "error");
  return out;
}

/** Chyby kontroly profilu z API (422: detail.problems[{path, message}], případně text) → jeden text. */
export function problemText(msg: string): string {
  try {
    const j = JSON.parse(msg) as { message?: string; problems?: { path: string; message: string }[] };
    if (j.problems?.length) return j.problems.map((p) => (p.path ? `${p.path}: ${p.message}` : p.message)).join("\n");
    if (j.message) return j.message;
  } catch { /* prostý text */ }
  return msg;
}

type St = Record<string, unknown>;
const st = (p: Profile): St => p.structure as St;
const sub = (o: unknown, k: string): St => ((o as St | undefined)?.[k] ?? {}) as St;

export const isProgram = (p: Profile) => p.kind === "program";

/** Vybraná část pro skupinu registru (kind z `/controllers/parts`) podle `structure` profilu. */
export function selectedPart(p: Profile, kind: string): string {
  const s = st(p);
  switch (kind) {
    case "forms": return (s.form as string) ?? "ideal";
    case "d_sources": return (sub(s, "d").source as string) ?? "error";
    case "d_filters": return (sub(s, "d").filter as string) ?? "td_over_n";
    case "antiwindups": return (s.antiwindup as string) ?? "clamp_conditional";
    case "algorithms": return (s.algorithm as string) ?? "position";
    case "normalisations": return (sub(s, "normalisation").kind as string) ?? "percent";
    case "pv_filters": return (sub(s, "pv").filter as string) ?? "lag1";
    case "deadbands": return (sub(sub(s, "error"), "deadband").other as string) ?? "none";
    case "nl_gains": return (sub(sub(s, "error"), "nonlinear").kind as string) ?? "none";
    case "output_stages": return (sub(s, "output").stage as string) ?? "none";
    default: return "";
  }
}

/** Nastaví část ve `structure` (kopie); `none` u mrtvého pásma / nelineárního zesílení položku odebere. */
export function setPart(p: Profile, kind: string, id: string): Profile {
  const s = structuredClone(st(p)) as St;
  const put = (k: string, v: St) => { s[k] = { ...sub(s, k), ...v }; };
  switch (kind) {
    case "forms": s.form = id; break;
    case "d_sources": put("d", { source: id }); break;
    case "d_filters": put("d", { filter: id }); break;
    case "antiwindups": s.antiwindup = id; break;
    case "algorithms": s.algorithm = id; break;
    case "normalisations": s.normalisation = { kind: id }; break;
    case "pv_filters": put("pv", { filter: id }); break;
    case "deadbands": {
      const e = { ...sub(s, "error") };
      if (id === "none") delete e.deadband; else e.deadband = { modes: {}, other: id };
      s.error = e; break;
    }
    case "nl_gains": {
      const e = { ...sub(s, "error") };
      if (id === "none") delete e.nonlinear; else e.nonlinear = { ...sub(e, "nonlinear"), kind: id };
      s.error = e; break;
    }
    case "output_stages": put("output", { stage: id }); break;
  }
  return { ...p, structure: s };
}

/** Po změně částí doplní chybějící parametry vybraných částí (role z katalogu, výchozí hodnota, jednotka, meze) a odebere parametry odložených. */
export function syncParams(p: Profile, parts: Part[]): Profile {
  const wanted = new Map<string, Part["params"][number]>();
  const owned = new Set<string>();
  for (const part of parts) {
    const used = selectedPart(p, part.kind) === part.id;
    for (const q of part.params) { owned.add(q.role); if (used) wanted.set(q.role, q); }
  }
  const have = new Set(p.params.map((x) => x.role));
  const keep = p.params.filter((x) => !owned.has(x.role) || wanted.has(x.role));
  const add: Param[] = [...wanted.values()].filter((q) => !have.has(q.role)).map((q) => ({
    key: q.role, role: q.role, name: q.role, unit: q.unit === "bool" ? undefined : q.unit, default: q.default, range: q.range ?? undefined,
  }));
  return { ...p, params: [...keep, ...add] };
}

const EQ: Record<string, string> = {
  ideal: "u = Kc · [ (b·SP − PV) + 1/(Ti·s) · e + Td·s/(1 + Td/N·s) · (c·SP − PV) ]",
  parallel: "u = Kp · (b·SP − PV) + Ki/s · e + Kd·s/(1 + s/N) · (c·SP − PV)",
  series: "u = Kc · (1 + 1/(Ti·s)) · (1 + Td·s/(1 + Td/N·s)) · e",
};

/** Rovnice regulátoru jako text (skládaný profil podle formy a algoritmu). */
export function equationText(p: Profile): string {
  if (isProgram(p)) return "MV = f(SP, PV, FF, stavy; parametry)";
  const base = EQ[selectedPart(p, "forms")] ?? EQ.ideal;
  return selectedPart(p, "algorithms") === "velocity" ? base.replace("u =", "Δu =") : base;
}

/** Fakta o skladbě: dvojice (registr, vybraná část); pro program prázdné. */
export function facts(p: Profile): [string, string][] {
  if (isProgram(p)) return [];
  return ["forms", "d_sources", "d_filters", "antiwindups", "algorithms", "deadbands", "pv_filters", "nl_gains", "output_stages",
    "normalisations"].map((k) => [k, selectedPart(p, k)]);
}

/** Řetěz bloků jako klíče překladů (SP → odchylka → P·I·D → FF → meze → MV); program má vlastní blok. */
export function blockChain(p: Profile): string[] {
  if (isProgram(p)) return ["rg_ui_blk_inputs", "rg_ui_blk_program", "rg_ui_blk_mv"];
  const s = st(p);
  const nl = selectedPart(p, "deadbands") !== "none" || selectedPart(p, "nl_gains") !== "none";
  const out = ["rg_ui_blk_sp", nl ? "rg_ui_blk_error_nl" : "rg_ui_blk_error", "rg_ui_blk_pid"];
  if (sub(s, "ff").mode) out.push("rg_ui_blk_ff");
  out.push("rg_ui_blk_limits");
  if (selectedPart(p, "output_stages") !== "none") out.push("rg_ui_blk_stage");
  out.push("rg_ui_blk_mv");
  return out;
}

/** Speciální funkce použité v profilu (id položky katalogu `registr/id`). */
export function specials(p: Profile): string[] {
  if (isProgram(p)) return [];
  const out: string[] = [];
  const nl = selectedPart(p, "nl_gains"), stage = selectedPart(p, "output_stages");
  if (selectedPart(p, "deadbands") === "gap") out.push("deadbands/gap");
  if (nl !== "none") out.push(`nl_gains/${nl}`);
  if (selectedPart(p, "algorithms") === "velocity") out.push("algorithms/velocity");
  if (selectedPart(p, "antiwindups") === "external_reset") out.push("antiwindups/external_reset");
  if (stage !== "none") out.push(`output_stages/${stage}`);
  return out;
}

/** Počty kontrol protokolu podle stavu. */
export function countChecks(checks: { status: string }[]) {
  const n = (s: string) => checks.filter((c) => c.status === s).length;
  return { ok: n("ok"), warn: n("warn"), fail: n("fail") };
}

/** Řádek a sloupec (od 1) ve zdroji → posun ve znacích (pro označení chyby v textovém poli). */
export function offsetOf(source: string, line: number, col: number): number {
  const lines = source.split("\n");
  let o = 0;
  for (let i = 0; i < Math.min(line - 1, lines.length); i++) o += lines[i].length + 1;
  return Math.min(o + Math.max(0, col - 1), source.length);
}

export const NEW_PROGRAM = `# PID regulátor (ideální) – jeden krok výpočtu
param Kp = 1.0  "Zesílení"        [-]
param Ti = 60   "Integrační čas"  [s]  min 0.1
param Td = 0    "Derivační čas"   [s]
param N  = 10   "Filtr D"         [-]
state I  = 0    [%] init MV0 - Kp * (SP - PV) - FF

e   = SP - PV
d   = lag(Td * ddt(-PV), Td / N)
v   = Kp * e + I + Kp * d + FF
MV  = clamp(v, MV_LO, MV_HI)
I   = I + Kp / Ti * e * dt + (MV - v) * dt / Ti      # zpětný výpočet

map Kp = Kc
map Ti = Ti
map Td = Td
map N = N
`;

export const SNIPPETS: [string, string][] = [
  ["param", 'param Kx = 1.0 "Popis" [-] min 0\n'],
  ["state", "state X = 0 [%]\n"],
  ["e = SP − PV", "e = SP - PV\n"],
  ["clamp", "MV = clamp(v, MV_LO, MV_HI)\n"],
  ["lag · ddt", "d = lag(Td * ddt(-PV), Td / N)\n"],
  ["deadband", "e = deadband(SP - PV, 0.5)\n"],
  ["gap", "e = gap(SP - PV, 0.5, 0.3)\n"],
  ["table", "k = table(PV, [0, 50, 100], [1, 1.5, 2])\n"],
  ["map", "map Kp = Kc\nunmap Kc = Kp\n"],
];
