/*
 * Záložka Model – grafy PV, MV a měřených poruch s úseky pro identifikaci (komponenta st.components.v2, běží
 * přímo na stránce). Každý vstup má pod grafem táhla svých úseků; v režimu „Společný úsek“ je jeden úsek pro
 * všechny vstupy. Kolečko = zoom, tažení v grafu = posun (všechny grafy spolu), šrafované části jsou vyřazené.
 *
 * Data z Pythonu (component.data):
 *   mode "common" | "inputs", t [s], T (délka), step (krok dat), unit {u, f} (časová osa), dec ("," / ".")
 *   rows: [{id, kind "pv" | "in", title, badge, note, color, wcol, wbg, wbd, wtx, y, lo, hi, ticks,
 *           wins [[a, b]], fits [FIT], model: {all, mv, dv, full}, resid}]
 *   excl [[a, b]] (vyřazené úseky), common [a, b], txt {…} (texty), view_key
 * Do Pythonu: stav „wins“ = {mode, wins: {id: [[a, b]]}, common: [a, b]} (po puštění táhla / změně čísla),
 *   trigger „mode“ = nový režim úseků.
 */
export default function (component) {
  "use strict";
  const D = component.data, root = component.parentElement, X = D.txt;
  const store = (window.__pidWins = window.__pidWins || {});
  const S = (store[D.view_key] = store[D.view_key] || { view: [0, D.T], model: "all", resid: false, onlyWin: true });
  if (!(S.view[1] > S.view[0]) || S.view[1] > D.T * 1.0001) S.view = [0, D.T];
  const W = { mode: D.mode, wins: {}, common: D.common.slice() };
  for (const r of D.rows) if (r.kind === "in") W.wins[r.id] = r.wins.map((w) => w.slice());
  const fmtN = (v, d) => {
    if (v === null || !isFinite(v)) return "–";
    const s = Math.abs(v) >= 1000 ? v.toFixed(0) : String(+v.toPrecision(d || 4));
    return D.dec === "," ? s.replace(".", ",") : s;
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

  function send() {
    component.setStateValue("wins", { mode: W.mode, wins: W.wins, common: W.common });
  }

  // ---------------------------------------------------------------- kostra
  // předchozí vykreslení pryč (styly komponenty v kořeni nechat); kořen se mezi běhy může změnit
  root.querySelectorAll(".pidw").forEach((n) => n.remove());
  if (window.__pidWinsBox && window.__pidWinsBox.isConnected) window.__pidWinsBox.remove();
  const box = el("div", "pidw" + (D.dark ? " dark" : ""));
  root.appendChild(box);
  window.__pidWinsBox = box;

  // lišta: režim úseků, zoom, legenda
  const bar = el("div", "pidw-card pidw-bar");
  bar.innerHTML =
    `<div class="pidw-grp"><span class="pidw-lab">${esc(X.mode)}</span>` +
    `<span class="pidw-help" title="${esc(X.h_mode)}">?</span>` +
    `<div class="pidw-seg" data-g="mode"><button data-v="common">${esc(X.common)}</button>` +
    `<button data-v="inputs">${esc(X.inputs)}</button></div></div>` +
    `<div class="pidw-grp"><span class="pidw-lab">${esc(X.zoom)}</span>` +
    `<div class="pidw-seg" data-g="zoom"><button data-v="all">${esc(X.zoom_all)}</button>` +
    `<button data-v="win">${esc(X.zoom_win)}</button></div>` +
    `<span class="pidw-note">${esc(X.zoom_note)}</span></div>` +
    `<div class="pidw-leg">${D.rows.filter((r) => r.kind === "in").map((r) =>
      `<span><i style="background:${r.wbg};border-color:${r.wtx}"></i>${esc(r.id)}</span>`).join("")}` +
    `<span><i class="pidw-hatch"></i>${esc(X.excluded)}</span></div>`;
  box.appendChild(bar);
  bar.querySelectorAll('[data-g="mode"] button').forEach((b) => {
    b.classList.toggle("on", b.dataset.v === W.mode);
    b.onclick = () => { if (b.dataset.v !== W.mode) component.setTriggerValue("mode", b.dataset.v); };
  });
  bar.querySelector('[data-v="all"]').onclick = () => { S.view = [0, D.T]; draw(); };
  bar.querySelector('[data-v="win"]').onclick = () => {
    const all = W.mode === "common" ? [W.common] : [].concat(...Object.values(W.wins));
    if (!all.length) return;
    const a = Math.min(...all.map((w) => w[0])), b = Math.max(...all.map((w) => w[1])), m = 0.2 * (b - a);
    S.view = [Math.max(0, a - m), Math.min(D.T, b + m)];
    draw();
  };

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
      head.appendChild(el("span", "pidw-leg2", `<span><i style="border-top:2px solid ${r.color}"></i>PV</span>` +
        `<span><i style="border-top:2px dashed #5b3fa8"></i>${esc(X.model)}</span>`));
    }
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
    let track = null, chips = null;
    const showTrack = (r.kind === "in" && W.mode === "inputs") || (r.kind === "pv" && W.mode === "common");
    if (showTrack) {
      track = el("div", "pidw-plot pidw-trackrow");
      track.append(el("span"), el("div", "pidw-track"));
      c.appendChild(track);
      chips = el("div", "pidw-chips");
      c.appendChild(chips);
    }
    let xax = null;
    if (ri === D.rows.length - 1) {
      xax = el("div", "pidw-plot");
      xax.append(el("span"), el("div", "pidw-xax"));
      c.appendChild(xax);
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
    const st = nice(hi - lo, 4);
    for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) {
      const s = el("span", "", fmtN(v, 4));
      s.style.top = (ty(v, lo, hi, h) / h * 100) + "%";
      ax.appendChild(s);
    }
    return st;
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
  function drawArea(card, area, ys, lo, hi, opts) {
    const w = area.clientWidth || 600, h = area.clientHeight || 100;
    area.innerHTML = "";
    const svg = svgEl("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}` });
    const pid = "pidwh" + Math.random().toString(36).slice(2, 7);
    const defs = svgEl("defs", {});
    const pat = svgEl("pattern", { id: pid, width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
    pat.append(svgEl("rect", { width: 6, height: 6, fill: "var(--pidw-hbg)" }), svgEl("rect", { width: 2, height: 6, fill: "#8a96a3" }));
    defs.appendChild(pat);
    svg.appendChild(defs);
    const st = nice(hi - lo, 4);
    for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st)
      svg.appendChild(svgEl("line", { x1: 0, x2: w, y1: ty(v, lo, hi, h), y2: ty(v, lo, hi, h), stroke: "var(--pidw-grid)" }));
    // úseky (všechny vstupy v PV, vlastní v grafu vstupu)
    if (W.mode === "common") band(svg, W.common[0], W.common[1], w, h, "#f59e0b", 0.14, opts.own ? "#c77d00" : null);
    else for (const rr of D.rows) {
      if (rr.kind !== "in") continue;
      if (opts.own && rr.id !== card.r.id) continue;
      for (const wn of W.wins[rr.id]) band(svg, wn[0], wn[1], w, h, rr.wcol, opts.own ? 0.28 : 0.13, opts.own ? rr.wtx : null);
    }
    for (const e of D.excl) band(svg, e[0], e[1], w, h, `url(#${pid})`, 0.85);
    for (const [arr, col, dash, sw] of opts.lines) {
      if (!arr) continue;
      const p = svgEl("path", { d: path(D.t, arr, w, h, lo, hi), fill: "none", stroke: col, "stroke-width": sw || 2 });
      if (dash) p.setAttribute("stroke-dasharray", dash);
      svg.appendChild(p);
    }
    area.appendChild(svg);
    // popisky úseků
    if (opts.own && W.mode === "inputs") (W.wins[card.r.id] || []).forEach((wn, i) => {
      const x = tx(wn[0], w);
      if (x < 0 || x > w) return;
      const l = el("span", "pidw-wlab", `${esc(card.r.id)} ${esc(X.win)} ${i + 1}`);
      l.style.cssText = `left:${x}px;color:${card.r.wtx};background:${card.r.wbg};border-color:${card.r.wbd}`;
      area.appendChild(l);
    });
  }
  function drawTrack(card) {
    const tr = card.track.querySelector(".pidw-track");
    tr.innerHTML = '<div class="pidw-rail"></div>';
    const w = tr.clientWidth || 600, r = card.r;
    const list = W.mode === "common" ? [W.common] : W.wins[r.id];
    const col = W.mode === "common" ? "#f59e0b" : r.wcol, bd = W.mode === "common" ? "#c77d00" : r.wtx;
    list.forEach((wn, i) => {
      const x0 = tx(wn[0], w), x1 = tx(wn[1], w);
      const fill = el("div", "pidw-fill");
      fill.style.cssText = `left:${Math.max(0, x0)}px;width:${Math.max(2, Math.min(w, x1) - Math.max(0, x0))}px;background:${col}`;
      fill.title = X.drag_win;
      tr.appendChild(fill);
      drag(fill, (dt) => { const L = wn[1] - wn[0]; wn[0] = clamp(wn[0] + dt, 0, D.T - L); wn[1] = wn[0] + L; }, w);
      for (const k of [0, 1]) {
        const x = k ? x1 : x0;
        if (x < -10 || x > w + 10) continue;
        const hd = el("button", "pidw-handle");
        hd.type = "button";
        hd.style.cssText = `left:${x}px;border-color:${bd}`;
        hd.setAttribute("aria-label", `${k ? X.end : X.start} ${i + 1}: ${fmtS(wn[k])} ${D.unit.u}`);
        tr.appendChild(hd);
        drag(hd, (dt) => {
          if (k) wn[1] = clamp(wn[1] + dt, wn[0] + D.step * 3, D.T);
          else wn[0] = clamp(wn[0] + dt, 0, wn[1] - D.step * 3);
        }, w);
      }
    });
  }
  function drawChips(card) {
    const r = card.r, ch = card.chips;
    ch.innerHTML = "";
    const list = W.mode === "common" ? [W.common] : W.wins[r.id];
    const st = W.mode === "common" ? "background:#fff4dc;border-color:#f2c46d;color:#5c3800"
      : `background:${r.wbg};border-color:${r.wbd};color:${r.wtx}`;
    list.forEach((wn, i) => {
      const c = el("span", "pidw-chip");
      c.style.cssText = st;
      const fit = W.mode === "inputs" && r.fits && r.fits[i] !== undefined && r.fits[i] !== null ? ` · FIT ${fmtN(r.fits[i], 3)} %` : "";
      c.innerHTML = `${i + 1} · <input aria-label="${esc(X.start)} ${i + 1}" value="${fmtS(wn[0])}">–` +
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
      if (del) del.onclick = () => { W.wins[r.id].splice(i, 1); draw(); send(); };
      ch.appendChild(c);
    });
    if (W.mode === "inputs") {
      const add = el("button", "pidw-add", esc(X.add.replace("{n}", r.id)));
      add.type = "button";
      add.onclick = () => {                          // nový úsek uprostřed zobrazeného rozsahu (20 % šířky)
        const L = 0.2 * (S.view[1] - S.view[0]), m = (S.view[0] + S.view[1]) / 2;
        W.wins[r.id].push([Math.max(0, m - L / 2), Math.min(D.T, m + L / 2)]);
        draw();
        send();
      };
      ch.appendChild(add);
    }
  }
  function drawX(card) {
    const xa = card.xax.querySelector(".pidw-xax");
    xa.innerHTML = "";
    const w = xa.clientWidth || 600, span = (S.view[1] - S.view[0]) / D.unit.f, st = nice(span, 7);
    for (let v = Math.ceil(S.view[0] / D.unit.f / st) * st; v <= S.view[1] / D.unit.f + 1e-9; v += st) {
      const x = tx(v * D.unit.f, w);
      if (x > w - 70) continue;                       // vpravo je popisek osy
      const s = el("span", "", fmtN(+v.toPrecision(6), 6));
      s.style.left = x + "px";
      xa.appendChild(s);
    }
    const u = el("span", "pidw-xu", esc(X.time.replace("{u}", D.unit.u)));
    xa.appendChild(u);
  }
  function draw() {
    for (const card of cards) {
      const r = card.r;
      if (card.head) card.head.querySelectorAll(".pidw-model button").forEach((b) => b.classList.toggle("on", b.dataset.v === S.model));
      card.head.querySelectorAll(".pidw-chk input").forEach((inp, k) => { inp.checked = k ? S.onlyWin : S.resid; });
      yTicks(card.ax, r.lo, r.hi, r.h);
      const lines = [[r.y, r.color, null, 1.8]];
      if (r.kind === "pv" && r.model) {
        const m = S.onlyWin ? r.model[S.model] : (r.model.full && S.model === "all" ? r.model.full : r.model[S.model]);
        lines.push([m, "#5b3fa8", "6 4", 2.4]);
      }
      drawArea(card, card.area, r.y, r.lo, r.hi, { own: r.kind === "in" || (r.kind === "pv" && W.mode === "common"), lines });
      if (card.resid) {
        card.resid.style.display = S.resid ? "" : "none";
        if (S.resid) {
          const ra = card.resid.querySelector(".pidw-area"), rx = card.resid.querySelector(".pidw-yax");
          const v = r.resid.filter((q) => q !== null && isFinite(q));
          const m = Math.max(1e-9, ...v.map(Math.abs));
          yTicks(rx, -m, m, 70);
          drawArea(card, ra, r.resid, -m * 1.1, m * 1.1, { own: false, lines: [[r.resid, "#5b3fa8", null, 1.4]] });
        }
      }
      if (card.track) { drawTrack(card); drawChips(card); }
      if (card.xax) drawX(card);
    }
  }
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  // táhla: posun v pixelech → čas podle zobrazeného rozsahu (po přiblížení jemněji)
  function drag(node, apply, w) {
    node.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      node.setPointerCapture(ev.pointerId);
      let last = ev.clientX;
      const move = (e) => {
        const dt = (e.clientX - last) / w * (S.view[1] - S.view[0]);
        last = e.clientX;
        apply(dt);
        draw();
      };
      const up = () => {
        node.removeEventListener("pointermove", move);
        node.removeEventListener("pointerup", up);
        for (const v of Object.values(W.wins)) for (const q of v) { q[0] = snap(q[0]); q[1] = snap(q[1]); }
        W.common = [snap(W.common[0]), snap(W.common[1])];
        draw();
        send();
      };
      node.addEventListener("pointermove", move);
      node.addEventListener("pointerup", up);
    });
  }
  const snap = (v) => Math.round(v / D.step) * D.step;

  // zoom kolečkem a posun tažením v grafech; najetí myší ukáže hodnoty
  for (const card of cards) {
    const a = card.area;
    a.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = a.getBoundingClientRect(), f = (e.clientX - rect.left) / rect.width;
      const t0 = S.view[0] + f * (S.view[1] - S.view[0]);
      const k = e.deltaY > 0 ? 1.25 : 0.8;
      let L = (S.view[1] - S.view[0]) * k;
      L = clamp(L, D.step * 20, D.T);
      let v0 = t0 - f * L;
      v0 = clamp(v0, 0, D.T - L);
      S.view = [v0, v0 + L];
      draw();
    }, { passive: false });
    a.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      a.setPointerCapture(e.pointerId);
      let last = e.clientX;
      const w = a.clientWidth;
      const move = (ev) => {
        const L = S.view[1] - S.view[0], dt = -(ev.clientX - last) / w * L;
        last = ev.clientX;
        const v0 = clamp(S.view[0] + dt, 0, D.T - L);
        S.view = [v0, v0 + L];
        draw();
      };
      const up = () => { a.removeEventListener("pointermove", move); a.removeEventListener("pointerup", up); };
      a.addEventListener("pointermove", move);
      a.addEventListener("pointerup", up);
    });
    a.addEventListener("mousemove", (e) => {
      const rect = a.getBoundingClientRect(), f = (e.clientX - rect.left) / rect.width;
      const t = S.view[0] + f * (S.view[1] - S.view[0]);
      let lo = 0, hi = D.t.length - 1;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (D.t[m] < t) lo = m; else hi = m; }
      const j = Math.abs(D.t[hi] - t) < Math.abs(D.t[lo] - t) ? hi : lo;
      const parts = [`${fmtS(D.t[j])} ${D.unit.u}`];
      for (const r of D.rows) parts.push(`${esc(r.id)} ${fmtN(r.y[j], 4)}`);
      const pvr = D.rows.find((r) => r.kind === "pv");
      if (pvr && pvr.model && pvr.model[S.model] && isFinite(pvr.model[S.model][j])) parts.push(`${esc(X.model)} ${fmtN(pvr.model[S.model][j], 4)}`);
      tip.innerHTML = parts.join(" · ");
      const br = box.getBoundingClientRect();
      tip.style.display = "block";
      tip.style.left = Math.min(e.clientX - br.left + 12, br.width - tip.offsetWidth - 4) + "px";
      tip.style.top = (e.clientY - br.top + 14) + "px";
    });
    a.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  }
  draw();
  let lastW = box.clientWidth;
  new ResizeObserver(() => {                         // překreslit jen při změně šířky (výška se mění kreslením)
    if (box.clientWidth !== lastW) { lastW = box.clientWidth; draw(); }
  }).observe(box);
}
