/*
 * Přepínače průběhu modelu pro prohlížeč záznamu (viewer.js) – graf záložky Model (identifikace). Zapíná se jen s D.model;
 * Trendy ji nepoužívají. Průběhy modelu jsou obyčejné signály grafu (kurzory, tabulka a export CSV je zahrnují);
 * přepínače jen mění, které z nich jsou v panelu s PV – stav se tedy čte z rozložení panelů (a ukládá s ním), takže signál
 * přidaný nebo odebraný ručně v seznamu signálů přepínače správně odráží.
 *
 * D.model = { pv (signál PV), all (celý model na celém záznamu), win (celý model jen v úsecích), mv, dv (části modelu),
 *   resid (rezidua), txt {m_all, m_mv, m_dv, r_win, r_full, resid} }
 *   část: all = celý model (MV + poruchy) · mv = jen MV · dv = jen poruchy; rozsah: full = celý záznam · win = jen úseky.
 */
export default function createModel(H) {
  "use strict";
  const M = H.D.model, X = M.txt || {}, { esc } = H;
  let range = "full";                                      // rozsah, když zrovna není zobrazen celý model
  const has = (n) => !!n && !!H.SG[n];
  const parts = () => [["all", X.m_all, true], ["mv", X.m_mv, has(M.mv)], ["dv", X.m_dv, has(M.dv)]].filter((q) => q[2]);
  const inPv = (n) => { const pi = H.panelOf(M.pv); return pi >= 0 && !!n && H.S().panels[pi].sigs.includes(n); };
  function state() {
    const part = inPv(M.mv) ? "mv" : inPv(M.dv) ? "dv" : "all";
    if (inPv(M.win)) range = "win"; else if (inPv(M.all)) range = "full";
    return { part, range, resid: H.panelOf(M.resid) >= 0 };
  }
  // part: "all" = vše v jedné skupině (Trendy / nekompaktní graf), "main" = jen reziduum (řádek kompaktního grafu),
  // "tools" = části a rozsah modelu (sbalitelný panel)
  function barHtml(part) {
    const st = state();
    const seg = (g, items, cur) => `<div class="pidv-seg" data-g="${g}">` + items.map(([v, t]) =>
      `<button data-v="${v}" class="${v === cur ? "on" : ""}">${esc(t || "")}</button>`).join("") + `</div>`;
    const segs = seg("mpart", parts().map(([v, t]) => [v, t]), st.part) + (has(M.win) ? seg("mrange", [["win", X.r_win], ["full", X.r_full]], st.range) : "");
    const res = has(M.resid) ? `<label class="pidv-chk2"><input type="checkbox" data-a="resid" data-testid="mw-resid" ${st.resid ? "checked" : ""}> ${esc(X.resid || "")}</label>` : "";
    if (part === "main") return res ? `<div class="pidv-grp">${res}</div>` : "";
    if (part === "tools") return `<div class="pidv-grp" data-testid="mw-model">${segs}</div>`;
    return `<div class="pidv-grp" data-testid="mw-model">${segs}${res}</div>`;
  }
  // přepíše členství modelových signálů v panelu s PV a (ne)zobrazí panel reziduí
  function apply(part, rng, resid) {
    const S = H.S();
    if (H.panelOf(M.pv) < 0) return;
    range = rng;
    for (const n of [M.all, M.win, M.mv, M.dv]) if (has(n)) H.removeSig(n);
    const pj = H.panelOf(M.pv);
    const target = part === "mv" ? M.mv : part === "dv" ? M.dv : (rng === "win" && has(M.win) ? M.win : M.all);
    if (has(target) && pj >= 0) S.panels[pj].sigs.push(target);
    if (has(M.resid)) {
      H.removeSig(M.resid);
      if (resid) S.panels.push({ sigs: [M.resid], h: 100, shared: false, lo: null, hi: null });
    }
    H.rebuild();
  }
  function hookBar(bar) {
    const g = bar;                                         // skupiny modelu mohou být v řádku i ve sbalitelném panelu
    g.querySelectorAll('[data-g="mpart"] button').forEach((b) => { b.onclick = () => { const s = state(); apply(b.dataset.v, s.range, s.resid); }; });
    g.querySelectorAll('[data-g="mrange"] button').forEach((b) => { b.onclick = () => { const s = state(); apply(s.part, b.dataset.v, s.resid); }; });
    const c = g.querySelector('[data-a="resid"]');
    if (c) c.onchange = () => { const s = state(); apply(s.part, s.range, c.checked); };
  }
  return { barHtml, hookBar };
}
