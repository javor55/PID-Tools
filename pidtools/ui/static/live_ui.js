/*
 * Živá simulace v prohlížeči – komponenta st.components.v2 (běží přímo na stránce, ~60 snímků/s).
 * Stav simulace se drží ve window.__pidLive, takže přežije přepnutí záložky i rerun aplikace.
 * Data z Pythonu (component.data): model, sady parametrů, prvky ventilu, rozsahy, texty, barvy.
 * Do Pythonu: trigger „apply“ = parametry sady 2 naladěné v simulaci (tlačítko „Zapsat do sady 2“).
 */
export default function (component) {
  "use strict";
  const CFG = component.data, root = component.parentElement, E = window.PIDLive;
  // texty nového vzhledu, které web_config nezná (hostitel je může přepsat v CFG.labels); jinak podle jazyka z desetinného znaku
  const FB = {
    cs: { now: "teď", kpi_change: "Změna", same: "stejná", run_dist: "Vyvolat poruchu", dist_shape: "Tvar", dist_where: "Kam",
          dist_size: "Velikost", dist_period: "Perioda", period_hint: "jen u sinusu a pulsu", noise_pv: "Šum PV σ", mv_man: "Ruční MV",
          mode_hint: "Ruční MV je aktivní v režimu MAN; přepnutí je beznárazové jako na faceplatu.",
          sets_note: "Sady se převezmou z Ladění při přepnutí na tuto záložku.",
          dist_note: "Porucha začne působit po stisknutí „Vyvolat poruchu“ (puls vyšle jeden puls); tvar a místo určují, jak smyčku zasáhne.",
          h_mode: "", h_sets: "", h_dist: "", h_kpi: "" },
    en: { now: "now", kpi_change: "Change", same: "same", run_dist: "Apply disturbance", dist_shape: "Shape", dist_where: "Where",
          dist_size: "Size", dist_period: "Period", period_hint: "sine and pulse only", noise_pv: "PV noise σ", mv_man: "Manual MV",
          mode_hint: "Manual MV is active in MAN mode; switching is bumpless, as on a faceplate.",
          sets_note: "The sets are taken from Tuning when you switch to this tab.",
          dist_note: "The disturbance starts when you press “Apply disturbance” (pulse sends one pulse); shape and place set how it hits the loop.",
          h_mode: "", h_sets: "", h_dist: "", h_kpi: "" } };
  const L = Object.assign({}, FB[CFG.decimal === "," ? "cs" : "en"], CFG.labels);
  const store = (window.__pidLive = window.__pidLive || {});
  const PR = CFG.pv_hi - CFG.pv_lo, MR = CFG.mv_hi - CFG.mv_lo;
  const EP = (x) => CFG.pv_lo + x * PR / 100, EM = (x) => CFG.mv_lo + x * MR / 100;
  const P = (x) => (x - CFG.pv_lo) / PR * 100, M = (x) => (x - CFG.mv_lo) / MR * 100;
  const dcm = (t) => t.replace(".", CFG.decimal);
  const fmt = (v) => !isFinite(v) ? "–" : dcm(Math.abs(v) >= 1000 ? v.toFixed(0) : Math.abs(v) < 1e-9 ? "0" : String(+v.toPrecision(4)));
  const tile = (v) => !isFinite(v) ? "–" : dcm(Math.abs(v) >= 1000 ? v.toFixed(0) : v.toPrecision(4));      // dlaždice: pevný počet míst (15,00)
  const clock = (s) => Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0");
  const WINDOWS = ["auto", 60, 300, 900, 3600];
  const MAXWIN = Math.max(CFG.window, 3600);
  const REC = Math.max(1, Math.ceil(MAXWIN / CFG.h / 20000));          // ukládá se každý REC-tý krok
  const N = Math.ceil(MAXWIN / CFG.h / REC) + 2;

  function at(b, k) { return (b.i - b.n + k + N) % N; }                  // k-tý nejstarší vzorek bufferu
  function gauss() {
    let u = 0, v = 0;
    while (!u) u = S.rng();
    while (!v) v = S.rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  // ---------------------------------------------------------------- stav (přežije rerun)
  let S = store[CFG.sim_id];
  if (!S) {
    S = store[CFG.sim_id] = {
      run: false, speed: CFG.speed0, set: "2", auto: true, compare: false, win: "auto",
      sp: EP(CFG.pv0), mv: EM(CFG.mv0),
      tune: Object.assign({}, CFG.sets["2"]), setsKey: "",
      noise: CFG.noise0, pvf: CFG.pvf0,
      dist: { type: "step", loc: "in", A: 0, pend: 0, Pp: CFG.dist_p0, t0: 0, d0: 0, x: 0, pulseUntil: -1 },
      plant: { k: 1, t: 1, th: 1, stic: CFG.plant.Stic || 0 },
      view: null, events: [], t: 0, acc: 0, tick: 0, loops: null, bufs: null, kpi: null, seed: 7,
    };
    reset();
  }
  // parametry z Pythonu se změnily (Ladění, zápis zpět) → bez resetu přeladit běžící smyčky
  const setsKey = JSON.stringify(CFG.sets);
  if (S.setsKey !== setsKey) {
    if (S.setsKey) { S.tune = Object.assign({}, CFG.sets["2"]); retune(); event(L.ev_tune); }
    S.setsKey = setsKey;
  }

  function setOf(name) { return name === "2" ? Object.assign({}, CFG.sets["2"], S.tune) : CFG.sets["1"]; }
  function loopNames() { return S.compare ? ["1", "2"] : [S.set]; }
  function plantP() {
    const p = CFG.p.slice(), c = CFG.code;
    p[0] *= S.plant.k;
    if (c === "P1D" || c === "P2D" || c === "I1D") p[1] *= S.plant.t;
    if (c === "P2D") p[2] *= S.plant.t;
    p[p.length - 1] *= S.plant.th;
    return p;
  }
  function newBuf() {
    const b = { n: 0, i: 0 };
    ["t", "SP", "PV", "MV", "V", "D"].forEach((k) => (b[k] = new Float64Array(N)));
    return b;
  }
  function reset() {
    S.loops = {}; S.bufs = {}; S.kpi = {}; S.t = 0; S.acc = 0; S.tick = 0; S.events = []; S.view = null;
    S.dist.x = 0; S.dist.t0 = 0; S.dist.d0 = 0; S.dist.pulseUntil = -1;
    S.rng = mulberry(S.seed);
    loopNames().forEach((nm) => {
      const plant = Object.assign({}, CFG.plant, { Seed: S.seed });       // stejný šum pro obě sady
      const lp = new E.LiveLoop(CFG.code, plantP(), Object.assign({}, CFG.sets[nm], setOf(nm)), CFG.h, CFG.pv0, CFG.mv0, plant);
      lp.setNoise(S.noise / PR * 100); lp.setPVFilter(S.pvf); lp.setStiction(S.plant.stic / MR * 100, stJ());
      S.loops[nm] = lp; S.bufs[nm] = newBuf();
      push(nm, [0, CFG.pv0, CFG.pv0, CFG.mv0, CFG.mv0], 0);
    });
    kpiReset(null);
  }
  function stJ() { const S0 = CFG.plant.Stic || 0, J0 = CFG.plant.SticJ; return J0 == null || S0 <= 0 ? null : S.plant.stic / MR * 100 * J0 / S0; }
  function retune() { for (const nm in S.loops) if (nm === "2") S.loops[nm].setTuning(setOf("2")); }
  function applyPlant() { for (const nm in S.loops) S.loops[nm].setPlant(plantP()); }
  function applyMeas() {
    for (const nm in S.loops) { S.loops[nm].setNoise(S.noise / PR * 100); S.loops[nm].setPVFilter(S.pvf); }
  }
  function applyStic() { for (const nm in S.loops) S.loops[nm].setStiction(S.plant.stic / MR * 100, stJ()); }
  function push(nm, r, d) {
    const b = S.bufs[nm], i = b.i;
    b.t[i] = r[0]; b.SP[i] = r[1]; b.PV[i] = r[2]; b.MV[i] = r[3]; b.V[i] = r[4]; b.D[i] = d;
    b.i = (i + 1) % N; b.n = Math.min(b.n + 1, N);
  }
  function mulberry(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  // ---------------------------------------------------------------- události a ukazatele kvality
  function event(text) {
    S.events.push({ t: S.t, text: text });
    if (S.events.length > 200) S.events.shift();
  }
  function kpiReset(spStep) {
    for (const nm in S.loops) {
      const b = S.bufs[nm], j = at(b, b.n - 1);
      S.kpi[nm] = { t0: S.t, iae: 0, maxdev: 0, over: 0, step: spStep, out: S.t, travel: 0, mvPrev: b.MV[j] };
    }
  }
  function kpiStep(nm, r) {
    const k = S.kpi[nm], e = r[1] - r[2], h = CFG.h;
    k.iae += Math.abs(e) * h;
    k.maxdev = Math.max(k.maxdev, Math.abs(e));
    if (k.step) k.over = Math.max(k.over, -Math.sign(k.step) * e);                // PV za novou SP ve směru skoku
    const band = Math.max(k.step ? 0.02 * Math.abs(k.step) : 0, 0.2);
    if (Math.abs(e) > band) k.out = r[0];
    k.travel += Math.abs(r[3] - k.mvPrev); k.mvPrev = r[3];
  }

  // ---------------------------------------------------------------- porucha
  function distNow() {
    const D = S.dist, t = S.t, Pp = Math.max(D.Pp, CFG.h);
    switch (D.type) {
      case "ramp": return D.d0 + (D.A - D.d0) * Math.min(1, (t - D.t0) / Pp);
      case "sine": return D.A * Math.sin(2 * Math.PI * (t - D.t0) / Pp);
      case "random": D.x += -D.x / Pp * CFG.h + D.A * Math.sqrt(2 * CFG.h / Pp) * gauss(); return D.x;
      case "pulse": return t < D.pulseUntil ? D.A : 0;
      default: return D.A;
    }
  }
  let dLast = 0;
  function distChanged() { S.dist.d0 = dLast; S.dist.t0 = S.t; }

  // ---------------------------------------------------------------- simulace
  function advance(dtReal) {
    S.acc += dtReal * S.speed;
    let steps = Math.min(Math.floor(S.acc / CFG.h), 40000);
    S.acc -= steps * CFG.h;
    if (S.acc > 10 * CFG.h) S.acc = 0;                                   // počítač nestíhá → nedohánět
    const sp = P(S.sp), um = M(S.mv);
    for (let k = 0; k < steps; k++) {
      const d = distNow(); dLast = d;
      const dIn = S.dist.loc === "in" ? d / MR * 100 : 0, dOut = S.dist.loc === "out" ? d / PR * 100 : 0;
      S.t += CFG.h; S.tick++;
      for (const nm in S.loops) {
        const r = S.loops[nm].tick(sp, S.auto, um, dIn, dOut);
        kpiStep(nm, r);
        if (S.tick % REC === 0) push(nm, r, d);
      }
    }
  }

  // ---------------------------------------------------------------- DOM
  const old = root.querySelector(".pidlive");
  if (old) old.remove();
  const el = document.createElement("div");
  el.className = "pidlive";
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  const qm = (t) => (t ? `<span class="qm" role="img" aria-label="${esc(t)}" title="${esc(t)}">?</span>` : "");
  const card = (open, title, help, body) => `<details${open ? " open" : ""}><summary><span class="st">${title}</span>${qm(help)}</summary><section>${body}</section></details>`;
  const pu = (u) => (u ? " [" + u + "]" : "");
  el.innerHTML = `
  <div class="lvg">
  <div class="lvm">
    <div class="card bar">
      <button id="run"></button><button id="reset">↺ ${L.reset}</button>
      <span class="lab">${L.lspeed}</span><div class="segs" id="speed"></div>
      <span class="mono" id="tnow"></span><span class="sp"></span>
      <span class="chipbox"><span class="chip" id="chip"></span><span class="lab" id="chipt"></span></span>
    </div>
    <div class="card">
      <div class="chead"><span class="t">${L.chart}</span>${qm(L.desc + " " + L.help)}<span class="n" id="read"></span><span class="legend" id="legend"></span></div>
      <div class="cvwrap"><canvas id="cv" style="height:${Math.round(CFG.ch * 0.76)}px"></canvas><div id="tip"></div></div>
    </div>
    <div class="card">
      <div class="chead"><span class="t">${L.kpi_title}</span>${qm(L.h_kpi)}<span class="n">${L.kpi_note}</span></div>
      <table id="kpi" class="kpi"></table>
    </div>
    <div class="hint">${L.blk}</div>
  </div>
  <div class="lvs">
  ${card(true, L.sec_mode, L.h_mode, `
    <div class="tiles"><div class="tile sp"><div class="l">SP</div><div class="v" id="tsp"></div></div>
      <div class="tile pv"><div class="l">PV</div><div class="v" id="tpv"></div></div>
      <div class="tile mv"><div class="l">MV</div><div class="v" id="tmv"></div></div></div>
    <div class="lrow"><span class="lab">${L.lmode}</span><div class="segs" id="mode"></div></div>
    <div class="lrow" id="spbox"><span class="lab">SP${esc(pu(CFG.u_pv))}</span><div class="pair"><input type="range" id="sps"><input class="num" type="number" step="any" id="spn"></div></div>
    <div class="lrow" id="mvbox"><span class="lab">${L.mv_man}${esc(pu(CFG.u_mv))}</span><div class="pair"><input type="range" id="mvs"><input class="num" type="number" step="any" id="mvn"></div></div>
    <div class="hint">${L.mode_hint}</div>`)}
  ${card(true, L.lcmp, L.h_sets, `
    <label class="chk"><input type="checkbox" id="cmp"> ${L.compare}</label>
    <div class="lrow" id="setgrp"><span class="lab">${L.lset}</span><div class="segs" id="set"></div></div>
    <table class="sets" id="sets"></table>
    <div class="hint">${L.sets_note}</div>`)}
  ${card(true, L.sec_dist, L.h_dist, `
    <div class="lrow stack"><span class="lab">${L.dist_shape}</span><div class="segs" id="dtype"></div></div>
    <div class="lrow"><span class="lab">${L.dist_where}</span><select id="dloc"></select></div>
    <div class="lrow"><span class="lab" id="ldist"></span><div class="pair"><input class="num" type="number" step="any" id="ds"><button class="mini" id="d0" title="${esc(L.d0)}">0</button></div></div>
    <div class="lrow"><span class="lab" id="lpp"></span><input class="num" type="number" step="any" id="pps"></div>
    <div class="lrow"><span class="lab">${L.noise_pv}</span><input class="num" type="number" step="any" id="nzs"></div>
    <div class="lrow"><span></span><button id="pulse" class="trigger">${L.run_dist}</button></div>
    <div class="hint">${L.dist_note}</div>`)}
  ${card(false, L.sec_tune, "", `
        <div class="tune" id="tune"></div>
        <div class="btns"><button id="apply" class="primary">${L.apply}</button><button id="revert">${L.revert}</button></div>
        <div class="hint">${L.tune_hint}</div>`)}
  ${card(false, L.sec_meas, "", `
        <div class="sl"><div class="top"><span class="lab">${L.pvf}</span><span class="val" id="pfv"></span></div><input type="range" id="pfs"></div>
        <div class="hint">${L.meas_hint}</div>`)}
  ${card(false, L.sec_plant, "", `
        <div class="sl"><div class="top"><span class="lab">${L.pk}</span><span class="val" id="pkv"></span></div><input type="range" id="pks"></div>
        <div class="sl"><div class="top"><span class="lab">${L.pt}</span><span class="val" id="ptv"></span></div><input type="range" id="pts"></div>
        <div class="sl"><div class="top"><span class="lab">${L.pth}</span><span class="val" id="pthv"></span></div><input type="range" id="pths"></div>
        <div class="sl"><div class="top"><span class="lab">${L.stic}</span><span class="val" id="stv"></span></div><input type="range" id="sts"></div>
        <div class="hint">${L.plant_hint}</div>`)}
  ${card(false, L.sec_view, "", `
        <div class="lab">${L.window}</div><div class="segs" id="win"></div>
        <div class="btns"><button id="csv">⤓ CSV</button><button id="png">⤓ PNG</button></div>
        <div class="hint">${L.view_hint}</div>`)}
  </div>
  </div>`;
  root.appendChild(el);
  const $ = (id) => el.querySelector("#" + id);

  function seg(id, opts, cur, onPick) {
    const box = $(id); box.innerHTML = "";
    opts.forEach((o) => {
      const b = document.createElement("button");
      b.textContent = o[1]; b.className = "seg" + (String(o[0]) === String(cur) ? " on" : "");
      b.setAttribute("aria-pressed", String(o[0]) === String(cur));
      b.onclick = () => { onPick(o[0]); seg(id, opts, o[0], onPick); };
      box.appendChild(b);
    });
  }
  // posuvník (volitelně s číselným polem: obojí se synchronizuje)
  function slider(id, lo, hi, val, step, onInput, onChange, numId) {
    const s = $(id), n = numId ? $(numId) : null;
    s.min = lo; s.max = hi; s.step = step || (hi - lo) / 1000; s.value = val;
    if (n) { n.min = lo; n.max = hi; n.value = +val.toPrecision(6); }
    s.oninput = () => { if (n) n.value = +parseFloat(s.value).toPrecision(6); onInput(parseFloat(s.value)); labels(); };
    s.onchange = () => { if (onChange) onChange(parseFloat(s.value)); labels(); };
    if (n) n.onchange = () => {
      const v = Math.max(lo, Math.min(hi, parseFloat(n.value)));
      if (!isFinite(v)) { n.value = +parseFloat(s.value).toPrecision(6); return; }
      s.value = v; n.value = +v.toPrecision(6); onInput(v); if (onChange) onChange(v); labels();
    };
  }
  function setNum(id, v) { const n = $(id); if (n && document.activeElement !== n) n.value = +v.toPrecision(5); }
  const sgn = (v) => (v > 0 ? "+" : "") + fmt(v).replace("-", "−");
  function labels() {
    const du = S.dist.loc === "in" ? CFG.u_mv : CFG.u_pv;
    $("ldist").textContent = (S.dist.type === "random" ? L.dist_sigma : L.dist_size) + pu(du);
    $("mvs").disabled = $("mvn").disabled = S.auto; $("mvbox").classList.toggle("dis", S.auto);
    $("sps").disabled = $("spn").disabled = !S.auto; $("spbox").classList.toggle("dis", !S.auto);   // MAN: SP zašedlá, AUTO: MV zašedlá
    liveFields();
    const stepT = S.dist.type === "step";
    $("lpp").textContent = stepT ? L.dist_period : (L["pp_" + S.dist.type] || L.dist_period);
    $("pps").disabled = stepT; $("pps").placeholder = stepT ? L.period_hint : "";
    if (stepT) $("pps").value = ""; else setNum("pps", S.dist.Pp);
    $("pfv").textContent = fmt(S.pvf) + " s";
    $("pkv").textContent = "× " + S.plant.k.toFixed(2);
    $("ptv").textContent = "× " + S.plant.t.toFixed(2);
    $("pthv").textContent = "× " + S.plant.th.toFixed(2);
    $("stv").textContent = fmt(S.plant.stic) + " " + CFG.u_mv;
    $("run").textContent = S.run ? "⏸ " + L.pause : "▶ " + L.start;
    $("run").className = S.run ? "go" : "primary";
    $("setgrp").style.display = S.compare ? "none" : "";
    $("chip").textContent = (S.auto ? "✓ " : "") + (S.auto ? "AUTO" : "MAN");
    $("chip").className = "chip" + (S.auto ? "" : " man");
    $("chipt").textContent = S.compare ? L.both_run : (S.set === "1" ? L.set1 : L.set2);
    $("cmp").checked = S.compare;
    setsTable(); legend();
  }
  function setsTable() {
    const t2 = setOf("2"), t1 = CFG.sets["1"], v = (x) => (x === null || x === undefined ? "0" : fmt(x).replace("-", "−"));
    const row = (nm, c) => `<tr><td>${nm}</td><td>${v(c.Gain)}</td><td>${v(c.TI)}</td><td>${v(c.TD)}</td></tr>`;
    $("sets").innerHTML = `<tr><th></th><th>${L.gain}</th><th>TI [s]</th><th>TD [s]</th></tr>` + row(L.set1, t1) + row(L.set2, t2);
  }
  function legend() {
    if (!theme) return;
    const it = (name, c, w, dash) => `<span class="li"><i style="border-top:${w}px ${dash ? "dashed" : "solid"} ${c}"></i>${name}</span>`;
    $("legend").innerHTML = it("SP", theme.sp, 2, true) + (S.compare ? it(L.set1, theme.set1, 2, true) + it(L.set2, theme.set2, 3, false)
      : it("PV", theme.pv, 3, false) + it("MV", theme.mv, 3, false));
  }
  function liveFields() {
    // zašedlé pole ukazuje živou hodnotu: v AUTO MV ze simulace, v MAN žádanou hodnotu
    const nm = Object.keys(S.bufs)[0], b = nm && S.bufs[nm];
    if (S.auto && b && b.n) { const mv = EM(b.MV[at(b, b.n - 1)]); $("mvs").value = mv; setNum("mvn", mv); }
    if (!S.auto && b && b.n) { const sp = EP(b.SP[at(b, b.n - 1)]); $("sps").value = sp; setNum("spn", sp); }
  }
  function distInput() {
    const span = S.dist.loc === "in" ? MR / 2 : PR / 2, n = $("ds"), lo = S.dist.type === "random" ? 0 : -span;
    S.dist.pend = Math.max(lo, Math.min(span, S.dist.pend || 0));
    n.min = lo; n.max = span; n.value = +S.dist.pend.toPrecision(6);
    n.onchange = () => {
      const v = parseFloat(n.value);
      S.dist.pend = Math.max(lo, Math.min(span, isFinite(v) ? v : 0)); n.value = +S.dist.pend.toPrecision(6);
    };
  }
  function tuneInputs() {
    const box = $("tune"), base = CFG.sets["2"];
    box.innerHTML = "";
    [["Gain", L.gain, Math.abs(base.Gain) * 0.05, Math.abs(base.Gain) * 5],
     ["TI", "TI [s]", Math.max((base.TI || 100) * 0.05, CFG.h), (base.TI || 100) * 5],
     ["TD", "TD [s]", 0, Math.max(base.TD * 4, (base.TI || 100) / 2)]].forEach(([k, lab, lo, hi]) => {
      const sg = k === "Gain" && base.Gain < 0 ? -1 : 1;
      const d = document.createElement("div"); d.className = "sl";
      d.innerHTML = `<div class="top"><span class="lab">${lab}</span><input class="num" type="number" step="any"></div><input type="range">`;
      const num = d.querySelector(".num"), rng = d.querySelector("input[type=range]");
      const val = () => (S.tune[k] === null ? 0 : S.tune[k]);
      rng.min = lo; rng.max = hi; rng.step = (hi - lo) / 500; rng.value = Math.abs(val()); num.value = +val().toPrecision(4);
      const set = (v, fromNum) => {
        S.tune[k] = k === "Gain" ? sg * Math.abs(v) : Math.max(0, v);
        if (k === "TI" && S.tune.TI <= 0) S.tune.TI = null;
        if (!fromNum) num.value = +S.tune[k].toPrecision(4);
        else rng.value = Math.abs(S.tune[k] || 0);
        retune(); setsTable();
      };
      rng.oninput = () => set(parseFloat(rng.value), false);
      rng.onchange = () => { event(L.ev_tune); kpiReset(null); };
      num.onchange = () => { set(parseFloat(num.value) || 0, true); event(L.ev_tune); kpiReset(null); };
      box.appendChild(d);
    });
  }
  $("run").onclick = () => { S.run = !S.run; last = null; labels(); };
  $("reset").onclick = () => { reset(); labels(); };
  $("cmp").onchange = () => { S.compare = $("cmp").checked; reset(); labels(); };
  seg("speed", CFG.speeds.map((v) => [v, v + "×"]), S.speed, (v) => (S.speed = v));
  seg("set", [["1", L.set1], ["2", L.set2]], S.set, (v) => {
    const lp = S.loops[S.set]; S.loops = { [v]: lp }; S.bufs = { [v]: S.bufs[S.set] }; S.kpi = { [v]: S.kpi[S.set] };
    S.set = v; lp.setTuning(setOf(v)); event(L.ev_set + " " + (v === "1" ? L.set1 : L.set2)); kpiReset(null); labels();
  });
  seg("mode", [["AUTO", "AUTO"], ["MAN", "MAN"]], S.auto ? "AUTO" : "MAN", (v) => {
    S.auto = v === "AUTO";
    if (!S.auto) { const b = S.bufs[Object.keys(S.bufs)[0]]; S.mv = EM(b.MV[at(b, b.n - 1)]); $("mvs").value = S.mv; setNum("mvn", S.mv); }
    event(v); kpiReset(null); labels();
  });
  slider("sps", CFG.pv_lo, CFG.pv_hi, S.sp, PR / 1000, (v) => (S.sp = v), (v) => {
    const prevSp = S.lastSp === undefined ? EP(CFG.pv0) : S.lastSp, st = P(v) - P(prevSp); if (v === prevSp) return;
    S.lastSp = v;
    event("SP " + fmt(prevSp) + " → " + fmt(v)); kpiReset(st);
  }, "spn");
  slider("mvs", CFG.mv_lo, CFG.mv_hi, S.mv, MR / 1000, (v) => (S.mv = v), (v) => { event("MV " + fmt(v)); kpiReset(null); }, "mvn");
  distInput();
  // porucha: velikost se zadá do pole, působit začne až „Vyvolat poruchu“ (u pulzu vyšle jeden puls)
  $("pulse").onclick = () => {
    S.dist.A = S.dist.pend || 0; distChanged();
    if (S.dist.type === "pulse") S.dist.pulseUntil = S.t + S.dist.Pp;
    event(L.ev_dist + " " + sgn(S.dist.A)); kpiReset(null); labels();
  };
  $("d0").onclick = () => {
    S.dist.A = 0; S.dist.pend = 0; $("ds").value = 0; S.dist.pulseUntil = -1; distChanged();
    event(L.ev_dist + " 0"); kpiReset(null); labels();
  };
  seg("dtype", ["step", "ramp", "sine", "random", "pulse"].map((k) => [k, L["dt_" + k]]), S.dist.type, (v) => {
    S.dist.type = v; distInput(); distChanged(); labels();
  });
  [["in", L.loc_in], ["out", L.loc_out]].forEach((o) => {
    const op = document.createElement("option"); op.value = o[0]; op.textContent = o[1]; $("dloc").appendChild(op);
  });
  $("dloc").value = S.dist.loc;
  $("dloc").onchange = () => { S.dist.loc = $("dloc").value; distInput(); distChanged(); labels(); };
  $("pps").onchange = () => {
    const v = parseFloat($("pps").value);
    if (isFinite(v)) S.dist.Pp = Math.max(CFG.h * 2, Math.min(CFG.dist_pmax, v));
    distChanged(); labels();
  };
  $("nzs").value = +S.noise.toPrecision(6);
  $("nzs").onchange = () => {
    const v = parseFloat($("nzs").value);
    S.noise = Math.max(0, Math.min(0.05 * PR, isFinite(v) ? v : 0)); $("nzs").value = +S.noise.toPrecision(6);
    applyMeas(); event(L.noise_pv + " " + fmt(S.noise));
  };
  slider("pfs", 0, CFG.pvf_max, S.pvf, CFG.pvf_max / 500, (v) => { S.pvf = v; applyMeas(); }, () => event(L.pvf + " " + fmt(S.pvf)));
  slider("pks", 0.5, 2, S.plant.k, 0.01, (v) => { S.plant.k = v; applyPlant(); }, () => event(L.pk + " ×" + S.plant.k.toFixed(2)));
  slider("pts", 0.5, 2, S.plant.t, 0.01, (v) => { S.plant.t = v; applyPlant(); }, () => event(L.pt + " ×" + S.plant.t.toFixed(2)));
  slider("pths", 0.5, 2, S.plant.th, 0.01, (v) => { S.plant.th = v; applyPlant(); }, () => event(L.pth + " ×" + S.plant.th.toFixed(2)));
  slider("sts", 0, 0.05 * MR, S.plant.stic, MR / 5000, (v) => { S.plant.stic = v; applyStic(); }, () => event(L.stic + " " + fmt(S.plant.stic)));
  seg("win", WINDOWS.map((w) => [w, w === "auto" ? L.win_auto + " (" + (CFG.window / 60).toFixed(CFG.window < 600 ? 1 : 0) + " min)" : w / 60 + " min"]), S.win,
      (v) => { S.win = v; S.view = null; });
  tuneInputs();
  $("apply").onclick = () => {
    component.setTriggerValue("apply", { Gain: S.tune.Gain, TI: S.tune.TI, TD: S.tune.TD });
    event(L.ev_applied);
  };
  $("revert").onclick = () => { S.tune = Object.assign({}, CFG.sets["2"]); retune(); tuneInputs(); event(L.ev_tune); kpiReset(null); };
  $("csv").onclick = exportCsv;
  $("png").onclick = () => $("cv").toBlob((b) => download(b, "live_simulation.png"));

  function download(blob, name) {
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function exportCsv() {
    const nms = Object.keys(S.bufs), b0 = S.bufs[nms[0]];
    const head = [L.time, "SP"].concat(...nms.map((n) => ["PV " + L["set" + n], "MV " + L["set" + n]]), [L.dist_amp]);
    const rows = [head.join(";")];
    for (let k = 0; k < b0.n; k++) {
      const j = at(b0, k), row = [b0.t[j].toFixed(3), EP(b0.SP[j]).toPrecision(6)];
      nms.forEach((n) => { const b = S.bufs[n], jj = at(b, k); row.push(EP(b.PV[jj]).toPrecision(6), EM(b.MV[jj]).toPrecision(6)); });
      row.push(b0.D[j].toPrecision(6));
      rows.push(row.join(";").replace(/\./g, CFG.decimal));
    }
    download(new Blob(["﻿" + rows.join("\n")], { type: "text/csv" }), "live_simulation.csv");
  }

  // ---------------------------------------------------------------- graf
  const cv = $("cv"), g = cv.getContext("2d"), tip = $("tip");
  const MONO = "'IBM Plex Mono', ui-monospace, monospace";
  const LEFT = 46;                                                      // šířka sloupce s popisky osy y
  let yr = {}, mouse = null, drag = null, theme = null, themeAt = 0, last = null, raf = 0;
  function readTheme() {
    const app = document.querySelector(".stApp") || document.body, cs = getComputedStyle(app);
    const m = (cs.backgroundColor || "").match(/\d+(\.\d+)?/g) || [255, 255, 255];
    const dark = (0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2]) < 128;
    const old = theme && theme.dark;
    theme = Object.assign({ text: cs.color, muted: dark ? "#94a3b8" : "#52606d", dark: dark,
                            grid: dark ? "rgba(148,163,184,0.16)" : "rgba(100,116,139,0.14)",
                            frame: dark ? "#3b4a63" : "#c3ccd6", base: dark ? "#26324a" : "#e5e9ef" }, dark ? CFG.dark : CFG.light);
    // vzhled podle návrhu: SP černě čárkovaně, sada 1 šedá čárkovaně, sada 2 fialová, MV oranžově, události tyrkysově
    theme.sp = theme.text;
    theme.set1 = dark ? "#94a3b8" : "#9aa5b1"; theme.set2 = dark ? "#a78bfa" : "#7c3aed";
    theme.mv = dark ? "#fb923c" : "#c2410c"; theme.event = dark ? "#2dd4bf" : "#0d9488";
    el.style.setProperty("--acc", theme.acc);
    el.classList.toggle("dark", dark);
    if (old !== dark) legend();
  }
  function nice(lo, hi, n) {
    const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw / mag;
    const st = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, dec = Math.max(0, -Math.floor(Math.log10(st) + 1e-9)), out = [];
    for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9 * Math.abs(st); v += st) out.push([v, v.toFixed(dec).replace(".", CFG.decimal)]);
    return out;
  }
  function span() { return S.win === "auto" ? CFG.window : S.win; }
  function xRange() {                                                   // celé okno; čas „teď“ putuje zleva doprava, pak graf jede
    if (S.view) return S.view;
    const nm = Object.keys(S.bufs)[0], b = S.bufs[nm], tEnd = b.t[at(b, b.n - 1)], W = span();
    const t0 = Math.max(0, tEnd - W);
    return [t0, t0 + W];
  }
  function firstIdx(b, t) {           // binární hledání prvního vzorku s časem ≥ t
    let lo = 0, hi = b.n - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (b.t[at(b, mid)] < t) lo = mid + 1; else hi = mid; }
    return lo;
  }
  function draw() {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    if (!W) return;
    if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    g.font = "11px " + MONO; g.textBaseline = "middle";
    const nms = Object.keys(S.bufs), xr = xRange();
    const hasD = nms.some((n) => { const b = S.bufs[n]; for (let k = Math.max(0, b.n - 2000); k < b.n; k++) if (b.D[at(b, k)] !== 0) return true; return false; }) || S.dist.A !== 0;
    const left = LEFT, right = 6, top = 4, bottom = 26, gap = 8, plotW = W - left - right;
    const hAll = H - top - bottom - gap, fr = [0.645, 0.355];
    const col = (n) => (S.compare ? (n === "1" ? theme.set1 : theme.set2) : null);
    const dash1 = (n) => (S.compare && n === "1" ? [5, 3] : []);
    const pvSeries = [{ key: "SP", f: EP, c: theme.sp, w: 1.5, dash: [6, 4], nm: nms[0] }]
      .concat(nms.map((n) => ({ key: "PV", f: EP, c: col(n) || theme.pv, w: S.compare && n === "1" ? 1.8 : 2.4, dash: dash1(n), nm: n })));
    const mvSeries = nms.map((n) => ({ key: "MV", f: EM, c: S.compare && n === "1" ? theme.set1 : theme.mv, w: S.compare && n === "1" ? 1.6 : 2,
                                     dash: dash1(n), nm: n }))
      .concat(S.plant.stic > 0 && !S.compare ? [{ key: "V", f: EM, c: theme.mv, w: 1.2, dash: [2, 3], nm: nms[0] }] : []);
    const panels = [{ id: "pv", title: "PV", tc: theme.acc, series: pvSeries, minSpan: 0.02 * PR },
                    { id: "mv", title: "MV", tc: theme.mv, series: mvSeries, minSpan: 0.02 * MR }];
    let y0 = top;
    panels.forEach((pn, i) => { pn.y0 = y0; pn.h = hAll * fr[i]; y0 += pn.h + gap; });
    const X = (t) => left + (t - xr[0]) / Math.max(xr[1] - xr[0], 1e-9) * plotW;
    const bNow = S.bufs[nms[0]], tNow = bNow.t[at(bNow, bNow.n - 1)];
    const xNow = X(tNow), yTop = panels[0].y0, yBot = panels[1].y0 + panels[1].h;

    panels.forEach((pn) => {
      // rozsah osy y: rozšíření hned, zúžení plynule (graf neposkakuje)
      let lo = Infinity, hi = -Infinity;
      pn.series.forEach((s) => {
        const b = S.bufs[s.nm];
        for (let k = firstIdx(b, xr[0]); k < b.n; k++) { const j = at(b, k); if (b.t[j] > xr[1]) break; const v = s.f(b[s.key][j]); if (v < lo) lo = v; if (v > hi) hi = v; }
      });
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      const pad = Math.max((hi - lo) * 0.12, pn.minSpan / 2); lo -= pad; hi += pad;
      const cur = yr[pn.id];
      if (!cur || S.view) yr[pn.id] = [lo, hi];
      else { cur[0] = lo < cur[0] ? lo : cur[0] + (lo - cur[0]) * 0.04; cur[1] = hi > cur[1] ? hi : cur[1] + (hi - cur[1]) * 0.04; }
      const r = yr[pn.id], Y = (v) => pn.y0 + pn.h - (v - r[0]) / (r[1] - r[0]) * pn.h;
      pn.Y = Y;
      // oblast, která ještě nenastala (vpravo od „teď“), jemně zašedlá
      if (xNow < left + plotW) { g.fillStyle = theme.dark ? "rgba(148,163,184,0.07)" : "rgba(100,116,139,0.07)"; g.fillRect(xNow, pn.y0, left + plotW - xNow, pn.h); }
      g.strokeStyle = theme.grid; g.fillStyle = theme.muted; g.lineWidth = 1; g.setLineDash([]);
      nice(r[0], r[1], 4).forEach((tk) => {
        const y = Math.round(Y(tk[0])) + 0.5;
        if (y < pn.y0 + 4 || y > pn.y0 + pn.h - 2) return;
        g.beginPath(); g.moveTo(left, y); g.lineTo(left + plotW, y); g.stroke();
        g.textAlign = "right"; g.fillText(tk[1], left - 6, y);
      });
      g.strokeStyle = theme.frame; g.beginPath(); g.moveTo(left + 0.5, pn.y0); g.lineTo(left + 0.5, pn.y0 + pn.h); g.stroke();
      g.strokeStyle = theme.base; g.beginPath(); g.moveTo(left, Math.round(pn.y0 + pn.h) + 0.5); g.lineTo(left + plotW, Math.round(pn.y0 + pn.h) + 0.5); g.stroke();
      g.font = "600 11px " + (CFG.font || "sans-serif"); g.fillStyle = pn.tc; g.textAlign = "left"; g.fillText(pn.title, 0, pn.y0 + 6);
      g.font = "11px " + MONO;
      g.save(); g.beginPath(); g.rect(left, pn.y0, plotW, pn.h); g.clip();
      pn.series.forEach((s) => {
        const b = S.bufs[s.nm], i0 = Math.max(0, firstIdx(b, xr[0]) - 1);
        let i1 = b.n; const cnt = i1 - i0, stride = Math.max(1, Math.floor(cnt / (plotW * 1.5)));
        g.strokeStyle = s.c; g.lineWidth = s.w; g.setLineDash(s.dash || []); g.lineJoin = "round"; g.beginPath();
        let first = true;
        for (let k = i0; k < i1; k += stride) {
          let mn = Infinity, mx = -Infinity;
          for (let kk = k; kk < Math.min(k + stride, i1); kk++) { const v = s.f(b[s.key][at(b, kk)]); if (v < mn) mn = v; if (v > mx) mx = v; }
          const x = X(b.t[at(b, k)]);
          if (first) { g.moveTo(x, Y(mn)); first = false; } else g.lineTo(x, Y(mn));
          if (mx !== mn) g.lineTo(x, Y(mx));
          if (x > left + plotW + 2) break;
        }
        g.stroke();
      });
      g.restore();
    });
    // značky událostí (poruchy, změny SP…): tyrkysová čárkovaná čára přes oba grafy a popisek
    let lastX = -1e9;
    g.font = "11px " + (CFG.font || "sans-serif");
    S.events.forEach((ev) => {
      if (ev.t < xr[0] || ev.t > xr[1]) return;
      const x = Math.round(X(ev.t)) + 0.5;
      g.strokeStyle = theme.event; g.lineWidth = 1; g.setLineDash([3, 4]);
      g.beginPath(); g.moveTo(x, yTop); g.lineTo(x, yBot); g.stroke(); g.setLineDash([]);
      if (x - lastX > 70) {
        g.fillStyle = theme.event; g.textAlign = "left";
        g.fillText(ev.text, Math.min(x + 5, left + plotW - g.measureText(ev.text).width), yTop + 9);
        lastX = x;
      }
    });
    // „teď“: svislá černá čára a čas
    if (xNow >= left && xNow <= left + plotW + 1) {
      g.strokeStyle = theme.text; g.lineWidth = 2; g.setLineDash([]);
      g.beginPath(); g.moveTo(Math.round(xNow) + 0.5, yTop); g.lineTo(Math.round(xNow) + 0.5, yBot); g.stroke();
      g.fillStyle = theme.text; g.font = "11px " + (CFG.font || "sans-serif");
      const lab = L.now + " · " + clock(tNow), lw = g.measureText(lab).width;
      g.textAlign = xNow + lw + 12 > left + plotW ? "right" : "left";
      g.fillText(lab, g.textAlign === "left" ? xNow + 5 : xNow - 5, yTop + 9);
    }
    g.lineWidth = 1;
    // časová osa (minuty, u krátkého okna sekundy)
    const mins = (xr[1] - xr[0]) >= 120, sc = mins ? 60 : 1, unit = mins ? "min" : "s";
    g.font = "11px " + MONO; g.fillStyle = theme.muted; g.textAlign = "center";
    const endTxt = unit + (S.view ? " · " + L.zoomed : ""), ew = g.measureText(endTxt).width;
    nice(xr[0] / sc, xr[1] / sc, 6).forEach((tk) => {
      const x = left + (tk[0] * sc - xr[0]) / Math.max(xr[1] - xr[0], 1e-9) * plotW;
      if (x < left - 1 || x > left + plotW - ew - 14) return;
      g.fillText(tk[1], Math.max(x, left + 6), yBot + 13);
    });
    g.textAlign = "right"; g.fillText(endTxt, left + plotW, yBot + 13);
    // výběr pro přiblížení
    if (drag && drag.x1 !== undefined) {
      g.fillStyle = "rgba(100,116,139,0.15)";
      g.fillRect(Math.min(drag.x0, drag.x1), yTop, Math.abs(drag.x1 - drag.x0), yBot - yTop);
    }
    // hodnoty pod myší
    tip.style.display = "none";
    if (mouse && mouse.x >= left && mouse.x <= left + plotW && !drag) {
      const t = xr[0] + (mouse.x - left) / plotW * (xr[1] - xr[0]);
      const b0 = S.bufs[nms[0]], k = Math.min(b0.n - 1, firstIdx(b0, t));
      if (b0.n && t <= tNow + 1e-9) {
        const x = X(b0.t[at(b0, k)]);
        g.strokeStyle = theme.muted; g.setLineDash([]); g.beginPath(); g.moveTo(x + 0.5, yTop); g.lineTo(x + 0.5, yBot); g.stroke();
        let html = `<b>${fmt(b0.t[at(b0, k)])} s</b><br>SP ${fmt(EP(b0.SP[at(b0, k)]))}`;
        nms.forEach((n) => { const b = S.bufs[n], j = at(b, Math.min(k, b.n - 1)); html += `<br>PV${S.compare ? " " + L["set" + n] : ""} ${fmt(EP(b.PV[j]))} · MV ${fmt(EM(b.MV[j]))}`; });
        if (hasD) html += `<br>${L.dist_short} ${fmt(b0.D[at(b0, k)])}`;
        tip.innerHTML = html; tip.style.display = "block";
        tip.style.left = Math.min(mouse.x + 12, W - 190) + "px"; tip.style.top = (mouse.y + 12) + "px";
      }
    }
    // aktuální hodnoty a ukazatele kvality
    const b = bNow, j = at(b, b.n - 1);
    $("read").textContent = L.read.replace("{t}", fmt(b.t[j])).replace("{pv}", fmt(EP(b.PV[j]))).replace("{sp}", fmt(EP(b.SP[j]))).replace("{mv}", fmt(EM(b.MV[j])));
    $("tnow").textContent = "t = " + (b.t[j] < 60 ? fmt(b.t[j]) + " s" : clock(b.t[j]) + " min");
    $("tsp").textContent = tile(EP(b.SP[j])); $("tpv").textContent = tile(EP(b.PV[j]));
    $("tmv").textContent = tile(EM(b.MV[j])) + (CFG.u_mv ? " " + CFG.u_mv : "");
    // ukazatele: řádek = ukazatel, sloupec = sada; lepší (menší) hodnota v řádku zvýrazněná
    const K = {};
    nms.forEach((n) => {
      const kp = S.kpi[n]; if (!kp) return;
      const settled = S.t - kp.out > Math.max(0.1 * span(), 5 * CFG.h);
      K[n] = [[S.t - kp.t0, fmt(S.t - kp.t0) + " s"], [kp.iae * PR / 100, fmt(kp.iae * PR / 100)],
              [kp.maxdev * PR / 100, fmt(kp.maxdev * PR / 100) + " " + CFG.u_pv],
              [kp.step ? Math.max(0, kp.over) / Math.abs(kp.step) : NaN, kp.step ? fmt(100 * Math.max(0, kp.over) / Math.abs(kp.step)) + " %" : "–"],
              [settled ? kp.out - kp.t0 : NaN, settled ? fmt(kp.out - kp.t0) + " s" : "…"],
              [kp.travel * MR / 100, fmt(kp.travel * MR / 100) + " " + CFG.u_mv]];
    });
    const kp0 = S.kpi[nms[0]];
    const chg = kp0 ? S.events.filter((e) => Math.abs(e.t - kp0.t0) < 1e-9).map((e) => e.text).join(", ") || "–" : "–";
    const names = [L.kpi_change, "IAE [" + (CFG.u_pv || "PV") + " · s]", L.kpi_maxdev, L.kpi_over, L.kpi_settle, L.kpi_travel];
    let rows = "<tr><th></th>" + nms.map((n) => `<th>${L["set" + n]}</th>`).join("") + "</tr>";
    names.forEach((nmK, r) => {
      if (r === 0) {
        const since = K[nms[0]] ? L.kpi_since + ": " + clock(K[nms[0]][0][0]) : "";
        rows += `<tr><td title="${esc(since)}">${nmK}</td>` + nms.map((n, i) => `<td class="chg">${i === 0 ? esc(chg) : L.same}</td>`).join("") + "</tr>";
        return;
      }
      const vals = nms.map((n) => (K[n] ? K[n][r] : [NaN, "–"]));
      const fin = vals.map((v) => v[0]).filter((v) => isFinite(v));
      const best = fin.length > 1 && Math.min(...fin) !== Math.max(...fin) ? Math.min(...fin) : null;
      rows += `<tr><td>${nmK}</td>` + vals.map((v) => `<td class="${best !== null && v[0] === best ? "best" : ""}">${v[1]}</td>`).join("") + "</tr>";
    });
    $("kpi").innerHTML = rows;
  }

  // myš: hodnoty, přiblížení tažením (při pauze), dvojklik = zpět
  const pos = (e) => { const r = cv.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  cv.onmousemove = (e) => { mouse = pos(e); if (drag) drag.x1 = mouse.x; };
  cv.onmouseleave = () => { mouse = null; drag = null; };
  cv.onmousedown = (e) => { if (!S.run) drag = { x0: pos(e).x }; };
  cv.onmouseup = () => {
    if (drag && drag.x1 !== undefined && Math.abs(drag.x1 - drag.x0) > 8) {
      const xr = xRange(), W = cv.clientWidth - 70, f = (x) => xr[0] + (x - 58) / W * (xr[1] - xr[0]);
      S.view = [f(Math.min(drag.x0, drag.x1)), f(Math.max(drag.x0, drag.x1))];
    }
    drag = null;
  };
  cv.ondblclick = () => { S.view = null; };

  function frame(ts) {
    if (!theme || ts - themeAt > 1000) { readTheme(); themeAt = ts; }
    if (S.run && (document.hidden || cv.offsetParent === null || cv.clientWidth === 0)) {   // jiná záložka aplikace / prohlížeče: pauza
      S.run = false; last = null; labels();
    }
    if (S.run) {
      if (last !== null) { advance(Math.min((ts - last) / 1000, 0.25)); if (S.view) S.view = null; }
      last = ts;
    }
    draw();
    if (S.run) liveFields();
    raf = requestAnimationFrame(frame);
  }
  labels();
  raf = requestAnimationFrame(frame);
  const onResize = () => draw();
  window.addEventListener("resize", onResize);
  return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); };
}
