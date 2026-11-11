/*
 * Obecný regulátor v prohlížeči (E1) – stejný interpret profilu jako pidtools/core/controller.py.
 * Čte stejný profil (`.pidctrl`, JSON, např. pidtools/controllers/presets/pcs7_pidconl.json); shoda s Pythonem
 * se hlídá testem tests/test_ctrl_engine_js.py (Node, odchylka < 1e-9). Vše v % normovacích rozsahů.
 *
 *   var prof = CtrlEngine.profile(jsonObject);
 *   var c = new CtrlEngine.Controller(prof, {Gain: 1, TI: 30, TD: 0, SampleTime: 1}, h);
 *   c.init(sp, y, u0, ff); c.step(sp, y, ff); c.track(sp, y, uMan, ff); c.setTuning(Gain, TI, TD);
 */
(function (root) {
  "use strict";

  /* ---- registry (stejné položky jako v Pythonu; rozšíření = přidat položku) */
  function Registry(name) { this.name = name; this.items = {}; }
  Registry.prototype.register = function (key, obj, planned) { this.items[key] = { obj: obj, planned: !!planned }; return obj; };
  Registry.prototype.get = function (key) {
    var it = this.items[key];
    if (!it) throw new Error(this.name + ": neznámá položka '" + key + "' (známé: " + Object.keys(this.items).sort().join(", ") + ")");
    if (it.planned) throw new Error(this.name + ": '" + key + "' je v návrhu a bude doplněno (fáze R3 / R4)");
    return it.obj;
  };
  var FORMS = new Registry("forma"), DEADBANDS = new Registry("mrtvé pásmo"), D_SOURCES = new Registry("zdroj D"),
    D_FILTERS = new Registry("filtr D"), ANTIWINDUPS = new Registry("anti-windup"), ALGORITHMS = new Registry("algoritmus"),
    NORMALISATIONS = new Registry("normování"), PV_FILTERS = new Registry("filtr PV");

  function form(fn, roles) { fn.roles = roles; return fn; }
  FORMS.register("ideal", form(function (a, b, c) { return [a, b, c]; }, ["Kc", "Ti", "Td"]));
  FORMS.register("parallel", form(function (kp, ki, kd) {
    if (kp === 0) throw new Error("paralelní forma: Kp = 0 nelze převést na ideální tvar");
    return [kp, (ki && ki > 0) ? kp / ki : null, kd / kp];
  }, ["Kp", "Ki", "Kd"]));
  FORMS.register("series", form(function (kc, ti, td) {
    if (ti === null || ti === undefined || !(ti > 0) || !isFinite(ti)) return [kc, ti, td];
    return [kc * (1.0 + td / ti), ti + td, ti * td / (ti + td)];
  }, ["Kc", "Ti", "Td"]));

  DEADBANDS.register("continuous", function (db) {
    return function (e) { return Math.abs(e) >= db ? e - (e > 0 ? 1.0 : -1.0) * db : 0.0; };
  });
  DEADBANDS.register("step", function (db) {
    return function (e) { return Math.abs(e) >= db ? e : 0.0; };
  });

  D_SOURCES.register("error", function () { return 0; });
  D_SOURCES.register("pv", function () { return 1; });
  D_SOURCES.register("error_or_pv", function (p) { return p.d_on_pv ? 1 : 0; });

  D_FILTERS.register("td_over_n", function (p, Td) {
    var N = Math.max(p.N === undefined ? 5.0 : p.N, 1e-6);
    return Td > 0 ? Td / N : 0.0;
  });
  D_FILTERS.register("none", function () { return 0.0; });
  D_FILTERS.register("fixed", function (p, Td) { return Td > 0 ? (p.Tf || 0.0) : 0.0; });

  ANTIWINDUPS.register("clamp_conditional", function (iOld, inc, uUn, u) {
    if (u === uUn || (uUn > u && inc < 0) || (uUn < u && inc > 0)) return iOld + inc;
    return iOld;
  });
  ANTIWINDUPS.register("back_calculation", function (iOld, inc, uUn, u, kAw) { return iOld + inc + (u - uUn) * kAw; });
  ANTIWINDUPS.register("none", function (iOld, inc) { return iOld + inc; });
  ANTIWINDUPS.register("external_reset", null, true);

  ALGORITHMS.register("position", true);
  ALGORITHMS.register("velocity", null, true);
  NORMALISATIONS.register("percent", true);
  NORMALISATIONS.register("engineering", null, true);
  PV_FILTERS.register("lag1", true);
  PV_FILTERS.register("none", false);

  /* ---- profil */
  function num(v) {
    if (typeof v === "string" && /^[+-]?inf$/.test(v)) return v[0] === "-" ? -Infinity : Infinity;
    return v === undefined ? null : v;
  }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  function Profile(data) {
    if (!data || data.format !== "pidctrl") throw new Error("není profil regulátoru (chybí format = 'pidctrl')");
    if (!(data.version >= 1)) throw new Error("profil regulátoru nemá platnou verzi");
    if (data.version > 1) throw new Error("profil verze " + data.version + " je novější než podporovaná 1");
    var st = data.structure, d = st.d || {};
    this.data = data; this.id = data.id;
    this.form = st.form || "ideal";
    this.formFn = FORMS.get(this.form);
    this.tuningRoles = this.formFn.roles;
    this.dSource = D_SOURCES.get(d.source || "error");
    this.dFilter = D_FILTERS.get(d.filter || "td_over_n");
    this.antiwindup = ANTIWINDUPS.get(st.antiwindup || "clamp_conditional");
    ALGORITHMS.get(st.algorithm || "position");
    NORMALISATIONS.get((st.normalisation || {}).kind || "percent");
    this.pvLag = !!PV_FILTERS.get((st.pv || {}).filter || "lag1");
    var db = (st.error || {}).deadband;
    this.dbModes = (db && db.modes) || {};
    this.dbOther = (db && db.other) || "step";
    var self = this;
    Object.keys(this.dbModes).map(function (k) { return self.dbModes[k]; }).concat([this.dbOther])
      .forEach(function (m) { DEADBANDS.get(m); });
    var out = st.output || {};
    this.useRate = !!out.rate_limit; this.useZone = !!out.control_zone;
    this.useSpRate = !!(st.sp || {}).rate_limit;
    this.params = data.params.map(function (p) {
      return { key: p.key, role: p.role, def: num(p.default), required: !!p.required, nullable: !!p.nullable,
        range: p.range || null, alias: p.alias || null };
    });
  }
  Profile.prototype.resolve = function (ctrl) {
    var out = {};
    this.params.forEach(function (p) {
      var v = ctrl[p.key];
      if ((v === undefined || v === null) && p.alias && ctrl[p.alias.key] !== undefined && ctrl[p.alias.key] !== null)
        v = ctrl[p.alias.key] ? p.alias["true"] : p.alias["false"];
      if (v === undefined || v === null) {
        if (p.nullable && has(ctrl, p.key)) { out[p.role] = null; return; }
        if (p.required) throw new Error("chybí parametr " + p.key);
        v = p.def;
      }
      out[p.role] = p.range ? Math.min(Math.max(v, p.range[0]), p.range[1]) : v;
    });
    return out;
  };

  /* ---- regulátor */
  function Controller(profile, ctrl, h) {
    var prof = profile instanceof Profile ? profile : new Profile(profile);
    this.profile = prof;
    var P = prof.resolve(ctrl);
    this._params = P;
    this.h = h;
    this.m = Math.max(1, Math.round(P.Ts / h));
    var Tc = this.Tc = this.m * h;
    this.lo = P.mv_lo; this.hi = P.mv_hi;
    this._db = null;
    if (P.deadband > 0) this._db = DEADBANDS.get(has(prof.dbModes, P.deadband_mode) ? prof.dbModes[P.deadband_mode] : prof.dbOther)(P.deadband);
    this.b = P.b; this._omb = 1.0 - this.b;
    this._dsrc = prof.dSource(P);
    var Tpv = prof.pvLag ? (P.pv_filter || 0.0) : 0.0;
    this._lag = Tpv > 0;
    this._apv = Tpv > 0 ? Math.exp(-h / Tpv) : 0.0;
    this._bpv = 1 - this._apv;
    this._rate = prof.useRate ? (P.mv_rate || 0.0) : 0.0;
    this._sprate = prof.useSpRate ? (P.sp_rate || 0.0) : 0.0;
    this._rlim = this._rate * Tc; this._slim = this._sprate * Tc;
    var cz = prof.useZone ? (P.con_zone || 0.0) : 0.0;
    this._cz = (cz > 0 && isFinite(this.lo) && isFinite(this.hi)) ? cz : 0.0;
    this._aw = prof.antiwindup;
    this._kAw = P.Tt ? Tc / P.Tt : 0.0;
    this.k = 0; this.dem = 0.0;
    this._setGains.apply(this, prof.tuningRoles.map(function (r) { return P[r]; }));
  }
  Controller.prototype._setGains = function (a, b, c) {
    var g = this.profile.formFn(a, b, c), Kc = g[0], Ti = g[1], Td = g[2], Tc = this.Tc;
    this.Kc = Kc; this.Ti = Ti; this.Td = Td;
    this.useI = Ti !== null && Ti !== undefined && isFinite(Ti) && Ti > 0;
    var Tf = this.Tf = this.profile.dFilter(this._params, Td);
    this._ki = this.useI ? Kc * Tc / Ti : 0.0;
    this._useD = Td > 0;
    this._ad = this._useD ? Tf / (Tf + Tc) : 0.0;
    this._kd = this._useD ? Kc * Td / (Tf + Tc) : 0.0;
    this._ksign = Kc >= 0 ? 1.0 : -1.0;
  };
  Controller.prototype.setTuning = function (a, b, c) {      // bez rázu výstupu (přepočet I složky)
    var e = this._err(), pOld = this._pTerm(e);
    this._setGains(a, b, c);
    this.I += pOld - this._pTerm(e);
  };
  Controller.prototype._err = function () {
    var e = this.spr - this.yf;
    return this._db !== null ? this._db(e) : e;
  };
  Controller.prototype._pTerm = function (e) { return this.Kc * (this.b * e - this._omb * this.yf); };
  Controller.prototype._xd = function (e) { return this._dsrc ? -this.yf : e; };
  Controller.prototype.init = function (sp, y, u0, ff) {
    ff = ff || 0.0;
    this.yf = y; this.spr = sp;
    var e = this._err();
    this.I = u0 - this._pTerm(e) - ff; this.D = 0.0;
    this.xdPrev = this._xd(e);
    this.u = this.uPrev = u0;
  };
  Controller.prototype.track = function (sp, y, uMan, ff) {
    ff = ff || 0.0;
    this.yf = this._lag ? this._apv * this.yf + this._bpv * y : y;
    this.spr = sp;
    var e = this._err();
    this.xdPrev = this._xd(e);
    this.D = 0.0;
    this.I = uMan - this._pTerm(e) - ff;
    this.u = this.uPrev = uMan;
    this.k += 1;
    return uMan;
  };
  Controller.prototype.step = function (sp, y, ff) {
    ff = ff || 0.0;
    var yf = this.yf = this._lag ? this._apv * this.yf + this._bpv * y : y;
    var k = this.k;
    this.k = k + 1;
    if (k % this.m) return this.u;
    var spr = this.spr;
    if (this._sprate > 0) {
      var lim = this._slim;
      spr = spr + Math.min(Math.max(sp - spr, -lim), lim);
    } else spr = sp;
    this.spr = spr;
    var e = spr - yf;
    if (this._db !== null) e = this._db(e);
    var Kc = this.Kc;
    var P = Kc * (this.b * e - this._omb * yf);
    var xd = this._dsrc ? -yf : e, D;
    if (this._useD) this.D = D = this._ad * this.D + this._kd * (xd - this.xdPrev);
    else D = this.D;
    this.xdPrev = xd;
    var uPrev = this.uPrev, u, rl;
    var cz = this._cz;
    if (cz > 0 && Math.abs(e) > cz) {                // regulační zóna
      u = e * this._ksign > 0 ? this.hi : this.lo;
      if (this._rate > 0) { rl = this._rlim; u = Math.min(Math.max(u, uPrev - rl), uPrev + rl); }
      this.I = u - P - D - ff;
      this.u = this.uPrev = u;
      return u;
    }
    var inc = this.useI ? this._ki * e : 0.0;
    var uUn = P + this.I + inc + D + ff;
    var dem = Math.abs(uUn - uPrev);
    if (dem > this.dem) this.dem = dem;
    u = Math.min(Math.max(uUn, this.lo), this.hi);
    if (this._rate > 0) { rl = this._rlim; u = Math.min(Math.max(u, uPrev - rl), uPrev + rl); }
    this.I = this._aw(this.I, inc, uUn, u, this._kAw);
    this.u = this.uPrev = u;
    return u;
  };

  var api = { Profile: Profile, Controller: Controller, profile: function (d) { return new Profile(d); },
    registries: { forms: FORMS, deadbands: DEADBANDS, dSources: D_SOURCES, dFilters: D_FILTERS, antiwindups: ANTIWINDUPS,
      algorithms: ALGORITHMS, normalisations: NORMALISATIONS, pvFilters: PV_FILTERS } };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CtrlEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
