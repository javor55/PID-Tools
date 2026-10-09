"""
Testy celé aplikace přes Streamlit AppTest: průchod všemi záložkami a funkcemi, uložení a obnova projektu,
přepnutí jazyka. Běží na ukázkových datech (hladina s měřeným přítokem).
"""
import json
import os

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from pidtools.core import MODELS
from pidtools.ui.project import serialize_project

WRAPPER = os.path.join(os.path.dirname(__file__), "_app_wrapper.py")
TIMEOUT = 900


def _dfs(app):
    """Tabulky posledního běhu (sdílená tabulka aplikace je vlastní komponenta – AppTest ji nečte)."""
    from types import SimpleNamespace
    return [SimpleNamespace(value=df) for _, df in (app.session_state["_tables"] if "_tables" in app.session_state
                                                    else [])]


def _main(at):
    """Hlavní záložky aplikace včetně „Projekt a report“ (vnořené záložky, např. pohledy v Ladění, se nepočítají)."""
    return [t for t in at.tabs if t.label[:1].isdigit() or t.label in ("Project & report", "Projekt a report")]


def _errors(at):
    """Výjimky a chybová hlášení aplikace (bez očekávaného hlášení o nestabilní výchozí sadě)."""
    exc = [x.message for x in at.exception]
    errs = [e.value for e in at.error if "Set 1" not in e.value]
    return exc + errs


def _button(at, label):
    return next(b for b in at.button if b.label == label)


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["src"] = "demo"
    at.run()
    at.session_state["c_d|demo"] = ["FI100.Pritok"]
    at.session_state["set1_gain"], at.session_state["set1_ti"] = -2.0, 200.0
    at.run()
    _button(at, "Identify").click().run()
    assert not _errors(at)
    return at


def test_start_without_data():
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception
    tabs = _main(at)                  # záložky jsou vidět i bez dat; Data nabízí nahrání, ostatní odkazují na Data
    assert len(tabs) == 8
    assert len(at.get("file_uploader")) == 2      # data (hlavní plocha Dat) + projekt (hlavička)
    assert any(i.value == "Load data in tab 1 · Data first." for i in at.info)


def test_identification(app):
    assert app.session_state["mcode"] in MODELS
    fits = [float(m.value.rstrip(" %")) for m in app.metric if m.label.startswith("Fit – identified")]
    assert fits and fits[0] > 95
    assert len(_main(app)) == 8


@pytest.mark.parametrize("method", ["SIMC", "iSIMC", "Lambda", "AMIGO", "AVG", "OPT"])
def test_tuning_methods(app, method):
    app.session_state[f"method|{app.session_state['mcode']}"] = method
    app.run()
    _button(app, "Calculate").click().run()          # návrh se počítá až na tlačítko (jako v desktopu)
    assert not _errors(app)
    assert app.session_state["sug_last"]["sig"]


@pytest.mark.parametrize("crit", ["MIGO", "IAE", "ISE", "ITAE", "OVS"])
def test_optimization_criteria(app, crit):
    app.session_state[f"method|{app.session_state['mcode']}"] = "OPT"
    app.session_state["opt_crit"] = crit
    app.run()
    assert not _errors(app)


def test_scenario_target_and_sets(app):
    app.session_state["opt_crit"], app.session_state["opt_target"], app.session_state["ctype"] = "IAE", "scen", "PID"
    app.run()
    app.run()
    _button(app, "Calculate").click().run()
    assert not _errors(app)
    _button(app, "Write to Set 2").click().run()
    assert app.session_state["tune_hist"][0]["set"] == 2
    for kind in ("in", "pv", "sp_in", "meas", "replay", "custom", "sp"):     # předvolby scénáře (jako desktop)
        app.session_state["scen_kind"] = kind
        app.run()
        assert not _errors(app), kind
    app.session_state["tun_view"] = "Frequency analysis"
    app.run()
    assert not _errors(app)
    app.session_state["tun_view"] = "Scenario response"
    app.run()
    assert not _errors(app)
    app.session_state["pvfilt"], app.session_state["mvrate"] = 2.0, 0.5
    app.run()
    assert not _errors(app)


def test_closed_loop_identification_web(app):
    """Režim „smyčka v AUTO“: po identifikaci jsou modely doladěné simulací smyčky se Set 1."""
    mc = app.session_state["mcode"]
    chosen = list(app.session_state["chosen"])
    app.session_state["id_mode"], app.session_state["chosen"] = "cl", [mc]
    app.run()
    _button(app, "Identify").click().run()
    assert not app.exception            # ukázková data nejsou z AUTO se Set 1 → sada 2 může vyjít nestabilní
    assert app.session_state["fit"]["res"][mc]["method"] == "cl"
    app.session_state["id_mode"], app.session_state["chosen"] = "open", chosen
    app.run()
    _button(app, "Identify").click().run()
    assert not _errors(app)


def test_loop_overview_web(app):
    """Přehled smyček: návrh smyček z názvů tagů a analýza bez chyb."""
    app.session_state["main_tab"] = [t.label for t in _main(app)][6]
    app.run()
    _button(app, "Analyse loops").click().run()
    assert not _errors(app)
    res = app.session_state["au_res"]["res"]
    assert res and res[0]["ok"] and res[0]["name"] == "LIC101"
    assert app.session_state["audit_loops"][0]["pv"] == "LIC101.PV"
    # seznam smyček: přidat, upravit (pole pod sebou), odebrat
    dkey = next(k for k in app.session_state if str(k).startswith("au_defs|"))
    n0 = len(app.session_state[dkey])
    _button(app, "Add").click().run()
    assert not _errors(app) and len(app.session_state[dkey]) == n0 + 1
    fk = next(k for k in app.session_state if str(k).startswith("au_f|") and str(k).endswith(f"|{n0}|integ"))
    app.session_state[fk] = True
    app.run()
    assert app.session_state[dkey][n0]["integ"] is True
    _button(app, "Remove").click().run()
    assert not _errors(app) and len(app.session_state[dkey]) == n0
    app.session_state["main_tab"] = [t.label for t in _main(app)][0]
    app.run()


def test_apc_more_structures_web(app):
    """Split range, VPC, poměr s křížovým omezením a RGA N×N: stránky bez chyb, s ukazateli."""
    app.session_state["main_tab"] = [t.label for t in _main(app)][4]
    for kind in ("split", "vpc", "ratio", "rga"):
        app.session_state["apc_kind"] = kind
        app.run()
        assert not app.exception, kind
    app.session_state["apc_kind"] = "split"
    app.run()
    assert any("b* =" in m.value for m in app.markdown)
    app.session_state["main_tab"] = [t.label for t in _main(app)][0]
    app.run()


def test_validation(app):
    app.session_state["pending_rngv"] = (2000.0, 3599.0)
    app.run()
    app.run()
    pred = [float(m.value.rstrip(" %")) for m in app.metric if m.label == "PV prediction fit"]
    assert pred and pred[0] > 90
    for mode, which in (("cl", "cur"), ("cl", "new"), ("pred", "cur")):
        app.session_state["val_mode"], app.session_state["val_which"] = mode, which
        app.run()
        assert not _errors(app)


def test_live_simulation(app):
    """Živá simulace běží v prohlížeči: stránka připojí komponentu s jádrem a konfigurací obou sad."""
    tabs = [t.label for t in _main(app)]
    app.session_state["main_tab"] = tabs[3]
    app.run()
    assert not _errors(app)
    comps = [c for c in app.main.get("bidi_component") if c.key == "live_sim"]
    assert len(comps) == 1
    doc = str(comps[0].proto)
    assert "pidtools_live_sim" in doc and "PIDLive" in doc and "sets" in doc and app.session_state["mcode"] in doc
    app.session_state["main_tab"] = tabs[0]
    app.run()


def test_model_tools(app):
    mc = app.session_state["mcode"]
    app.session_state["unc_n"] = 5
    _button(app, "Compute uncertainty").click().run()
    assert not _errors(app)
    ith = len(MODELS[mc]["params"]) - 1
    app.session_state[f"idf|{mc}|{ith}"], app.session_state[f"ed|{mc}|{ith}"] = False, 8.0   # θ neidentifikovat
    _button(app, "Refit").click().run()
    app.run()
    assert not _errors(app)
    assert app.session_state[f"ed|{mc}|{ith}"] == 8.0
    app.session_state["dist_level"], app.session_state["id_stic"], app.session_state["chosen"] = "high", True, ["I1D"]
    app.run()
    _button(app, "Identify").click().run()
    assert not _errors(app)


def test_lazy_tabs_and_comparison(app):
    """Grafy se posílají jen pro aktivní záložku; porovnání metod se počítá až po rozbalení."""
    labels = [t.label for t in _main(app)]
    n_charts = {}
    for lbl in labels:
        app.session_state["main_tab"] = lbl
        app.run()
        assert not _errors(app)
        n_charts[lbl] = len(app.get("plotly_chart"))
    assert n_charts[labels[0]] > 0 and n_charts[labels[-1]] == 0   # Data má grafy, Projekt žádné
    app.session_state["main_tab"] = labels[2]
    app.run()
    n_df = len(_dfs(app))
    app.session_state["cmp_open"] = True
    app.run()
    assert not _errors(app)
    assert len(_dfs(app)) == n_df + 1
    app.session_state["cmp_open"] = False
    app.session_state["main_tab"] = labels[0]
    app.run()


def test_guides(app):
    """Každá záložka má průvodce (v nápovědě „?“ hlavičky, pro aktivní záložku); tlačítko přepne záložku."""
    labels = [t.label for t in _main(app)]
    seen = {}
    for i, lbl in enumerate(labels):
        app.session_state["main_tab"] = lbl
        app.run()
        assert not _errors(app)
        heads = [m.value for m in app.markdown if m.value == "##### Purpose and steps"]
        assert len(heads) == 1, lbl
        seen[i] = [m.value for m in app.markdown]
    assert any("**Which model when**" in v for v in seen[1])
    assert any("**Which method when**" in v for v in seen[2])
    app.session_state["main_tab"] = labels[2]
    app.run()
    btn = next(b for b in app.button if b.label == "Go to Live simulation")
    btn.click().run()
    assert not _errors(app)
    assert app.session_state["main_tab"] == labels[3]
    app.session_state["main_tab"] = labels[0]
    app.run()


def test_other_tabs(app):
    for k, v in (("perf_compare", True), ("cas_om", "OPT")):
        app.session_state[k] = v
        app.run()
        assert not _errors(app)


def test_report_project_roundtrip_and_language(app):
    app.session_state["main_tab"] = [t.label for t in _main(app)][7]      # Projekt a report
    app.session_state["rep_plant"], app.session_state["rep_comment"] = "Kotelna <K2>", "a & b"
    app.run()
    _button(app, "Create report").click().run()
    assert not _errors(app)
    rep = app.session_state["report_html"]
    assert rep.startswith("<!doctype html>") and "Kotelna &lt;K2&gt;" in rep and "a &amp; b" in rep
    assert "PIDConL" in rep and "Ms" in rep and "Gain" in rep
    proj = json.loads(serialize_project(app.session_state["_proj_payload"]))
    app.session_state["main_tab"] = [t.label for t in _main(app)][0]
    app.run()
    assert proj["version"] == 2 and proj["data"] and proj["fit"]

    at2 = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at2.session_state["test_inject"] = json.dumps(proj)
    at2.run()
    at2.run()
    assert not at2.exception
    assert at2.session_state["src"] == "project"
    assert at2.session_state["mcode"] == app.session_state["mcode"]
    assert at2.session_state["set2_gain"] == pytest.approx(app.session_state["set2_gain"])
    # přepnutí jazyka zachová stav (model, sady, výběr sloupců)
    at2.session_state["lang"] = "cs"
    at2.run()
    assert not at2.exception
    assert at2.session_state["mcode"] == app.session_state["mcode"]
    assert any(t.label.startswith("4 · Živá") for t in _main(at2))


def test_legacy_project_v1():
    """Projekt ze starší verze (Set 1 v „current“, nové parametry v „new“) se načte a nové parametry jdou do Set 2."""
    path = os.path.join(os.path.dirname(__file__), "data", "project_v1.json")
    proj = json.load(open(path, encoding="utf-8"))
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.session_state["test_inject"] = json.dumps(proj)
    at.run()
    at.run()
    assert not at.exception
    assert at.session_state["set2_gain"] == pytest.approx(proj["new"]["Gain"])


def test_switch_source_keeps_settings():
    """
    Demo → Soubor (bez souboru, běh skončí st.stop) → Demo: bez chyb, nastavení i identifikace zůstanou.
    (Samotné vynulování widgetů nastávalo jen v prohlížeči – AppTest stav nevykreslených widgetů nezahazuje;
    ověřeno ručně přes Playwright.)
    """
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["src"] = "demo"
    at.run()
    _button(at, "Identify").click().run()
    before = {k: at.number_input(key=k).value for k in ("pv_hi", "mv_hi", "mvl_hi", "thmax", "samp")}
    assert all(v > 0 for v in before.values())
    at.session_state["src"] = "file"
    at.run()
    at.session_state["src"] = "demo"
    at.run()
    assert not _errors(at)
    assert {k: at.number_input(key=k).value for k in before} == before
    assert "fit" in at.session_state            # identifikace dema zůstala


def test_smith_template_values():
    """APC › Smithův prediktor: tabulka hodnot do šablony SmithPredictorControl (zesílení ve fyzikálních jednotkách)."""
    app = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    app.run()
    app.session_state["src"] = "demo"
    app.run()
    app.session_state["pv_hi"] = 200.0           # rozsah PV ≠ MV → zesílení v %/% a ve fyzikálních jednotkách se liší
    app.run()
    _button(app, "Identify").click().run()
    app.session_state["main_tab"] = [t.label for t in _main(app)][4]
    app.session_state["mcode"] = "P1D"            # demo je hladina (integrační) – tam se tabulka nezobrazí
    app.session_state["apc_kind"] = "smith"
    app.run()
    assert not _errors(app)
    tab = next(d.value for d in _dfs(app) if len(d.value) and "SmithModelGain (Mul04)" in d.value.iloc[:, 0].values)
    vals = dict(zip(tab.iloc[:, 0] + "." + tab.iloc[:, 1], tab.iloc[:, 2]))
    k = app.session_state["fit"]["res"]["P1D"]["p"][0]
    assert vals["SmithModelGain (Mul04).In2"] == pytest.approx(k * 2.0, rel=1e-3)
    assert {"SmithModelTimLag (Lag).LagTime", "SmithModelDeadti (DeadTime).DeadTime", "PV0 (Add04).In2",
            "PIDConL.Gain", "PIDConL.TI"} <= set(vals)
    assert any("Based on:" in c.value for c in app.caption)                  # z čeho výpočet vychází
    gen = next(d.value for d in _dfs(app) if len(d.value) and "Dead time θ" in d.value.iloc[:, 0].values)
    assert len(gen) >= 9
    app.session_state["apc_sm_method"] = "manual"         # ruční regulátor → přímo do šablony
    app.session_state["apc_sm_mg"], app.session_state["apc_sm_mti"] = 0.7, 33.0
    app.run()
    assert not _errors(app)
    tab = next(d.value for d in _dfs(app) if len(d.value) and "SmithModelGain (Mul04)" in d.value.iloc[:, 0].values)
    vals = dict(zip(tab.iloc[:, 0] + "." + tab.iloc[:, 1], tab.iloc[:, 2]))
    assert vals["PIDConL.Gain"] == pytest.approx(0.7) and vals["PIDConL.TI"] == pytest.approx(33.0)
    app.session_state["apc_sm_method"] = "OPT"
    app.run()
    assert not _errors(app)


def _nonlinear_data():
    """Nelineární proces (zesílení 0,7 → 1,9 podle MV, časová konstanta podle PV) se skoky na třech úrovních."""
    blocks = []
    for lv in (20.0, 50.0, 80.0):
        blocks += [(lv, 900), (lv + 5, 400), (lv - 5, 400), (lv, 400)]
    mv = np.concatenate([np.full(n, v) for v, n in blocks])
    n, h, th = len(mv), 1.0, 6
    K = lambda u: 0.3 + 0.02 * u                                                   # noqa: E731
    F = lambda u: 0.3 * u + 0.01 * u * u                                           # noqa: E731  ∫K
    y = np.zeros(n)
    y[0] = F(mv[0])
    for k in range(1, n):
        w = F(mv[max(k - 1 - th, 0)])
        a = np.exp(-h / (20 + 0.3 * y[k - 1]))
        y[k] = a * y[k - 1] + (1 - a) * w
    assert K(80) / K(20) > 2.5
    pv = y + np.random.default_rng(3).normal(0, 0.02, n)
    return np.arange(n) * h, pv, mv


def test_gain_scheduling_page():
    """APC › Gain scheduling: identifikace tří bodů, tabulka pro GainSched a simulace s menší IAE než jedna sada."""
    t, pv, mv = _nonlinear_data()
    proj = dict(version=2, fname="gs.csv", tag="TIC1", state={"mcode": "P1D"},
                map={"c_pv": "PV", "c_mv": "MV", "c_sp": "—", "c_d": [], "c_pos": "—"},
                ranges={"id": None, "val": None}, data={"cols": {"t_s": t.tolist(), "PV": pv.tolist(),
                                                                 "MV": mv.tolist()}})
    app = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    app.run()
    app.session_state["test_inject"] = json.dumps(proj)
    app.run()
    _button(app, "Identify").click().run()
    app.session_state["mcode"] = "P1D"
    app.run()
    _button(app, "Calculate").click().run()            # sada 2 = návrh SIMC (návrh se počítá na tlačítko)
    _button(app, "Write to Set 2").click().run()
    app.session_state["main_tab"] = [t_.label for t_ in _main(app)][4]
    app.session_state["apc_kind"] = "gainsched"
    for i, (a, b) in enumerate(((0, 2090), (2100, 4190), (4200, 6290)), start=1):
        app.session_state[f"gs_r{i}"] = (float(a), float(b))
    app.run()
    assert not _errors(app)
    _button(app, "Identify points").click().run()
    assert not _errors(app)
    pts = app.session_state["gs_pts"]
    assert len(pts) == 3
    gains = [q[3] for q in pts]                     # K v bodech roste s pracovním bodem
    assert gains[0] < gains[1] < gains[2] and gains[2] / gains[0] > 2
    tab = next(d.value for d in _dfs(app) if len(d.value) and "X1 … X3" in d.value.iloc[:, 0].values)
    xs = tab.iloc[0, 1:4].astype(float).values
    assert np.all(np.diff(xs) > 0)
    g = tab.iloc[1, 1:4].astype(float).values
    assert g[0] > g[2]                               # vyšší zesílení procesu → menší Gain regulátoru
    kp = next(d.value for d in _dfs(app) if len(d.value) and "SP step" in d.value.columns)
    assert kp["IAE – scheduler"].sum() < kp["IAE – one set"].sum()
    # režim X = ER: symetrická tabulka −E, 0, +E a srovnání se sadou 2 a řídicím pásmem
    app.session_state["gs_x"] = "er"
    app.session_state["gs_er_E"] = 4.0
    app.session_state["gs_er_k"] = 3.0
    app.run()
    assert any("Reduce k" in e for e in _errors(app))   # sada 2 (SIMC, τc = θ) je už ostrá → k = 3 nestabilní
    app.session_state["gs_er_k"] = 1.25
    app.run()
    assert not _errors(app)
    tab = next(d.value for d in _dfs(app) if len(d.value) and "X1 … X3 (ER)" in d.value.iloc[:, 0].values)
    assert list(tab.iloc[0, 1:4].astype(float)) == [-4.0, 0.0, 4.0]
    g = tab.iloc[1, 1:4].astype(float).values
    assert g[0] == pytest.approx(1.25 * g[1], rel=1e-3) and g[2] == pytest.approx(g[0])
    kp = next(d.value for d in _dfs(app) if len(d.value) and "Settled" in d.value.columns)
    assert len(kp) >= 2 and kp["Settled"].iloc[1] == "✓"
    # změna NormPV: body se přepočítají (X v jednotkách PV stejné), identifikace bodů není potřeba
    app.session_state["gs_x"] = "pv"
    app.run()
    x_before = [q[0] for q in app.session_state["gs_pts"]]
    app.session_state["pv_hi"] = 200.0
    app.run()
    assert not _errors(app)
    assert [q[0] for q in app.session_state["gs_pts"]] == pytest.approx([x / 2 for x in x_before])
    assert not any("Segments, ranges or the model changed" in w.value for w in app.warning)


def test_feedforward_in_apc(app):
    """Dopředná vazba: stav v Ladění, návrh a simulace v APC, promítnutí do sad a obnova z projektu."""
    assert any("Feedforward from measured disturbances is off" in c.value for c in app.caption)
    app.session_state["main_tab"] = [t.label for t in _main(app)][4]
    app.session_state["apc_kind"] = "ff"
    app.run()
    assert not _errors(app)
    kp = next(d.value for d in _dfs(app) if len(d.value) and "Max. PV deviation" in d.value.columns)
    iae_ = dict(zip(kp.iloc[:, 0], kp["IAE disturbance"]))
    assert iae_["Static FF"] < iae_["No FF"] and iae_["Dynamic FF"] < iae_["No FF"]
    app.session_state["ffuse|0"] = True
    app.run()
    assert not _errors(app)
    assert app.session_state["ff_state"][0]["use"]
    assert app.session_state["set2_ctrl"]["FF"][0] == pytest.approx(app.session_state["ff_state"][0]["gain"])
    g0 = app.session_state["ff_state"][0]["gain"]                  # ruční úprava → „znovu z modelu“ vrátí návrh
    kg = next(k for k in app.session_state if str(k).startswith("ffg|0|"))
    assert app.button(key="g_ffreset|0").disabled
    app.session_state[kg] = 2 * g0 + 1.0
    app.run()
    assert app.session_state["ff_state"][0]["gain"] == pytest.approx(2 * g0 + 1.0)
    app.button(key="g_ffreset|0").click().run()
    assert not _errors(app)
    assert app.session_state["ff_state"][0]["gain"] == pytest.approx(g0) and app.session_state["ff_state"][0]["use"]
    assert any("FFwdHiLim" in str(d.value.iloc[:, 0].values) for d in _dfs(app) if len(d.value))
    # simulace v Ladění: stejná sada 2 bez FF pro porovnání (scénář se skokem měřené poruchy)
    app.session_state["scen_kind"] = "meas"
    app.run()
    assert not _errors(app)
    kp = next(d.value for d in _dfs(app) if len(d.value) and "Set 2 without FF" in list(d.value.index))
    iae_ = dict(zip(kp.index, kp["IAE [%·s]"].astype(float)))
    assert iae_["Set 2"] != pytest.approx(iae_["Set 2 without FF"], rel=1e-3)   # FF se v simulaci projeví
    # obnova z projektu (ff v projektu → klíče widgetů)
    app.session_state["override_ff"] = [dict(use=True, gain=-0.5, dyn=True, lead=12.0, lag=4.0, delay=0.0)]
    app.run()
    st_ = app.session_state["ff_state"][0]
    assert st_["gain"] == pytest.approx(-0.5) and st_["dyn"] and st_["lead"] == pytest.approx(12.0)
    assert app.session_state["set2_ctrl"]["FF_LL"][0][0] == pytest.approx(12.0)
    app.session_state["ffuse|0"] = False
    app.session_state["apc_kind"] = "cascade"
    app.run()


def test_range_change_rescales_model():
    """Změna NormPV po identifikaci: model se přepočítá (K / 3), žádná výzva k nové identifikaci."""
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["src"] = "demo"
    at.run()
    at.session_state["c_d|demo"] = ["FI100.Pritok"]
    at.run()
    _button(at, "Identify").click().run()
    code = at.session_state["mcode"]
    k0 = at.session_state["fit"]["res"][code]["p"][0]
    kd0 = at.session_state["fit"]["res"][code]["pdl"][0][0]
    t0 = at.session_state["fit"]["res"][code]["p"][-1]
    at.session_state["pv_hi"] = 300.0
    at.run()
    assert not _errors(at)
    r = at.session_state["fit"]["res"][code]
    assert r["p"][0] == pytest.approx(k0 / 3) and r["pdl"][0][0] == pytest.approx(kd0 / 3)
    assert r["p"][-1] == pytest.approx(t0)
    assert at.session_state[f"ed|{code}|0"] == pytest.approx(k0 / 3)
    assert not any("changed since the last fit" in w.value for w in at.warning)


def _ff_example_app():
    """Uživatelská data (CV / MV / SP / DV, MV 125–135 %) načtená jako projekt s daty."""
    import pandas as pd
    df = pd.read_csv(os.path.join(os.path.dirname(__file__), "data", "ff_example.csv"))
    proj = dict(version=2, fname="ff.csv", tag="", state={},
                map={"c_pv": "CV", "c_mv": "MV", "c_sp": "SP", "c_d": ["DV"], "c_pos": "—"},
                ranges={"id": None, "val": None},
                data={"cols": {"t_s": (df["Sample#"] - 1).tolist(), "CV": df.CV.tolist(), "MV": df.MV.tolist(),
                               "SP": df.SP.tolist(), "DV": df.DV.tolist()}})
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["test_inject"] = json.dumps(proj)
    at.run()
    _button(at, "Identify").click().run()
    at.session_state["main_tab"] = [t.label for t in _main(at)][2]
    at.run()
    return at


def test_scenario_sp_from_to():
    """Scénář: SP z → na v jednotkách PV; po změně rozsahu výchozí skok neuvízne na 5 % starého rozsahu."""
    at = _ff_example_app()
    at.session_state["pv_hi"] = 400.0
    at.session_state["scen_kind"] = "custom"          # vlastní události: skok SP v tabulce se přepíše z „z → na“
    at.run()
    k0 = next(k for k in at.session_state if str(k).startswith("sim_sp0|"))
    k1 = next(k for k in at.session_state if str(k).startswith("sim_sp1|"))
    assert at.session_state[k0] == pytest.approx(370.0)
    at.session_state[k0], at.session_state[k1] = 360.0, 380.0
    at.run()
    assert not _errors(at)
    rows = at.session_state[next(k for k in at.session_state if str(k).startswith("scen_df|") and str(k).count("|") == 2)]
    assert rows[0][1] == "SP" and rows[0][3] == pytest.approx(20.0)
    sb = at.session_state["scen_built"]
    assert sb["sp"][0] * 4 == pytest.approx(360.0) and sb["sp"][-1] * 4 == pytest.approx(380.0)
    # rozsah MV (data 125–135) nebyl zadán → odhad z dat místo výchozích 0–100; zadaný NormPV 0–400 zůstal
    assert (at.session_state["mv_lo"], at.session_state["mv_hi"]) == (0.0, 200.0)
    assert (at.session_state["pv_lo"], at.session_state["pv_hi"]) == (0.0, 400.0)
    assert not any("lies outside the controller limits" in w.value for w in at.warning)


def test_range_typed_by_user_is_kept():
    """Rozsah zadaný v bloku (i 0–100 při datech mimo něj, např. podle PLC) odhad z dat nepřepíše."""
    at = _ff_example_app()
    assert (at.session_state["mv_lo"], at.session_state["mv_hi"]) == (0.0, 200.0)
    at.number_input(key="mv_hi").set_value(100.0).run()
    at.run()
    assert not _errors(at)
    assert (at.session_state["mv_lo"], at.session_state["mv_hi"]) == (0.0, 100.0)
    assert at.session_state["mv_rng_user"]


def test_opc_source_web():
    """Zdroj OPC UA (jen čtení): hledání tagů na testovacím serveru, historie → data aplikace."""
    pytest.importorskip("asyncua")
    from pidtools.app import opc
    url, stop = opc.test_server(48451)
    try:
        at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
        at.run()
        at.session_state["src"] = "opc"
        at.session_state["opc_url"] = url
        at.session_state["opc_q"] = "TIC200"
        at.run()
        _button(at, "Find").click().run()
        assert len(at.session_state["opc_found"]) == 3
        at.session_state["opc_pick"] = list(at.session_state["opc_found"])
        at.run()
        _button(at, "Read history").click().run()
        assert not at.exception
        assert at.session_state["opc_df"]["n"] == 3 and len(_main(at)) == 8
        assert at.session_state[next(k for k in at.session_state if str(k).startswith("c_pv|opc|"))] == "TIC200.PV"
    finally:
        stop()


def test_rows_as_samples_web():
    """Čas, který se nemění → co řádek, to vzorek s varováním; perioda řádku se dá nastavit (i v minutách)."""
    import numpy as np
    n = 300
    mv = np.where((np.arange(n) // 60) % 2, 60.0, 50.0)
    pv = 40 + np.convolve(mv - 50, np.ones(10) / 10, "same")
    proj = dict(version=2, fname="const_time.csv", tag="", state={},
                map={"c_pv": "CV", "c_mv": "MV1", "c_sp": "—", "c_d": [], "c_pos": "—"}, ranges={"id": None, "val": None},
                data={"cols": {"t_s": [0.0] * n, "CV": pv.tolist(), "MV1": mv.tolist()}})
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["test_inject"] = json.dumps(proj)
    at.run()
    assert not at.exception and len(_main(at)) == 8
    assert at.session_state["c_tim"] == "#row"
    assert any("not recognised" in w.value for w in at.warning)
    at.session_state["row_dt"] = 2.0
    at.session_state["read_manual"] = True        # jednotka času je v ručním nastavení čtení
    at.session_state["time_unit"] = "min"
    at.run()
    assert not at.exception
    assert any("2 min" in c.value for c in at.caption)


def test_set1_check_and_estimate_web():
    """Smyčka v AUTO: Set 1 nesedí se záznamem → upozornění; odhad Set 1 ze záznamu dá záporný Gain a kladné TI."""
    at = _ff_example_app()
    at.session_state["main_tab"] = [t.label for t in _main(at)][1]
    at.session_state["id_mode"] = "cl"
    at.run()
    assert not _errors(at)
    assert any("probably does not match" in w.value for w in at.warning)
    _button(at, "Estimate set 1 from the record").click().run()
    assert not _errors(at)
    assert at.session_state["set1_gain"] < 0 < at.session_state["set1_ti"] < 100
    assert any("estimated from the record" in i.value for i in at.info)


def test_time_charts_marked_for_chart_tools():
    """Grafy s časem na ose x dostanou značku pro chart_tools.js (popisky v min / h, měření)."""
    import plotly.graph_objects as go
    from pidtools.i18n import T
    from pidtools.ui.charts import _mark_time
    f = go.Figure(go.Scatter(x=[0, 1], y=[0, 1]))
    f.update_xaxes(title_text=T("time_s"))
    _mark_time(f)
    assert f.layout.meta["pt"]["time"]
    g = go.Figure(go.Scatter(x=[0, 1], y=[0, 1]))
    g.update_xaxes(title_text="MV [%]")
    _mark_time(g)
    assert g.layout.meta is None


def test_sim_length_unit_follows_process_speed():
    """Jednotka délky simulace: dokud ji uživatel nezvolí, podle délky (rychlý proces → s); zvolená zůstane."""
    at = _ff_example_app()
    assert not _errors(at)
    from pidtools.app.timefmt import auto_unit
    tend = next(at.session_state[k] for k in at.session_state if str(k).startswith("tend_r|"))
    u = at.session_state["sim_len_u"]
    assert u == auto_unit(tend * {"s": 1, "min": 60, "h": 3600}[u])
    at.selectbox(key="sim_len_u").set_value("h").run()
    at.run()
    assert at.session_state["sim_len_u"] == "h" and at.session_state["sim_len_u_set"]


def test_apc_reset_buttons_web(app):
    """„Původní hodnoty“ v APC: po ruční úpravě vrátí výchozí / vypočtené hodnoty a zase zešedne."""
    app.session_state["main_tab"] = [t.label for t in _main(app)][4]
    cases = (("vpc", "apc_vpc", "apc_vpc_f", 5.0), ("ratio", "apc_ra", "apc_ra_R", 1.2),
             ("split", "apc_sr", "apc_sr_gap", 0.0), ("smith", "apc_sm_err", "apc_sm_eth", 0))
    for kind, bkey, vkey, v0 in cases:
        app.session_state["apc_kind"] = kind
        app.run()
        assert not _errors(app), kind
        assert app.button(key=f"g_reset|{bkey}").disabled, kind
        app.session_state[vkey] = v0 + 7
        app.run()
        assert not app.button(key=f"g_reset|{bkey}").disabled, kind
        app.button(key=f"g_reset|{bkey}").click().run()
        assert not _errors(app), kind
        assert app.session_state[vkey] == pytest.approx(v0) and app.button(key=f"g_reset|{bkey}").disabled, kind


def test_per_input_segments_web():
    """Úseky podle vstupů: MV a porucha mají vlastní úseky, vyřazení dat, typ poruchy Auto, křížové ověření, projekt."""
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["src"] = "demo"
    at.run()
    at.session_state["win_mode"] = "inputs"
    at.session_state["chosen"] = ["I1D", "P1D"]
    at.session_state["wins|demo"] = {"MV": [[250.0, 1300.0], [2500.0, 3300.0]], "FI100.Pritok": [[850.0, 1750.0]]}
    at.session_state["dkind|FI100.Pritok"] = "auto"
    at.run()
    assert not _errors(at)
    assert any(w.key == "excl|demo|PV|lo" for w in at.number_input)      # vyřazení dat podle mezí
    _button(at, "Identify").click().run()
    assert not _errors(at)
    res = at.session_state["fit"]["res"]
    assert res["I1D"]["method"] == "win" and len(res["I1D"]["fits"]) >= 2 and res["I1D"]["fit"] > 80
    assert len(res["I1D"]["pdl"][0]) == 4                       # typ přenosu poruchy vybraný automaticky
    tab = next(d.value for d in _dfs(at) if "FIT [%]" in d.value.columns)
    assert "Cross-validation [%]" in tab.columns                 # porovnání typů přenosu podle návrhu
    _button(at, "Cross-validation").click().run()
    assert not _errors(at) and at.session_state["cv_res"]["res"]["I1D"]
    at.session_state["main_tab"] = [t.label for t in _main(at)][7]
    at.run()
    proj = json.loads(serialize_project(at.session_state["_proj_payload"]))
    assert proj["windows"]["wins"]["FI100.Pritok"] == [[850.0, 1750.0]]
    assert proj["fit"]["res"]["I1D"]["method"] == "win"
