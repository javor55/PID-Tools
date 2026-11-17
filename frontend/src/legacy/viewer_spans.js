/*
 * Vrstva úseků identifikace pro prohlížeč záznamu (viewer.js) – graf záložky Model. Zapíná se jen s D.spans; Trendy
 * ji nepoužívají. Přebírá chování dřívějšího trend.js:
 *   režim "common" – jeden společný úsek (táhla pod panelem s PV, tj. prvním panelem),
 *   režim "inputs" – každý vstup (MV, poruchy) má vlastní úseky; táhla a čipy jsou pod panelem, ve kterém je jeho signál,
 *   tažení táhla = mez, tažení výplně nebo kdekoli na liště = posun nejbližšího úseku, dvojklik na liště = nejbližší
 *   mez se přitáhne na místo kliknutí, čip: čísla začátku a konce, shoda modelu (FIT), přiblížení, odebrání, přidání úseku.
 * Vyloučené části záznamu (excl) jsou šrafované, úseky jsou pásy pod průběhy (vlastní panel vstupu sytěji a s mezemi).
 *
 * D.spans = { mode "common" | "inputs", common [a, b], step (perioda mřížky), unit {u, f}, ccol, cbd, ctx, cbg (barvy společného úseku),
 *   inputs [{id, sig (název signálu v grafu), wins [[a, b]], fits [číslo | null], wcol, wbg, wbd, wtx, badge, note}],
 *   excl [[a, b]], txt {mode, h_mode, common, inputs, zoom_win, win, drag_win, start, end, zoom_one, del, add, excluded} }
 * Ven: component.setStateValue("wins", {mode, wins, common}) po puštění táhla / změně čísla / přidání / odebrání úseku,
 * component.setTriggerValue("mode", "common" | "inputs") při přepnutí režimu (nastavení ukládá React obal).
 */
export default function createSpans(H) {
  "use strict";
  const { el, esc, clamp } = H;
  let Dd = H.D.spans, X = {}, rows = [], last = "";
  const W = { mode: "common", common: [0, 1], wins: {} };

  function load(d) {
    Dd = d; X = d.txt || {}; rows = d.inputs || [];
    W.mode = d.mode === "inputs" ? "inputs" : "common";
    W.common = (d.common || [0, H.D.T]).slice();
    W.wins = {};
    for (const r of rows) W.wins[r.id] = (r.wins || []).map((w) => w.slice());
    last = JSON.stringify(d);
  }
  load(Dd);
  const step = () => Dd.step || 1;
  const snap = (v) => Math.round(v / step()) * step();
  const unit = () => Dd.unit || { u: "s", f: 1 };
  const fmtS = (s) => {                                   // čas v jednotce osy pro políčka
    const v = +(s / unit().f).toFixed(unit().f === 1 ? 0 : 2);
    return H.D.dec === "," ? String(v).replace(".", ",") : String(v);
  };
  const parseS = (txt) => parseFloat(String(txt).replace(",", ".")) * unit().f;

  function send() {
    H.component.setStateValue("wins", JSON.parse(JSON.stringify({ mode: W.mode, wins: W.wins, common: W.common })));
  }

  // ---- komu patří které úseky: společný úsek prvnímu panelu, vstupy panelu s jejich signálem
  function owners(pi) {                                   // [{r | null}] vlastníci lišty v panelu pi
    if (W.mode === "common") return pi === 0 ? [{ r: null }] : [];
    return rows.filter((r) => H.panelOf(r.sig) === pi).map((r) => ({ r }));
  }
  function winsOf(o) {                                    // úseky vlastníka jako {w, col, bd, tx, bg, r, i}
    if (!o.r) return [{ w: W.common, col: Dd.ccol, bd: Dd.cbd, tx: Dd.ctx, bg: Dd.cbg, r: null, i: 0 }];
    return (W.wins[o.r.id] || []).map((w, i) => ({ w, col: o.r.wcol, bd: o.r.wtx, tx: o.r.wtx, bg: o.r.wbg, r: o.r, i }));
  }
  const allWins = () => (W.mode === "common" ? [W.common] : rows.flatMap((r) => W.wins[r.id] || []));
  const label = (x) => (x.r ? `${x.r.id} ${X.win || ""} ${x.i + 1}` : X.common || "");

  // ---- lišta nástrojů: přepínač režimu a přiblížení na úseky
  function barHtml() {
    return `<div class="pidv-grp" data-testid="mw-mode-grp"><span class="pidv-lab">${esc(X.mode || "")}</span>` +
      `<span class="pidv-help" title="${esc(X.h_mode || "")}">?</span>` +
      `<div class="pidv-seg" data-g="wmode" data-testid="mw-mode">` +
      [["common", X.common], ["inputs", X.inputs]].map(([v, t]) =>
        `<button data-v="${v}" class="${v === W.mode ? "on" : ""}">${esc(t || "")}</button>`).join("") + `</div>` +
      `<button class="pidv-btn" data-a="zwin" data-testid="mw-zoom-win">${esc(X.zoom_win || "")}</button></div>`;
  }
  function hookBar(bar) {
    bar.querySelectorAll('[data-g="wmode"] button').forEach((b) => {
      b.onclick = () => { if (b.dataset.v !== W.mode) H.component.setTriggerValue("mode", b.dataset.v); };
    });
    const z = bar.querySelector('[data-a="zwin"]');
    if (z) z.onclick = () => {                             // všechny úseky ±20 %
      const all = allWins();
      if (!all.length) return;
      const a = Math.min(...all.map((w) => w[0])), b = Math.max(...all.map((w) => w[1])), m = 0.2 * (b - a);
      H.setView(Math.max(0, a - m), Math.min(H.D.T, b + m));
    };
  }

  // ---- hlavička panelu: štítek s počtem úseků vstupu
  function header(pi, ph) {
    if (W.mode !== "inputs") return;
    for (const { r } of owners(pi)) {
      if (!r.badge) continue;
      const b = el("span", "pidv-sbadge", esc(r.badge));
      b.style.cssText = `color:${r.wtx};background:${r.wbg};border-color:${r.wbd}`;
      b.dataset.testid = "mw-badge";
      b.setAttribute("data-testid", "mw-badge");
      if (r.note) b.title = r.note;
      ph.appendChild(b);
    }
  }

  // ---- DOM pod panelem: lišta s táhly a čipy s čísly
  function panelExtra(P, before) {
    P.sp = [];
    const own = owners(P.pi);
    if (!own.length) return;
    const wrap = el("div", "pidv-spans");
    wrap.setAttribute("data-testid", "mw-spans");
    own.forEach((o) => {
      const trk = el("div", "pidv-trk");
      trk.setAttribute("data-testid", "mw-track");
      trk.dataset.owner = o.r ? o.r.id : "common";
      const chips = el("div", "pidv-chips");
      chips.setAttribute("data-testid", "mw-chips");
      chips.dataset.owner = o.r ? o.r.id : "common";
      wrap.append(trk, chips);
      const part = { o, trk, chips, key: "" };
      P.sp.push(part);
      trk.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        const k = e.target.dataset ? e.target.dataset.k : undefined, list = winsOf(o);
        let x;
        if (k !== undefined && e.target.dataset.i !== undefined) x = list[+e.target.dataset.i];
        else x = nearestWin(list, tAt(P, trk, e));            // kdekoli na liště: posun nejbližšího úseku
        if (x) startDrag(e, P, x.w, k === undefined ? "move" : k);
      });
      trk.addEventListener("dblclick", (e) => pullLimit(winsOf(o), tAt(P, trk, e)));
    });
    P.c.insertBefore(wrap, before);
  }
  const tAt = (P, node, e) => {
    const rc = node.getBoundingClientRect(), v = H.view();
    return clamp(v[0] + (e.clientX - rc.left - H.L()) / (P.w - H.L() - H.R) * (v[1] - v[0]), 0, H.D.T);
  };

  // pásy pod průběhy (volá drawPanel uvnitř ořezu grafu)
  let pat = null, patDark = null;
  function hatch(g) {
    if (pat && patDark === !!H.D.dark) return pat;
    const c = document.createElement("canvas");
    c.width = c.height = 6;
    const q = c.getContext("2d");
    q.fillStyle = H.col("--pv-hl"); q.fillRect(0, 0, 6, 6);
    q.strokeStyle = "#8a96a3"; q.lineWidth = 2;
    q.beginPath(); q.moveTo(-1, 7); q.lineTo(7, -1); q.moveTo(-1, 1); q.lineTo(1, -1); q.moveTo(5, 7); q.lineTo(7, 5); q.stroke();
    pat = g.createPattern(c, "repeat"); patDark = !!H.D.dark;
    return pat;
  }
  function bands(g, P) {
    const L = H.L(), x1 = P.w - H.R, h = P.h, TOP = H.TOP, BOT = H.BOT;
    const band = (a, b, fill, alpha, stroke) => {
      const xa = H.tx(a, P), xb = H.tx(b, P);
      if (xb < L || xa > x1) return;
      g.globalAlpha = alpha; g.fillStyle = fill;
      g.fillRect(Math.max(L, xa), TOP, Math.max(1, Math.min(x1, xb) - Math.max(L, xa)), h - TOP - BOT);
      g.globalAlpha = 1;
      if (stroke) { g.fillStyle = stroke; for (const x of [xa, xb]) if (x >= L && x <= x1) g.fillRect(x - 0.8, TOP, 1.6, h - TOP - BOT); }
    };
    const own = owners(P.pi);
    if (W.mode === "common") band(W.common[0], W.common[1], Dd.ccol, 0.12, own.length ? Dd.cbd : null);
    else for (const r of rows) {
      const mine = own.some((o) => o.r === r);
      if (own.length && !mine) continue;                    // panel vstupu: jen jeho úseky (sytěji, s mezemi)
      for (const w of W.wins[r.id] || []) band(w[0], w[1], r.wcol, own.length ? 0.28 : 0.13, own.length ? r.wtx : null);
    }
    if ((Dd.excl || []).length) {
      const pt = hatch(g);
      for (const e of Dd.excl) {
        const xa = H.tx(e[0], P), xb = H.tx(e[1], P);
        if (xb < L || xa > x1) continue;
        g.globalAlpha = 0.85; g.fillStyle = pt;
        g.fillRect(Math.max(L, xa), TOP, Math.max(1, Math.min(x1, xb) - Math.max(L, xa)), h - TOP - BOT);
        g.globalAlpha = 1;
      }
    }
  }

  // táhla, výplně, štítky a čipy (po každém překreslení panelu)
  function after(P) {
    for (const part of P.sp || []) { drawTrack(P, part); drawChips(P, part); }
  }
  function drawTrack(P, part) {
    const tr = part.trk, L = H.L(), R = H.R, w = P.w, pw = w - L - R, v = H.view();
    tr.style.width = w + "px";
    tr.innerHTML = `<div class="pidv-rail" style="left:${L}px;width:${pw}px"></div>`;
    const px = (t) => L + (t - v[0]) / (v[1] - v[0]) * pw;
    winsOf(part.o).forEach((x, i) => {
      const x0 = px(x.w[0]), x1 = px(x.w[1]);
      const a = Math.max(L, x0), b = Math.min(L + pw, x1);
      if (b > a) {
        const fill = el("div", "pidv-fill");
        fill.style.cssText = `left:${a}px;width:${Math.max(2, b - a)}px;background:${x.col}`;
        fill.title = X.drag_win || "";
        fill.dataset.i = i; fill.dataset.k = "move";
        tr.appendChild(fill);
        const lab = el("span", "pidv-wlab", esc(label(x)));
        lab.style.cssText = `left:${a}px;color:${x.tx};background:${x.bg};border-color:${x.bd}`;
        lab.dataset.testid = "mw-wlab"; lab.setAttribute("data-testid", "mw-wlab");
        tr.appendChild(lab);
      }
      for (const k of [0, 1]) {
        const xx = k ? x1 : x0;
        if (xx < L - 10 || xx > L + pw + 10) continue;
        const hd = el("button", "pidv-handle");
        hd.type = "button";
        hd.style.cssText = `left:${xx}px;border-color:${x.bd}`;
        hd.dataset.i = i; hd.dataset.k = String(k);
        hd.setAttribute("data-testid", "mw-handle");
        hd.setAttribute("aria-label", `${k ? X.end : X.start} ${i + 1}: ${fmtS(x.w[k])} ${unit().u}`);
        tr.appendChild(hd);
      }
    });
  }
  function drawChips(P, part) {
    const r = part.o.r, list = winsOf(part.o);
    const key = JSON.stringify([W.mode, list.map((x) => x.w), r && r.fits, H.D.dec]);
    if (key === part.key && part.chips.firstChild) return;   // čísla se nemění: nepřestavovat (zachová se zaostření políček)
    part.key = key;
    const ch = part.chips;
    ch.innerHTML = "";
    list.forEach((x) => {
      const wn = x.w, c = el("span", "pidv-chip2");
      c.style.cssText = `background:${x.bg};border-color:${x.bd};color:${x.tx}`;
      c.setAttribute("data-testid", "mw-chip");
      const fv = r && r.fits ? r.fits[x.i] : null;
      const fit = W.mode === "inputs" && fv !== undefined && fv !== null ? ` · FIT ${H.fmtG(fv, 3)} %` : "";
      c.innerHTML = `${esc(x.r ? String(x.i + 1) : X.common || "")} · <input aria-label="${esc(X.start)} ${x.i + 1}" value="${fmtS(wn[0])}">–` +
        `<input aria-label="${esc(X.end)} ${x.i + 1}" value="${fmtS(wn[1])}"> ${esc(unit().u)}${fit} ` +
        `<button type="button" class="pidv-smini" data-a="zoom">${esc(X.zoom_one)}</button>` +
        (W.mode === "inputs" ? `<button type="button" class="pidv-smini" data-a="del" title="${esc(X.del)}" aria-label="${esc(X.del)} ${x.i + 1}">×</button>` : "");
      const [ia, ib] = c.querySelectorAll("input");
      const commit = () => {
        const a = parseS(ia.value), b = parseS(ib.value);
        if (isFinite(a) && isFinite(b) && b - a > step() * 3) {
          wn[0] = clamp(Math.min(a, b), 0, H.D.T);
          wn[1] = clamp(Math.max(a, b), 0, H.D.T);
          H.redraw();
          send();
        } else { ia.value = fmtS(wn[0]); ib.value = fmtS(wn[1]); }
      };
      for (const inp of [ia, ib]) {
        inp.onchange = commit;
        inp.onkeydown = (e) => { if (e.key === "Enter") inp.blur(); };
      }
      c.querySelector('[data-a="zoom"]').onclick = () => {
        const m = 0.2 * (wn[1] - wn[0]);
        H.setView(Math.max(0, wn[0] - m), Math.min(H.D.T, wn[1] + m));
      };
      const del = c.querySelector('[data-a="del"]');
      if (del) del.onclick = () => { const Ls = W.wins[r.id]; Ls.splice(Ls.indexOf(wn), 1); part.key = ""; H.redraw(); send(); };
      ch.appendChild(c);
    });
    if (W.mode === "inputs" && r) {
      const add = el("button", "pidv-sadd", esc((X.add || "+").replace("{n}", r.id)));
      add.type = "button";
      add.setAttribute("data-testid", "mw-add");
      add.onclick = () => {                               // nový úsek uprostřed zobrazeného rozsahu (20 % šířky)
        const v = H.view(), Ln = 0.2 * (v[1] - v[0]), m = (v[0] + v[1]) / 2;
        W.wins[r.id].push([snap(Math.max(0, m - Ln / 2)), snap(Math.min(H.D.T, m + Ln / 2))]);
        part.key = ""; H.redraw(); send();
      };
      ch.appendChild(add);
    }
  }

  // ---- tažení: posluchače na okně jen během tažení (táhla se při kreslení obnovují)
  function startDrag(ev, P, wn, k) {
    ev.preventDefault();
    ev.stopPropagation();
    let last_ = ev.clientX, moved = false;
    const T = H.D.T, d3 = step() * 3;
    const move = (e) => {
      const v = H.view(), dt = (e.clientX - last_) / (P.w - H.L() - H.R) * (v[1] - v[0]);
      if (!moved && Math.abs(e.clientX - ev.clientX) < 3) return;   // klik / dvojklik bez pohybu
      moved = true;
      last_ = e.clientX;
      if (k === "move") { const Ln = wn[1] - wn[0]; wn[0] = clamp(wn[0] + dt, 0, T - Ln); wn[1] = wn[0] + Ln; }
      else if (k === "1") wn[1] = clamp(wn[1] + dt, wn[0] + d3, T);
      else wn[0] = clamp(wn[0] + dt, 0, wn[1] - d3);
      H.redraw();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (!moved) return;
      const Ln = wn[1] - wn[0];
      wn[0] = snap(wn[0]);
      wn[1] = k === "move" ? wn[0] + snap(Ln) : snap(wn[1]);
      for (const pt of H.panels().flatMap((q) => q.sp || [])) pt.key = "";
      H.redraw();
      send();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }
  function nearestWin(list, t) {                           // úsek nejblíž k času t
    let best = null, bd = Infinity;
    for (const x of list) {
      const d = t < x.w[0] ? x.w[0] - t : t > x.w[1] ? t - x.w[1] : 0;
      if (d < bd) { bd = d; best = x; }
    }
    return best;
  }
  function pullLimit(list, t) {                            // dvojklik: nejbližší mez úseku na místo kliknutí
    let best = null, bk = 0, bd = Infinity;
    for (const x of list) for (const k of [0, 1]) {
      const d = Math.abs(x.w[k] - t);
      if (d < bd) { bd = d; best = x.w; bk = k; }
    }
    if (!best) return;
    t = snap(clamp(t, 0, H.D.T));
    if (bk === 0) best[0] = Math.min(t, best[1] - step() * 3);
    else best[1] = Math.max(t, best[0] + step() * 3);
    for (const pt of H.panels().flatMap((q) => q.sp || [])) pt.key = "";
    H.redraw();
    send();
  }

  // ---- nová data ze serveru (režim, úseky, shoda): beze změny se nic neděje
  function update(d) {
    const j = JSON.stringify(d);
    if (j === last) return;
    const old = W.mode;
    load(d);
    if (old !== W.mode) H.rebuild();                       // jiná lišta a vlastníci lišt
    else { for (const P of H.panels()) for (const pt of P.sp || []) pt.key = ""; H.redraw(); }
  }

  return { barHtml, hookBar, header, panelExtra, bands, after, update };
}
