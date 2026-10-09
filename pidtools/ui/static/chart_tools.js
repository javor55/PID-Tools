/*
 * Nástroje všech grafů Plotly na stránce (běží přímo ve stránce, ne v iframe):
 *  - časová osa v s / min / h: u grafů s layout.meta.pt.time se popisky osy x přepočítají na zvolenou jednotku
 *    (auto = podle viditelného úseku) s „hezkými“ dílky, i po přiblížení;
 *  - měření: tlačítko u grafu zapne dva přetahovatelné kurzory – t₁, t₂, Δt a změna každé křivky mezi nimi.
 * data: {unit: "auto" | "s" | "min" | "h", txt: {measure, measure_tip, close}}
 */
export default function (component) {
  const { data } = component;
  const W = (window.__pidCharts = window.__pidCharts || { unit: "auto", txt: {}, seen: new WeakSet() });
  W.unit = (data && data.unit) || "auto";
  W.txt = (data && data.txt) || W.txt;
  const P = () => window.Plotly;

  // výška hlavičky se záložkami → --pid-top: plocha a panel pod ní mají výšku okna a rolují nezávisle
  function measureTop() {
    const tl = document.querySelector('.st-key-main_tab [role="tablist"]');
    if (!tl) return;
    const top = Math.round(tl.getBoundingClientRect().bottom + (document.querySelector('[data-testid="stMain"]')?.scrollTop || 0));
    document.documentElement.style.setProperty("--pid-top", top + "px");
  }
  if (!W.topObs) {
    W.topObs = true;
    window.addEventListener("resize", measureTop);
    setInterval(measureTop, 1500);
  }
  measureTop();
  const U = { s: 1, min: 60, h: 3600 };

  function unitFor(span) {
    if (W.unit in U) return W.unit;
    return span <= 1200 ? "s" : span <= 72000 ? "min" : "h";
  }
  function nice(x) {
    const e = Math.pow(10, Math.floor(Math.log10(x)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * e >= x * (1 - 1e-9)) return m * e;
    return 10 * e;
  }
  function num(v, step) {
    const d = Math.max(0, Math.min(6, -Math.floor(Math.log10(step) + 1e-9)));
    return v.toFixed(d).replace(/\.0+$/, "");
  }
  function sig(v) {
    if (v === null || !isFinite(v)) return "—";
    return Number(v.toPrecision(4)).toString();
  }
  function dur(s) {
    const a = Math.abs(s);
    if (a < 120) return sig(s) + " s";
    if (a < 7200) return sig(s / 60) + " min";
    const m = Math.round(a / 60);
    return (s < 0 ? "-" : "") + Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0") + " min";
  }
  function tval(t, u) {
    return u === "s" ? sig(t) + " s" : sig(t / U[u]) + " " + u;
  }
  const isTime = (gd) => !!(gd.layout && gd.layout.meta && gd.layout.meta.pt && gd.layout.meta.pt.time);

  // ---- časová osa
  function applyTime(gd) {
    const fl = gd._fullLayout;
    if (!fl || !isTime(gd) || !P()) return;
    gd.__ptTitles = gd.__ptTitles || {};
    const upd = {};
    let key = "";
    for (const ax of Object.keys(fl).filter((k) => /^xaxis\d*$/.test(k))) {
      const xa = fl[ax];
      if (!xa || xa.type === "log" || xa.type === "date" || !xa.range) continue;
      const [a, b] = xa.range.map(Number);
      if (!isFinite(a) || !isFinite(b) || b <= a) continue;
      const u = unitFor(b - a);
      const tl = gd.layout[ax] && gd.layout[ax].title;
      const title = typeof tl === "string" ? tl : tl && tl.text;
      if (!(ax in gd.__ptTitles)) gd.__ptTitles[ax] = title || "";
      const t0 = gd.__ptTitles[ax];
      if (u === "s") {
        upd[ax + ".tickmode"] = "auto";
        upd[ax + ".tickvals"] = null;
        upd[ax + ".ticktext"] = null;
        if (t0) upd[ax + ".title.text"] = t0;
        key += ax + ":s|";
        continue;
      }
      const step = nice((b - a) / U[u] / 7);
      const vals = [], txt = [];
      for (let v = Math.ceil(a / U[u] / step) * step; v <= b / U[u] + 1e-9; v += step) {
        vals.push(v * U[u]);
        txt.push(num(v, step));
      }
      upd[ax + ".tickmode"] = "array";
      upd[ax + ".tickvals"] = vals;
      upd[ax + ".ticktext"] = txt;
      if (t0) upd[ax + ".title.text"] = t0.replace(/\[\s*s\s*\]/, "[" + u + "]");
      key += ax + ":" + u + ":" + vals[0] + ":" + step + "|";
    }
    if (!key || gd.__ptKey === key) return;
    gd.__ptKey = key;
    P().relayout(gd, upd);
  }

  // ---- měření
  function curves(gd) {
    const out = [];
    for (const tr of gd._fullData || []) {
      if (tr.visible !== true || !tr.x || !tr.y || !tr.name || tr.type !== "scatter") continue;
      if (tr.xaxis !== "x" && tr.xaxis && !/^x\d*$/.test(tr.xaxis)) continue;
      out.push(tr);
    }
    return out;
  }
  function at(tr, t) {
    const x = tr.x, y = tr.y, n = x.length;
    if (!n || t < x[0] || t > x[n - 1]) return null;
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      const m = (lo + hi) >> 1;
      if (x[m] < t) lo = m; else hi = m;
    }
    const j = Math.abs(x[hi] - t) < Math.abs(x[lo] - t) ? hi : lo;
    const v = Number(y[j]);
    return isFinite(v) ? v : null;
  }
  function drawMeas(gd) {
    const m = gd.__ptMeas, fl = gd._fullLayout;
    if (!m || !fl || !fl.xaxis) return;
    const xa = fl.xaxis, sz = fl._size, log = xa.type === "log";
    const toPx = (t) => sz.l + xa.l2p(log ? Math.log10(t) : t);
    m.lines.forEach((ln, i) => {
      ln.style.left = toPx(m.t[i]) - 5 + "px";
      ln.style.top = sz.t + "px";
      ln.style.height = sz.h + "px";
    });
    const span = (xa.range[1] - xa.range[0]) * (log ? 0 : 1);
    const u = isTime(gd) ? unitFor(span) : null;
    const [t1, t2] = m.t;
    const fx = (t) => (u ? tval(t, u) : sig(t));
    const parts = ["t₁ = " + fx(t1), "t₂ = " + fx(t2),
      log ? "t₂/t₁ = " + sig(t2 / t1) : "Δt = " + (u ? dur(t2 - t1) : sig(t2 - t1))];
    for (const tr of curves(gd)) {
      const a = at(tr, t1), b = at(tr, t2);
      if (a !== null && b !== null) parts.push("Δ" + tr.name + " = " + sig(b - a));
    }
    m.box.textContent = parts.join("   ");
    m.box.style.left = sz.l + "px";
    m.box.style.top = Math.max(0, sz.t - 22) + "px";
    m.box.style.maxWidth = sz.w + "px";
  }
  function startMeas(gd) {
    const fl = gd._fullLayout;
    if (!fl || !fl.xaxis) return;
    const xa = fl.xaxis, log = xa.type === "log";
    const r = xa.range.map(Number).map((v) => (log ? Math.pow(10, v) : v));
    const m = (gd.__ptMeas = { t: log ? [Math.sqrt(r[0] * Math.sqrt(r[0] * r[1])), Math.sqrt(r[1] * Math.sqrt(r[0] * r[1]))]
      : [r[0] + 0.3 * (r[1] - r[0]), r[0] + 0.6 * (r[1] - r[0])], lines: [] });
    if (getComputedStyle(gd).position === "static") gd.style.position = "relative";
    ["#d97706", "#7c3aed"].forEach((col, i) => {
      const ln = document.createElement("div");
      ln.className = "pt-meas-line";
      ln.style.cssText = "position:absolute;width:11px;cursor:ew-resize;z-index:20;touch-action:none;";
      ln.innerHTML = `<div style="position:absolute;left:5px;top:0;bottom:0;width:0;border-left:2px solid ${col}"></div>`;
      ln.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        ln.setPointerCapture(ev.pointerId);
        const move = (e) => {
          const f = gd._fullLayout, x = f.xaxis, rect = gd.getBoundingClientRect();
          let v = x.p2l(e.clientX - rect.left - f._size.l);
          const lo = Math.min(...x.range), hi = Math.max(...x.range);
          v = Math.min(Math.max(v, lo), hi);
          m.t[i] = x.type === "log" ? Math.pow(10, v) : v;
          drawMeas(gd);
        };
        const up = () => {
          ln.removeEventListener("pointermove", move);
          ln.removeEventListener("pointerup", up);
        };
        ln.addEventListener("pointermove", move);
        ln.addEventListener("pointerup", up);
      });
      gd.appendChild(ln);
      m.lines.push(ln);
    });
    const box = document.createElement("div");
    box.className = "pt-meas-box";
    box.style.cssText = "position:absolute;z-index:21;font:11px ui-monospace,Consolas,monospace;" +
      "background:rgba(255,255,255,.9);color:#1f2933;padding:2px 6px;border-radius:4px;white-space:nowrap;" +
      "overflow:hidden;text-overflow:ellipsis;pointer-events:none;";
    gd.appendChild(box);
    m.box = box;
    drawMeas(gd);
  }
  function stopMeas(gd) {
    const m = gd.__ptMeas;
    if (!m) return;
    m.lines.forEach((l) => l.remove());
    if (m.box) m.box.remove();
    gd.__ptMeas = null;
  }
  function addButton(gd) {
    if (gd.querySelector(":scope > .pt-meas-btn")) return;
    if (getComputedStyle(gd).position === "static") gd.style.position = "relative";
    const b = document.createElement("button");
    b.className = "pt-meas-btn";
    b.type = "button";
    b.textContent = W.txt.measure || "Measure";
    b.title = W.txt.measure_tip || "";
    b.style.cssText = "position:absolute;left:2px;top:2px;z-index:22;font:11px sans-serif;padding:1px 6px;" +
      "border:1px solid #cbd2d9;border-radius:4px;background:rgba(255,255,255,.85);color:#374151;cursor:pointer;";
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (gd.__ptMeas) {
        stopMeas(gd);
        b.style.background = "rgba(255,255,255,.85)";
      } else {
        startMeas(gd);
        b.style.background = "#fde68a";
      }
    });
    gd.appendChild(b);
  }

  function init(gd) {
    if (!gd._fullLayout) return;
    addButton(gd);
    if (!W.seen.has(gd) && typeof gd.on === "function") {
      W.seen.add(gd);
      gd.on("plotly_afterplot", () => {
        applyTime(gd);
        drawMeas(gd);
      });
      gd.on("plotly_relayout", () => drawMeas(gd));
    }
    applyTime(gd);
    drawMeas(gd);
  }
  function scan() {
    document.querySelectorAll(".js-plotly-plot").forEach(init);
  }
  if (W.lastUnit !== W.unit) {          // jiná jednotka → popisky os všech grafů znovu
    W.lastUnit = W.unit;
    document.querySelectorAll(".js-plotly-plot").forEach((gd) => { gd.__ptKey = null; });
  }
  // ---- panel nastavení: „Rozbalit vše / Sbalit vše“ (přepne sekce kliknutím na jejich nadpis, bez nového běhu)
  if (!W.sideTools) {
    W.sideTools = true;
    document.addEventListener("click", (ev) => {
      const b = ev.target.closest && ev.target.closest(".pid-side-tools button[data-pid-all]");
      if (!b) return;
      const side = b.closest('[class*="st-key-pidside_"]');
      if (!side) return;
      const want = b.getAttribute("data-pid-all") === "1";
      side.querySelectorAll('[data-testid="stExpander"] details').forEach((d) => {
        if (d.open !== want) {
          const s = d.querySelector("summary");
          if (s) s.click();
        }
      });
    });
  }
  scan();
  if (!W.obs) {
    let pending = false;
    W.obs = new MutationObserver(() => {
      if (pending) return;
      pending = true;
      setTimeout(() => {
        pending = false;
        scan();
      }, 300);
    });
    W.obs.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("resize", () => document.querySelectorAll(".js-plotly-plot").forEach(drawMeas));
  }
}
