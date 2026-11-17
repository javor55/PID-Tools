// Cílené zneplatnění dotazů prostoru. Všechny dotazy mají tvar ["ws", wid, "<část>", …] (nebo ["ws", wid] pro
// samotný prostor); část (queryKey[2]) určuje, do kterých skupin dotaz patří. Změna nastavení / úloha pak
// zneplatní jen skupiny, kterých se týká (`affected`), místo celého prostoru.
import type { QueryClient, QueryKey } from "@tanstack/react-query";

// guide = stav postupu na záložkách (FEATURE-003): počítá se z dat, modelu, sad a projektu, ne z kritérií optimalizace
export type Group = "data" | "model" | "tuning" | "apc" | "live" | "project" | "guide" | "ws";

export const ALL_GROUPS: readonly Group[] = ["data", "model", "tuning", "apc", "live", "project", "guide", "ws"];

/** Část klíče dotazu → skupiny. Dotaz může patřit do více skupin (bezpečnější víc než míň). */
const PART_GROUPS: Record<string, Group[]> = {
  // data: zdroje, smyčky, signály, kvalita, třídění, úseky
  sources: ["data"], loops: ["data"], "loops-active": ["data"], mappings: ["data"], layout: ["data"],
  preview: ["data"], rawsignals: ["data"], trends: ["data"], spark: ["data"], quality: ["data"],
  dataquality: ["data"], dqsummary: ["data"], datastats: ["data"], triage: ["data"], "tri-thr": ["data"],
  loopsov: ["data", "model", "tuning", "project"], auditloops: ["data"], diag: ["data"],
  loopmode: ["data", "model"], windows: ["data", "model"], grid: ["data", "model"],
  // model: identifikace a ověření
  model: ["model"], modelloop: ["model"], validation: ["model"], curves: ["model"],
  // ladění a simulace
  tuning: ["tuning"], sim: ["tuning"], simulate: ["tuning"], freq: ["tuning"], rob: ["tuning"], plant: ["tuning"],
  scenario: ["tuning"], twarn: ["tuning"], "record-set": ["tuning", "model"],
  // APC, živá simulace, projekt
  apc: ["apc"], live: ["live"],
  "guide-status": ["guide"],                     // stav postupu na záložkách (FEATURE-003)
  batch: ["project"],                            // výsledek hromadné úlohy (FEATURE-007)
  journal: ["project"], "report-sections": ["project"], "save-state": ["project"], guide: ["project"],
  // zpět / znovu (FEATURE-006): popisky kroků se mění po každém zápisu nastavení, sady, úseku i scénáře → ve všech skupinách
  undo: [...ALL_GROUPS],
  // nastavení se zneplatňuje vždy zvlášť (invalidateGroups)
  settings: ["ws"],
};

/** Části s dynamickou příponou za „|“ (např. `validate|…`) – rozhoduje předpona. */
const PREFIX_GROUPS: Record<string, Group[]> = {
  set1check: ["model", "tuning"], validate: ["model"], step: ["model"], compare: ["model"],
};

/** Skupiny dotazu podle klíče; neznámá část = všechny skupiny (dnešní chování, bezpečné). */
export function groupsOfKey(key: QueryKey): readonly Group[] {
  if (key.length < 3) return ["ws"];
  const part = String(key[2]);
  return PART_GROUPS[part] ?? PREFIX_GROUPS[part.split("|")[0] ?? ""] ?? ALL_GROUPS;
}

// Tabulka nastavení → skupiny. Skupina `ws` (samotný ["ws", wid] = WorkspaceInfo: soubor, sloupce, úsek, rozložení)
// se u ladění a simulace nemění, proto ji SIM ani OPT neobsahují; změní ji až identifikace / rozsahy / jazyk.
const SIM: Group[] = ["tuning", "apc", "live", "project", "guide"];
const OPT: Group[] = ["tuning", "live", "project"];   // kritéria optimalizace čte jen výpočet ladění (core.tuning)
const IDENT: Group[] = ["model", "tuning", "apc", "live", "project", "guide", "ws"];
const IDENT_DATA: Group[] = ["data", ...IDENT];      // identifikace, která mění i úseky / režim smyčky

const EXACT: Record<string, readonly Group[]> = {};
const setExact = (keys: string[], groups: readonly Group[]) => { for (const k of keys) EXACT[k] = groups; };

// ladění a simulace (blok PIDConL, sady, kritéria, scénář, simulace, kaskáda)
setExact(["opt_ms", "opt_noise", "opt_robust", "opt_crit", "opt_target", "opt_ovs", "avg_dpv", "avg_dmv"], OPT);
setExact(["samp", "diffgain", "pfb", "propfac", "dfb", "db", "db_mode", "mvl_lo", "mvl_hi", "pvfilt", "mvrate",
  "sprate", "set1_gain", "set1_ti", "set1_td", "set2_gain", "set2_ti", "set2_td", "set2_defined", "ctype",
  "scen_kind",
  "scen_d_in", "scen_d_pv", "scen2", "sim_len_u", "sim_len_u_set", "sim_J", "sim_noise", "vchar_last",
  "cas_src", "cas_k", "cas_t1", "cas_t2", "cas_th", "cas_im", "cas_om", "cas_oct", "cas_samp", "cas_tci",
  "cas_tco"], SIM);
// historie ladění se píše ze serveru; mění jen ladění a projekt
setExact(["tune_hist"], ["tuning", "project", "guide"]);
// identifikace
setExact(["chosen", "mcode", "mtype", "mtype0", "proc_type", "dist_level", "dist_strength", "gain_sign",
  "id_stic", "thmax", "read_manual", "plan_dpv", "plan_snr"], IDENT);
setExact(["win_mode", "id_mode", "val_rng"], IDENT_DATA);
// diagnostika a přehled smyček
setExact(["diag_integ", "diag_theta"], ["data", "model", "project", "guide", "ws"]);
setExact(["audit_loops", "tri_thr"], ["data", "project", "guide", "ws"]);
// rozsahy a jednotky – mění vše
setExact(["pv_lo", "pv_hi", "mv_lo", "mv_hi", "u_pv", "u_mv", "pv_rng_user", "mv_rng_user"], ALL_GROUPS);
// jazyk a název smyčky se promítají všude (texty ze serveru, názvy)
setExact(["lang", "loop_tag"], ALL_GROUPS);
// hlavička protokolu a historie živé simulace
setExact(["rep_plant", "rep_author", "rep_status", "rep_comment"], ["project", "guide", "ws"]);
setExact(["live_runs"], ["live", "project", "guide", "ws"]);
// jen rozhraní: výška grafu čte živá simulace, rozložení prohlížeče a jednotka času server nepoužívá
setExact(["plot_h"], ["live", "ws"]);
setExact(["chart_tunit", "dview", "mview"], ["ws"]);

const PREFIXES: [string, readonly Group[]][] = [
  ["method|", SIM], ["tc|", SIM], ["tend_r|", SIM], ["sim_S|", SIM], ["scen_df|", SIM], ["gs_", SIM],
  ["apc_sm_", SIM],
  ["fx|", IDENT], ["idf|", IDENT], ["ed|", IDENT],
  ["dkind|", IDENT_DATA], ["dsign|", IDENT_DATA], ["dsel|", IDENT_DATA], ["wmode|", IDENT_DATA],
];

function groupsOfSetting(key: string): readonly Group[] {
  const ex = EXACT[key];
  if (ex) return ex;
  for (const [p, g] of PREFIXES) if (key.startsWith(p)) return g;
  return ALL_GROUPS;                     // neznámý klíč = všechny skupiny
}

/** Skupiny dotazů, které změna uvedených klíčů nastavení může ovlivnit. */
export function affected(settingKeys: string[]): Group[] {
  const out = new Set<Group>();
  for (const k of settingKeys) for (const g of groupsOfSetting(k)) out.add(g);
  return ALL_GROUPS.filter((g) => out.has(g));
}

/** Zneplatní dotazy prostoru z uvedených skupin + `settings` (kromě `opts.settings === false`) a vždy `save-state`. */
export function invalidateGroups(qc: QueryClient, wid: string | null, groups: readonly Group[],
  opts: { settings?: boolean } = {}): Promise<void> {
  const want = new Set<Group>(groups);
  return qc.invalidateQueries({
    queryKey: ["ws", wid],
    predicate: (q) => {
      const k = q.queryKey;
      if (k[0] !== "ws" || k[1] !== wid) return false;
      if (k.length >= 3 && k[2] === "save-state") return true;
      if (k.length >= 3 && k[2] === "settings") return opts.settings !== false;
      return groupsOfKey(k).some((g) => want.has(g));
    },
  });
}
