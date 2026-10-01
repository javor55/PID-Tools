/*
 * Ovládání a vykreslení živé simulace v prohlížeči (canvas, ~60 snímků/s, bez komunikace se serverem).
 * Konfigurace v CFG (z pidtools/ui/pages/live.py): model, sady parametrů, prvky ventilu, rozsahy, texty, barvy.
 */
(function () {
  "use strict";
  var E = window.PIDLive, L = CFG.labels, C = CFG.colors;
  var $ = function (id) { return document.getElementById(id); };
  var EP = function (x) { return CFG.pv_lo + x * (CFG.pv_hi - CFG.pv_lo) / 100; };
  var EM = function (x) { return CFG.mv_lo + x * (CFG.mv_hi - CFG.mv_lo) / 100; };
  var P = function (x) { return (x - CFG.pv_lo) / (CFG.pv_hi - CFG.pv_lo) * 100; };
  var M = function (x) { return (x - CFG.mv_lo) / (CFG.mv_hi - CFG.mv_lo) * 100; };
  var fmt = function (v) { return Math.abs(v) >= 1000 ? v.toFixed(0) : v.toPrecision(4); };

  // ---------------------------------------------------------------- stav
  var S = { run: false, speed: CFG.speed0, set: "2", auto: true, sp: EP(CFG.pv0), mv: EM(CFG.mv0), d: 0 };
  var loop, buf, acc = 0, last = null;
  var REC = Math.max(1, Math.ceil(CFG.window / CFG.h / 20000));   // ukládá se každý REC-tý krok (max. ~20 000 bodů)
  var N = Math.ceil(CFG.window / CFG.h / REC) + 2, tick = 0;
  function newBuffers() { return { t: new Float64Array(N), SP: new Float64Array(N), PV: new Float64Array(N),
                                   MV: new Float64Array(N), V: new Float64Array(N), n: 0, i: 0 }; }
  function reset() {
    loop = new E.LiveLoop(CFG.code, CFG.p, CFG.sets[S.set], CFG.h, CFG.pv0, CFG.mv0, CFG.plant);
    buf = newBuffers(); acc = 0; push([0, CFG.pv0, CFG.pv0, CFG.mv0, CFG.mv0]);
    yr = [null, null];
  }
  function push(r) {
    var i = buf.i;
    buf.t[i] = r[0]; buf.SP[i] = r[1]; buf.PV[i] = r[2]; buf.MV[i] = r[3]; buf.V[i] = r[4];
    buf.i = (i + 1) % N; buf.n = Math.min(buf.n + 1, N);
  }
  function at(k) { return (buf.i - buf.n + k + N) % N; }     // k-tý nejstarší vzorek

  // ---------------------------------------------------------------- ovládání
  function seg(id, opts, cur, onPick) {
    var el = $(id); el.innerHTML = "";
    opts.forEach(function (o) {
      var b = document.createElement("button");
      b.textContent = o[1]; b.className = "seg" + (o[0] === cur ? " on" : "");
      b.onclick = function () { onPick(o[0]); seg(id, opts, o[0], onPick); };
      el.appendChild(b);
    });
  }
  function slider(id, lo, hi, val, onInput) {
    var el = $(id); el.min = lo; el.max = hi; el.step = (hi - lo) / 1000; el.value = val;
    el.oninput = function () { onInput(parseFloat(el.value)); refreshLabels(); };
  }
  function refreshLabels() {
    $("spv").textContent = fmt(S.sp) + " " + CFG.u_pv;
    $("mvv").textContent = fmt(S.mv) + " " + CFG.u_mv;
    $("dv").textContent = (S.d >= 0 ? "+" : "") + fmt(S.d) + " " + CFG.u_mv;
    $("mvs").disabled = S.auto;
    $("mvbox").classList.toggle("dis", S.auto);
  }
  function setRun(r) {
    S.run = r; $("run").textContent = r ? "❚❚ " + L.pause : "▶ " + L.start;
    $("run").classList.toggle("primary", !r); last = null;
  }
  $("run").onclick = function () { setRun(!S.run); };
  $("reset").textContent = "⟲ " + L.reset;
  $("reset").onclick = function () { reset(); draw(); };
  seg("speed", CFG.speeds.map(function (v) { return [v, v + "×"]; }), S.speed, function (v) { S.speed = v; });
  seg("set", [["1", L.set1], ["2", L.set2]], S.set, function (v) { S.set = v; loop.setTuning(CFG.sets[v]); });
  seg("mode", [["AUTO", "AUTO"], ["MAN", "MAN"]], "AUTO", function (v) {
    S.auto = v === "AUTO";
    if (!S.auto) { S.mv = EM(buf.MV[at(buf.n - 1)]); $("mvs").value = S.mv; }   // bezrázově z aktuální MV
    refreshLabels();
  });
  var span = (CFG.mv_hi - CFG.mv_lo) / 2;
  slider("sps", CFG.pv_lo, CFG.pv_hi, S.sp, function (v) { S.sp = v; });
  slider("mvs", CFG.mv_lo, CFG.mv_hi, S.mv, function (v) { S.mv = v; });
  slider("ds", -span, span, 0, function (v) { S.d = v; });
  $("d0").onclick = function () { S.d = 0; $("ds").value = 0; refreshLabels(); };
  ["lsp", "lmv", "ld", "lspeed", "lset", "lmode"].forEach(function (k) { $(k).textContent = L[k]; });
  $("d0").title = L.d0;

  // ---------------------------------------------------------------- simulace (krok podle reálného času × rychlost)
  function advance(dtReal) {
    acc += dtReal * S.speed;
    var steps = Math.min(Math.floor(acc / CFG.h), 20000);
    acc -= steps * CFG.h;
    if (acc > 10 * CFG.h) acc = 0;                             // počítač nestíhá → nedohánět
    var sp = P(S.sp), um = M(S.mv), d = S.d / (CFG.mv_hi - CFG.mv_lo) * 100;
    for (var k = 0; k < steps; k++) {
      var r = loop.tick(sp, S.auto, um, d);
      if (++tick % REC === 0) push(r);
    }
  }

  // ---------------------------------------------------------------- graf (canvas)
  var cv = $("cv"), g = cv.getContext("2d"), yr = [null, null];
  function nice(lo, hi, n) {
    var raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw / mag;
    var st = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, out = [];
    var dec = Math.max(0, -Math.floor(Math.log10(st) + 1e-9));   // počet desetinných míst podle kroku
    for (var v = Math.ceil(lo / st) * st; v <= hi + 1e-9 * Math.abs(st); v += st) out.push([v, v.toFixed(dec)]);
    return out;
  }
  function range(series, i0, panel) {
    var lo = Infinity, hi = -Infinity;
    for (var k = i0; k < buf.n; k++) {
      var j = at(k);
      series.forEach(function (s) { var v = s.f(buf[s.key][j]); if (v < lo) lo = v; if (v > hi) hi = v; });
    }
    var pad = Math.max((hi - lo) * 0.12, panel.minSpan / 2);
    lo -= pad; hi += pad;
    var cur = yr[panel.idx];
    if (!cur) { yr[panel.idx] = [lo, hi]; return yr[panel.idx]; }
    // rozšíření okamžitě, zúžení plynule (graf neposkakuje)
    cur[0] = lo < cur[0] ? lo : cur[0] + (lo - cur[0]) * 0.04;
    cur[1] = hi > cur[1] ? hi : cur[1] + (hi - cur[1]) * 0.04;
    return cur;
  }
  function draw() {
    var dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    g.font = "11px " + CFG.font; g.textBaseline = "middle";
    // osa nejdřív roste s daty (aby nebyla na začátku prázdná), po zaplnění okna se posouvá
    var tEnd = buf.t[at(buf.n - 1)], tStart = Math.max(0, tEnd - CFG.window);
    var span = Math.min(CFG.window, Math.max(tEnd - tStart, CFG.window / 8));
    var i0 = 0;
    while (i0 < buf.n - 1 && buf.t[at(i0)] < tStart) i0++;
    var left = 56, right = 12, top = 22, bottom = 26, gap = 18;
    var plotW = W - left - right, hAll = H - top - bottom - gap;
    var panels = [
      { idx: 0, y0: top, h: hAll * 0.62, title: CFG.lab_pv, minSpan: 0.02 * (CFG.pv_hi - CFG.pv_lo),
        series: [{ key: "SP", f: EP, c: C.sp, w: 1.5, dash: [6, 4], name: "SP" },
                 { key: "PV", f: EP, c: C.pv, w: 2, name: "PV" }] },
      { idx: 1, y0: top + hAll * 0.62 + gap, h: hAll * 0.38, title: CFG.lab_mv, minSpan: 0.02 * (CFG.mv_hi - CFG.mv_lo),
        series: [{ key: "MV", f: EM, c: S.set === "1" ? C.set1 : C.set2, w: 2, name: "MV" }]
                 .concat(CFG.plant.Stic > 0 ? [{ key: "V", f: EM, c: C.mv, w: 1.2, dash: [2, 3], name: L.valve }] : []) }
    ];
    var X = function (t) { return left + (t - tStart) / Math.max(span, 1e-9) * plotW; };
    panels.forEach(function (pn) {
      var r = range(pn.series, i0, pn), Y = function (v) { return pn.y0 + pn.h - (v - r[0]) / (r[1] - r[0]) * pn.h; };
      g.strokeStyle = C.grid; g.fillStyle = C.muted; g.lineWidth = 1; g.setLineDash([]);
      nice(r[0], r[1], 4).forEach(function (tk) {
        var y = Math.round(Y(tk[0])) + 0.5;
        g.beginPath(); g.moveTo(left, y); g.lineTo(left + plotW, y); g.stroke();
        g.textAlign = "right"; g.fillText(tk[1], left - 6, y);
      });
      g.save(); g.translate(14, pn.y0 + pn.h / 2); g.rotate(-Math.PI / 2); g.textAlign = "center";
      g.fillText(pn.title, 0, 0); g.restore();
      g.save(); g.beginPath(); g.rect(left, pn.y0, plotW, pn.h); g.clip();
      var stride = Math.max(1, Math.floor((buf.n - i0) / (plotW * 1.5)));
      pn.series.forEach(function (s) {
        g.strokeStyle = s.c; g.lineWidth = s.w; g.setLineDash(s.dash || []); g.beginPath();
        var first = true;
        for (var k = i0; k < buf.n; k += stride) {
          var lo = Infinity, hi = -Infinity, j, kk;
          for (kk = k; kk < Math.min(k + stride, buf.n); kk++) { var v = s.f(buf[s.key][at(kk)]); if (v < lo) lo = v; if (v > hi) hi = v; }
          j = at(k);
          var x = X(buf.t[j]);
          if (first) { g.moveTo(x, Y(lo)); first = false; } else g.lineTo(x, Y(lo));
          if (hi !== lo) g.lineTo(x, Y(hi));
        }
        g.stroke();
      });
      g.restore();
      // legenda
      var lx = left + 4;
      g.textAlign = "left"; g.setLineDash([]);
      pn.series.forEach(function (s) {
        g.strokeStyle = s.c; g.lineWidth = s.w; g.setLineDash(s.dash || []);
        g.beginPath(); g.moveTo(lx, pn.y0 - 9); g.lineTo(lx + 18, pn.y0 - 9); g.stroke();
        g.setLineDash([]); g.fillStyle = C.text; g.fillText(s.name, lx + 22, pn.y0 - 9);
        lx += 30 + g.measureText(s.name).width;
      });
    });
    // časová osa
    g.fillStyle = C.muted; g.textAlign = "center"; g.strokeStyle = C.grid; g.setLineDash([]);
    var tb = top + hAll + gap;
    nice(tStart, tStart + span, 6).forEach(function (tk) {
      var x = Math.round(X(tk[0])) + 0.5;
      g.beginPath(); g.moveTo(x, top); g.lineTo(x, tb); g.stroke();
      g.fillText(tk[1], x, tb + 10);
    });
    g.textAlign = "right"; g.fillText(L.time, left + plotW, tb + 21);
    // hodnoty
    var j = at(buf.n - 1);
    $("read").textContent = L.read.replace("{t}", fmt(buf.t[j])).replace("{pv}", fmt(EP(buf.PV[j])))
      .replace("{sp}", fmt(EP(buf.SP[j]))).replace("{mv}", fmt(EM(buf.MV[j])));
  }

  function frame(ts) {
    if (S.run) {
      if (last !== null) advance(Math.min((ts - last) / 1000, 0.25));
      last = ts;
    }
    draw();
    requestAnimationFrame(frame);
  }

  reset(); refreshLabels(); setRun(false);
  requestAnimationFrame(frame);
  window.addEventListener("resize", draw);
})();
