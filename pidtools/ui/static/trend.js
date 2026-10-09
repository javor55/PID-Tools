/*
 * Graf průběhů – jedna komponenta pro celou aplikaci (Data, Model, Diagnostika). Běží přímo na stránce
 * (st.components.v2). Karty pod sebou se společnou časovou osou: kolečko = zoom, tažení v grafu = posun,
 * najetí myší = hodnoty. Volitelně úseky s táhly:
 *   mode "view"    – jen průběhy (Data),
 *   "common"       – jeden společný úsek (táhla pod první kartou),
 *   "inputs"       – každý vstup (karta kind "in") má vlastní úseky (Model),
 *   "ab"           – úsek A a volitelně B pro srovnání (Diagnostika).
 * Úseky: tažení táhla = mez, tažení výplně nebo kdekoli na liště = posun celého úseku, dvojklik v grafu
 * nebo na liště = nejbližší mez úseku se přitáhne na místo kliknutí.
 *
 * Data z Pythonu (component.data):
 *   key, sig (otisk dat – stejný otisk = nic se nepřekresluje), mode, t [s], T, step, unit {u, f}, clock (ms epochy
 *   pro t = 0 nebo null), dec, dark, bar {mode_switch, zoom, legend: [[barva, text, styl]]},
 *   rows: [{id, kind "pv" | "in" | "sig", title, badge, note, color, y, lo, hi, h, lines [[y, barva, čárkování,
 *          tloušťka, název]], wins, fits, wcol, wbg, wbd, wtx, model {all, mv, dv, full}, resid}],
 *   excl [[a, b]], common [a, b], ab {a: [a, b], b: [a, b] | null, ca, cb, la, lb}, txt {…}
 * Do Pythonu: stav „wins“ = {mode, wins, common, ab} (po puštění táhla / změně čísla), trigger „mode“.
 */
export default function (component) {
  "use strict";
  const D = component.data, root = component.parentElement, X = D.txt || {};
  const reg = (window.__pidTrend = window.__pidTrend || {});
  const prev = reg[D.key];
  // stejná data jako minule a graf je pořád na stránce → nic nedělat (rychlé běhy aplikace)
  if (prev && prev.sig === D.sig && prev.box && prev.box.isConnected && root.contains(prev.box)) return;
  root.querySelectorAll(".pidw").forEach((n) => n.remove());
  if (prev && prev.ro) prev.ro.disconnect();             // sledování velikosti starého grafu pryč
  if (prev && prev.box && prev.box.isConnected) prev.box.remove();

  const views = (window.__pidTrendView = window.__pidTrendView || {});
  const S = (views[D.view_key] = views[D.view_key] || { view: [0, D.T], model: "all", resid: false, onlyWin: true });
  if (!(S.view[1] > S.view[0]) || S.view[1] > D.T * 1.0001) S.view = [0, D.T];
  const W = { mode: D.mode, wins: {}, common: (D.common || [0, D.T]).slice(),
              ab: D.ab ? { a: D.ab.a.slice(), b: D.ab.b ? D.ab.b.slice() : null } : null };
  for (const r of D.rows) if (r.kind === "in") W.wins[r.id] = (r.wins || []).map((w) => w.slice());

  const fmtN = (v, d) => {
    if (v === null || v === undefined || !isFinite(v)) return "–";
    const s = Math.abs(v) >= 1000 ? v.toFixed(0) : String(+v.toPrecision(d || 4));
    return D.dec === "," ? s.replace(".", ",") : s;
  };
  const pad2 = (n) => String(n).padStart(2, "0");
  const clockStr = (s, full) => {                       // absolutní čas (hodiny:minuty), v tipu i datum
    const d = new Date(D.clock + s * 1000);
    const hm = `${d.getHours()}:${pad2(d.getMinutes())}` + (full || (S.view[1] - S.view[0]) < 600 ? `:${pad2(d.getSeconds())}` : "");
    return full ? `${d.getDate()}.${d.getMonth() + 1}. ${hm}` : hm;
  };
  const fmtS = (s) => {                                   // čas v jednotce osy (s / min / h) pro políčka
    const v = +(s / D.unit.f).toFixed(D.unit.f === 1 ? 0 : 2);
    return D.dec === "," ? String(v).replace(".", ",") : String(v);
  };
  const parseS = (txt) => parseFloat(String(txt).replace(",", ".")) * D.unit.f;
  const el = (tag, cls, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const snap = (v) => Math.round(v / D.step) * D.step;
  const editable = D.mode !== "view";

  function send() {
    component.setStateValue("wins", { mode: W.mode, wins: W.wins, common: W.common, ab: W.ab });
  }

  // ---------------------------------------------------------------- kostra
  const box = el("div", "pidw" + (D.dark ? " dark" : ""));
  root.appendChild(box);
  reg[D.key] = { sig: D.sig, box };

  const B = D.bar || {};
  if (B.title || B.mode_switch || B.zoom || (B.legend && B.legend.length)) {
    const bar = el("div", "pidw-card pidw-bar");
    let h = B.title ? `<div class="pidw-grp"><h2 class="pidw-title">${esc(B.title)}</h2>` +
      (B.note ? `<span class="pidw-note">${esc(B.note)}</span>` : "") + `</div>` : "";
    if (B.mode_switch)
      h += `<div class="pidw-grp"><span class="pidw-lab">${esc(X.mode)}</span>` +
        `<span class="pidw-help" title="${esc(X.h_mode)}">?</span>` +
        `<div class="pidw-seg" data-g="mode"><button data-v="common">${esc(X.common)}</button>` +
        `<button data-v="inputs">${esc(X.inputs)}</button></div></div>`;
    if (B.zoom)
      h += `<div class="pidw-grp"><span class="pidw-lab">${esc(X.zoom)}</span>` +
        `<div class="pidw-seg" data-g="zoom"><button data-v="all">${esc(X.zoom_all)}</button>` +
        (editable ? `<button data-v="win">${esc(X.zoom_win)}</button>` : "") + `</div>` +
        `<span class="pidw-note">${esc(X.zoom_note)}</span></div>`;
    h += `<div class="pidw-leg">${(B.legend || []).map(([c, t, st]) =>
      st === "hatch" ? `<span><i class="pidw-hatch"></i>${esc(t)}</span>`
        : st === "line" ? `<span><i class="pidw-ln" style="border-top-color:${c}"></i>${esc(t)}</span>`
          : `<span><i style="background:${st || "transparent"};border-color:${c}"></i>${esc(t)}</span>`).join("")}</div>`;
    bar.innerHTML = h;
    box.appendChild(bar);
    bar.querySelectorAll('[data-g="mode"] button').forEach((b) => {
      b.classList.toggle("on", b.dataset.v === W.mode);
      b.onclick = () => { if (b.dataset.v !== W.mode) component.setTriggerValue("mode", b.dataset.v); };
    });
    const za = bar.querySelector('[data-v="all"]');
    if (za) za.onclick = () => { S.view = [0, D.T]; draw(); };
    const zw = bar.querySelector('[data-v="win"]');
    if (zw) zw.onclick = () => {
      const all = winsFor(null).map((x) => x.w);
      if (!all.length) return;
      const a = Math.min(...all.map((w) => w[0])), b = Math.max(...all.map((w) => w[1])), m = 0.2 * (b - a);
      S.view = [Math.max(0, a - m), Math.min(D.T, b + m)];
      draw();
    };
  }

  // úseky, které patří ke kartě (pro táhla a dvojklik); null = všechny
  function winsFor(card) {
    const out = [];
    if (W.mode === "common") out.push({ w: W.common, col: "#f59e0b", bd: "#c77d00" });
    else if (W.mode === "ab") {
      out.push({ w: W.ab.a, col: D.ab.ca, bd: D.ab.ca, lab: D.ab.la });
      if (W.ab.b) out.push({ w: W.ab.b, col: D.ab.cb, bd: D.ab.cb, lab: D.ab.lb });
    } else if (W.mode === "inputs") {
      for (const r of D.rows) {
        if (r.kind !== "in" || (card && card.r.id !== r.id)) continue;
        for (const w of W.wins[r.id]) out.push({ w, col: r.wcol, bd: r.wtx, id: r.id });
      }
    }
    return out;
  }
  const trackCard = (r, ri) => editable && ((W.mode === "inputs" && r.kind === "in") || (W.mode !== "inputs" && ri === 0));

  // karty grafů
  const cards = [];
  D.rows.forEach((r, ri) => {
    const c = el("section", "pidw-card");
    const head = el("div", "pidw-head");
    head.innerHTML = `<h2>${esc(r.title)}</h2>` + (r.badge ? `<span class="pidw-badge" style="color:${r.wtx};` +
      `background:${r.wbg};border-color:${r.wbd}">${esc(r.badge)}</span>` : "") +
      (r.note ? `<span class="pidw-note">${esc(r.note)}</span>` : "");
    if (r.kind === "pv" && r.model) {
      const g = el("div", "pidw-seg pidw-model");
      for (const [k, lab] of [["all", X.m_all], ["mv", X.m_mv], ["dv", X.m_dv]]) {
        if (k !== "all" && !r.model[k]) continue;
        const b = el("button", "", esc(lab));
        b.dataset.v = k;
        b.onclick = () => { S.model = k; draw(); };
        g.appendChild(b);
      }
      head.appendChild(g);
      const c1 = el("label", "pidw-chk", `<input type="checkbox"> ${esc(X.resid)}`);
      c1.querySelector("input").onchange = (e) => { S.resid = e.target.checked; draw(); };
      const c2 = el("label", "pidw-chk", `<input type="checkbox"> ${esc(X.only_win)}`);
      c2.querySelector("input").onchange = (e) => { S.onlyWin = e.target.checked; draw(); };
      head.append(c1, c2);
    }
    const leg = [[r.color, r.id]].concat((r.lines || []).filter((l) => l[4]).map((l) => [l[1], l[4], l[2]]));
    if (r.kind === "pv" && r.model) leg.push(["#5b3fa8", X.model, "6 4"]);
    if (leg.length > 1)
      head.appendChild(el("span", "pidw-leg2", leg.map(([col, nm, dash]) =>
        `<span><i style="border-top:2px ${dash ? "dashed" : "solid"} ${col}"></i>${esc(nm)}</span>`).join("")));
    c.appendChild(head);
    const plot = el("div", "pidw-plot");
    const ax = el("div", "pidw-yax");
    const area = el("div", "pidw-area");
    area.style.height = r.h + "px";
    ax.style.height = r.h + "px";
    plot.append(ax, area);
    c.appendChild(plot);
    let resid = null;
    if (r.kind === "pv" && r.resid) {
      resid = el("div", "pidw-plot pidw-resid");
      const rax = el("div", "pidw-yax"), rarea = el("div", "pidw-area");
      rax.style.height = rarea.style.height = "70px";
      resid.append(rax, rarea);
      c.appendChild(resid);
    }
    const xax = el("div", "pidw-plot");                  // časová osa pod každým grafem
    xax.append(el("span"), el("div", "pidw-xax"));
    c.appendChild(xax);
    let track = null, chips = null;
    if (trackCard(r, ri)) {
      track = el("div", "pidw-plot pidw-trackrow");
      track.append(el("span"), el("div", "pidw-track"));
      c.appendChild(track);
      chips = el("div", "pidw-chips");
      c.appendChild(chips);
    }
    box.appendChild(c);
    cards.push({ r, c, ax, area, resid, track, chips, xax, head });
  });
  const tip = el("div", "pidw-tip");
  box.appendChild(tip);

  // ---------------------------------------------------------------- kreslení
  const NS = "http://www.w3.org/2000/svg";
  const tx = (t, w) => (t - S.view[0]) / (S.view[1] - S.view[0]) * w;
  const ty = (y, lo, hi, h) => h - (y - lo) / (hi - lo) * h;
  function path(xs, ys, w, h, lo, hi) {
    let d = "", pen = false;
    const a = S.view[0], b = S.view[1];
    let i0 = 0, i1 = xs.length - 1;
    while (i0 < i1 && xs[i0 + 1] < a) i0++;
    while (i1 > i0 && xs[i1 - 1] > b) i1--;
    const stride = Math.max(1, Math.floor((i1 - i0) / (2 * w)));
    for (let i = i0; i <= i1; i += stride) {
      const y = ys[i];
      if (y === null || !isFinite(y)) { pen = false; continue; }
      d += (pen ? "L" : "M") + tx(xs[i], w).toFixed(1) + "," + ty(y, lo, hi, h).toFixed(1);
      pen = true;
    }
    return d;
  }
  function nice(span, n) {
    const raw = span / n, e = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * e >= raw) return m * e;
    return 10 * e;
  }
  function yTicks(ax, lo, hi, h) {
    ax.innerHTML = "";
    const st = nice(hi - lo, h < 120 ? 2 : 4);
    for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) {
      const s = el("span", "", fmtN(+v.toPrecision(8), 4));
      s.style.top = (ty(v, lo, hi, h) / h * 100) + "%";
      ax.appendChild(s);
    }
  }
  function svgEl(tag, attrs) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function band(svg, a, b, w, h, fill, op, stroke) {
    const x0 = tx(a, w), x1 = tx(b, w);
    if (x1 < 0 || x0 > w) return;
    svg.appendChild(svgEl("rect", { x: Math.max(0, x0), y: 0, width: Math.max(1, Math.min(w, x1) - Math.max(0, x0)), height: h,
      fill, "fill-opacity": op }));
    if (stroke) for (const x of [x0, x1]) if (x >= 0 && x <= w)
      svg.appendChild(svgEl("rect", { x: x - 0.8, y: 0, width: 1.6, height: h, fill: stroke }));
  }
  function drawArea(card, area, lo, hi, opts) {
    const w = area.clientWidth || 600, h = area.clientHeight || 100;
    area.innerHTML = "";
    const svg = svgEl("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}` });
    const pid = "pidwh" + Math.random().toString(36).slice(2, 7);
    const defs = svgEl("defs", {});
    const pat = svgEl("pattern", { id: pid, width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
    pat.append(svgEl("rect", { width: 6, height: 6, fill: "var(--pidw-hbg)" }), svgEl("rect", { width: 2, height: 6, fill: "#8a96a3" }));
    defs.appendChild(pat);
    svg.appendChild(defs);
    const st = nice(hi - lo, h < 120 ? 2 : 4);
    for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st)
      svg.appendChild(svgEl("line", { x1: 0, x2: w, y1: ty(v, lo, hi, h), y2: ty(v, lo, hi, h), stroke: "var(--pidw-grid)" }));
    // úseky: společné / A, B ve všech grafech; podle vstupů všechny v PV, vlastní v grafu vstupu
    if (W.mode === "common" || W.mode === "ab") for (const x of winsFor(null)) band(svg, x.w[0], x.w[1], w, h, x.col, 0.12, opts.own ? x.bd : null);
    else if (W.mode === "inputs") for (const rr of D.rows) {
      if (rr.kind !== "in") continue;
      if (card.r.kind === "in" && rr.id !== card.r.id) continue;
      for (const wn of W.wins[rr.id]) band(svg, wn[0], wn[1], w, h, rr.wcol, card.r.kind === "in" ? 0.28 : 0.13, card.r.kind === "in" ? rr.wtx : null);
    }
    for (const e of D.excl || []) band(svg, e[0], e[1], w, h, `url(#${pid})`, 0.85);
    for (const [arr, col, dash, sw] of opts.lines) {
      if (!arr) continue;
      const p = svgEl("path", { d: path(D.t, arr, w, h, lo, hi), fill: "none", stroke: col, "stroke-width": sw || 1.8 });
      if (dash) p.setAttribute("stroke-dasharray", dash);
      svg.appendChild(p);
    }
    area.appendChild(svg);
    // popisky úseků
    if (opts.labels) winsFor(card).forEach((x, i) => {
      const xx = tx(x.w[0], w);
      if (xx < 0 || xx > w) return;
      const r = card.r;
      const txt = x.lab || `${r.id} ${X.win || ""} ${i + 1}`;
      const l = el("span", "pidw-wlab", esc(txt));
      l.style.cssText = W.mode === "inputs" ? `left:${xx}px;color:${r.wtx};background:${r.wbg};border-color:${r.wbd}`
        : `left:${xx}px;color:${x.bd};background:var(--pidw-card);border-color:${x.bd}`;
      area.appendChild(l);
    });
  }
  function drawTrack(card) {
    const tr = card.track.querySelector(".pidw-track");
    tr.innerHTML = '<div class="pidw-rail"></div>';
    const w = tr.clientWidth || 600;
    winsFor(card).forEach((x, i) => {
      const wn = x.w, x0 = tx(wn[0], w), x1 = tx(wn[1], w);
      const fill = el("div", "pidw-fill");
      fill.style.cssText = `left:${Math.max(0, x0)}px;width:${Math.max(2, Math.min(w, x1) - Math.max(0, x0))}px;background:${x.col}`;
      fill.title = X.drag_win || "";
      fill.dataset.i = i;
      fill.dataset.k = "move";
      tr.appendChild(fill);
      for (const k of [0, 1]) {
        const xx = k ? x1 : x0;
        if (xx < -10 || xx > w + 10) continue;
        const hd = el("button", "pidw-handle");
        hd.type = "button";
        hd.style.cssText = `left:${xx}px;border-color:${x.bd}`;
        hd.dataset.i = i;
        hd.dataset.k = String(k);
        hd.setAttribute("aria-label", `${k ? X.end : X.start} ${i + 1}: ${fmtS(wn[k])} ${D.unit.u}`);
        tr.appendChild(hd);
      }
    });
  }
  function drawChips(card) {
    const r = card.r, ch = card.chips;
    ch.innerHTML = "";
    winsFor(card).forEach((x, i) => {
      const wn = x.w, c = el("span", "pidw-chip");
      c.style.cssText = W.mode === "inputs" ? `background:${r.wbg};border-color:${r.wbd};color:${r.wtx}`
        : `background:var(--pidw-card);border-color:${x.bd};color:${x.bd}`;
      const fit = W.mode === "inputs" && r.fits && r.fits[i] !== undefined && r.fits[i] !== null ? ` · FIT ${fmtN(r.fits[i], 3)} %` : "";
      c.innerHTML = `${esc(x.lab || String(i + 1))} · <input aria-label="${esc(X.start)} ${i + 1}" value="${fmtS(wn[0])}">–` +
        `<input aria-label="${esc(X.end)} ${i + 1}" value="${fmtS(wn[1])}"> ${esc(D.unit.u)}${fit} ` +
        `<button type="button" class="pidw-mini" data-a="zoom">${esc(X.zoom_one)}</button>` +
        (W.mode === "inputs" ? `<button type="button" class="pidw-mini" data-a="del" title="${esc(X.del)}">×</button>` : "");
      const [ia, ib] = c.querySelectorAll("input");
      const commit = () => {
        const a = parseS(ia.value), b = parseS(ib.value);
        if (isFinite(a) && isFinite(b) && b - a > D.step * 3) {
          wn[0] = clamp(Math.min(a, b), 0, D.T);
          wn[1] = clamp(Math.max(a, b), 0, D.T);
          draw();
          send();
        } else { ia.value = fmtS(wn[0]); ib.value = fmtS(wn[1]); }
      };
      for (const inp of [ia, ib]) {
        inp.onchange = commit;
        inp.onkeydown = (e) => { if (e.key === "Enter") inp.blur(); };
      }
      c.querySelector('[data-a="zoom"]').onclick = () => {
        const m = 0.2 * (wn[1] - wn[0]);
        S.view = [Math.max(0, wn[0] - m), Math.min(D.T, wn[1] + m)];
        draw();
      };
      const del = c.querySelector('[data-a="del"]');
      if (del) del.onclick = () => { const L = W.wins[r.id]; L.splice(L.indexOf(wn), 1); draw(); send(); };
      ch.appendChild(c);
    });
    if (W.mode === "inputs") {
      const add = el("button", "pidw-add", esc((X.add || "+").replace("{n}", r.id)));
      add.type = "button";
      add.onclick = () => {                          // nový úsek uprostřed zobrazeného rozsahu (20 % šířky)
        const L = 0.2 * (S.view[1] - S.view[0]), m = (S.view[0] + S.view[1]) / 2;
        W.wins[r.id].push([snap(Math.max(0, m - L / 2)), snap(Math.min(D.T, m + L / 2))]);
        draw();
        send();
      };
      ch.appendChild(add);
    }
  }
  function drawX(card) {
    const xa = card.xax.querySelector(".pidw-xax");
    xa.innerHTML = "";
    const w = xa.clientWidth || 600;
    if (D.clock) {                                     // hodiny: hezké kroky 1 min … 1 den
      const steps = [60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
      const span = S.view[1] - S.view[0], st = steps.find((s) => span / s <= 7) || 86400;
      const off = ((D.clock / 1000) % st + st) % st;   // zarovnání na celé minuty / hodiny místního času
      const tz = -new Date(D.clock).getTimezoneOffset() * 60;
      for (let v = Math.ceil((S.view[0] + off + tz) / st) * st - off - tz; v <= S.view[1]; v += st) {
        const x = tx(v, w);
        if (x < 0 || x > w - 30) continue;
        const s = el("span", "", clockStr(v));
        s.style.left = x + "px";
        xa.appendChild(s);
      }
      return;
    }
    const span = (S.view[1] - S.view[0]) / D.unit.f, st = nice(span, 7);
    for (let v = Math.ceil(S.view[0] / D.unit.f / st) * st; v <= S.view[1] / D.unit.f + 1e-9; v += st) {
      const x = tx(v * D.unit.f, w);
      if (x > w - 50) continue;                       // vpravo je jednotka osy
      const s = el("span", "", fmtN(+v.toPrecision(6), 6));
      s.style.left = x + "px";
      xa.appendChild(s);
    }
    xa.appendChild(el("span", "pidw-xu", esc(D.unit.u)));
  }
  function draw() {
    for (const card of cards) {
      const r = card.r;
      card.head.querySelectorAll(".pidw-model button").forEach((b) => b.classList.toggle("on", b.dataset.v === S.model));
      card.head.querySelectorAll(".pidw-chk input").forEach((inp, k) => { inp.checked = k ? S.onlyWin : S.resid; });
      yTicks(card.ax, r.lo, r.hi, r.h);
      const lines = (r.lines || []).map((l) => [l[0], l[1], l[2], l[3] || 1.4]).concat([[r.y, r.color, null, 1.8]]);
      if (r.kind === "pv" && r.model) {
        const m = S.onlyWin ? r.model[S.model] : (r.model.full && S.model === "all" ? r.model.full : r.model[S.model]);
        lines.push([m, "#5b3fa8", "6 4", 2.4]);
      }
      drawArea(card, card.area, r.lo, r.hi, { own: !!card.track, labels: !!card.track, lines });
      if (card.resid) {
        card.resid.style.display = S.resid ? "" : "none";
        if (S.resid) {
          const ra = card.resid.querySelector(".pidw-area"), rx = card.resid.querySelector(".pidw-yax");
          const v = r.resid.filter((q) => q !== null && isFinite(q));
          const m = Math.max(1e-9, ...v.map(Math.abs));
          yTicks(rx, -m, m, 70);
          drawArea(card, ra, -m * 1.1, m * 1.1, { own: false, labels: false, lines: [[r.resid, "#5b3fa8", null, 1.4]] });
        }
      }
      drawX(card);
      if (card.track) { drawTrack(card); drawChips(card); }
    }
  }

  // ---------------------------------------------------------------- táhla a úseky
  // Tažení: posluchače na okně (táhla se při kreslení obnovují – zachycení na prvku by se ztratilo).
  function startDrag(ev, card, wn, k, w) {
    ev.preventDefault();
    ev.stopPropagation();
    let last = ev.clientX, moved = false;
    const move = (e) => {
      const dt = (e.clientX - last) / w * (S.view[1] - S.view[0]);
      if (!moved && Math.abs(e.clientX - ev.clientX) < 3) return;   // klik / dvojklik bez pohybu
      moved = true;
      last = e.clientX;
      if (k === "move") { const L = wn[1] - wn[0]; wn[0] = clamp(wn[0] + dt, 0, D.T - L); wn[1] = wn[0] + L; }
      else if (k === "1") wn[1] = clamp(wn[1] + dt, wn[0] + D.step * 3, D.T);
      else wn[0] = clamp(wn[0] + dt, 0, wn[1] - D.step * 3);
      draw();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (!moved) return;
      const L = wn[1] - wn[0];
      wn[0] = snap(wn[0]);
      wn[1] = k === "move" ? wn[0] + snap(L) : snap(wn[1]);
      draw();
      send();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }
  function nearestWin(card, t) {                       // úsek, jehož střed je nejblíž
    let best = null, bd = Infinity;
    for (const x of winsFor(card)) {
      const d = t < x.w[0] ? x.w[0] - t : t > x.w[1] ? t - x.w[1] : 0;
      if (d < bd) { bd = d; best = x.w; }
    }
    return best;
  }
  function pullLimit(card, t) {                         // dvojklik: nejbližší mez úseku na místo kliknutí
    let best = null, bk = 0, bd = Infinity;
    for (const x of winsFor(card)) for (const k of [0, 1]) {
      const d = Math.abs(x.w[k] - t);
      if (d < bd) { bd = d; best = x.w; bk = k; }
    }
    if (!best) return;
    t = snap(clamp(t, 0, D.T));
    if (bk === 0) best[0] = Math.min(t, best[1] - D.step * 3);
    else best[1] = Math.max(t, best[0] + D.step * 3);
    draw();
    send();
  }
  const tAt = (node, e) => { const rc = node.getBoundingClientRect(); return S.view[0] + (e.clientX - rc.left) / rc.width * (S.view[1] - S.view[0]); };
  for (const card of cards) {
    if (!card.track) continue;
    const tr = card.track.querySelector(".pidw-track");
    tr.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const w = tr.clientWidth || 600, k = e.target.dataset ? e.target.dataset.k : undefined;
      const list = winsFor(card);
      let wn;
      if (k !== undefined && e.target.dataset.i !== undefined) wn = list[+e.target.dataset.i] && list[+e.target.dataset.i].w;
      else wn = nearestWin(card, tAt(tr, e));          // kdekoli na liště: posun nejbližšího úseku
      if (wn) startDrag(e, card, wn, k === undefined ? "move" : k, w);
    });
    tr.addEventListener("dblclick", (e) => pullLimit(card, tAt(tr, e)));
  }

  // ---------------------------------------------------------------- zoom, posun, hodnoty
  for (const card of cards) {
    const a = card.area;
    a.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = a.getBoundingClientRect(), f = (e.clientX - rect.left) / rect.width;
      const t0 = S.view[0] + f * (S.view[1] - S.view[0]);
      const k = e.deltaY > 0 ? 1.25 : 0.8;
      let L = (S.view[1] - S.view[0]) * k;
      L = clamp(L, D.step * 20, D.T);
      const v0 = clamp(t0 - f * L, 0, D.T - L);
      S.view = [v0, v0 + L];
      draw();
    }, { passive: false });
    a.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      let last = e.clientX;
      const w = a.clientWidth;
      const move = (ev) => {
        const L = S.view[1] - S.view[0], dt = -(ev.clientX - last) / w * L;
        last = ev.clientX;
        const v0 = clamp(S.view[0] + dt, 0, D.T - L);
        S.view = [v0, v0 + L];
        draw();
      };
      const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
    if (editable && (card.track || W.mode !== "inputs" || card.r.kind === "in"))
      a.addEventListener("dblclick", (e) => pullLimit(card.track ? card : (card.r.kind === "in" ? card : cards.find((c) => c.track) || card), tAt(a, e)));
    a.addEventListener("mousemove", (e) => {
      const t = tAt(a, e);
      let lo = 0, hi = D.t.length - 1;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (D.t[m] < t) lo = m; else hi = m; }
      const j = Math.abs(D.t[hi] - t) < Math.abs(D.t[lo] - t) ? hi : lo;
      const parts = [D.clock ? clockStr(D.t[j], true) : `${fmtS(D.t[j])} ${D.unit.u}`];
      for (const r of D.rows) parts.push(`${esc(r.id)} ${fmtN(r.y[j], 4)}`);
      const pvr = D.rows.find((r) => r.kind === "pv");
      if (pvr && pvr.model && pvr.model[S.model] && isFinite(pvr.model[S.model][j])) parts.push(`${esc(X.model)} ${fmtN(pvr.model[S.model][j], 4)}`);
      tip.innerHTML = parts.join(" · ");
      const br = box.getBoundingClientRect();
      tip.style.display = "block";
      tip.style.left = Math.max(4, Math.min(e.clientX - br.left + 12, br.width - tip.offsetWidth - 4)) + "px";
      tip.style.top = (e.clientY - br.top + 14) + "px";
    });
    a.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  }
  draw();
  let lastW = box.clientWidth;
  const ro = new ResizeObserver(() => {              // překreslit jen při změně šířky (výška se mění kreslením)
    if (box.clientWidth !== lastW) { lastW = box.clientWidth; draw(); }
  });
  ro.observe(box);
  reg[D.key].ro = ro;                                // odpojí ho příští vykreslení tohoto grafu
}
