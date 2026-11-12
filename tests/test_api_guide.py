"""
API – průvodce záložky (E2): GET /workspaces/{wid}/guide/{tab}; kontrolní seznam se počítá živě ze stavu projektu,
obsah (postup, tabulky, slovníček) pochází z app.guides; APC FF / Smith / RGA mají kontrolní seznam a implementaci.
"""
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools import i18n  # noqa: E402
from pidtools.api import create_app  # noqa: E402
from pidtools.app import guides  # noqa: E402

TABS = ["data", "model", "tuning", "apc", "live", "diag", "loops", "project"]


def _wait(c, job, t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        st = c.get(f"/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return
        time.sleep(0.2)
    raise AssertionError("job timeout")


def _g(c, wid, tab, lang="cs"):
    r = c.get(f"/workspaces/{wid}/guide/{tab}", params={"lang": lang})
    assert r.status_code == 200, r.text
    return r.json()


def _find(g, text):
    return [x for x in g["checklist"] if text in x["text"]]


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def wid(client):
    w = client.post("/workspaces").json()["id"]
    yield w
    client.delete(f"/workspaces/{w}")


def test_unknown_tab_and_workspace(client, wid):
    assert client.get(f"/workspaces/{wid}/guide/nope").status_code == 404
    assert client.get("/workspaces/nope/guide/data").status_code == 404


@pytest.mark.parametrize("lang", ["cs", "en"])
def test_every_tab_has_shape_content_and_glossary(client, wid, lang):
    client.post(f"/workspaces/{wid}/data/demo")
    for tab in TABS:
        g = _g(client, wid, tab, lang)
        assert g["tab"] == tab and g["title"] and g["steps"], tab
        assert all(s["title"] for s in g["steps"])
        assert g["glossary"] and all(x["term"] and x["text"] for x in g["glossary"])
        assert all(x["ok"] in ("ok", "warn", "todo") for x in g["checklist"])
        assert g["checklist"], tab
    # texty podle jazyka požadavku
    assert _g(client, wid, "model", "cs")["title"] != _g(client, wid, "model", "en")["title"]


def test_tables_contain_markdown_tables(client, wid):
    for tab, title in (("model", "Který model kdy"), ("tuning", "Která metoda kdy"), ("apc", "Která struktura kdy")):
        g = _g(client, wid, tab)
        t = [x for x in g["tables"] if x["title"] == title]
        assert t and "|---|" in t[0]["md"], tab


def test_no_data_checklist_points_to_data_tab(client, wid):
    g = _g(client, wid, "tuning")
    assert [x["ok"] for x in g["checklist"]] == ["warn"]
    assert g["checklist"][0]["action"]["tab"] == "data"
    assert g["steps"] and g["tables"]                           # obsah je i bez dat


def test_data_tab_checks_from_state(client, wid):
    client.post(f"/workspaces/{wid}/data/demo")
    g = _g(client, wid, "data")
    loaded = _find(g, "Data načtena")
    assert loaded and loaded[0]["ok"] == "ok" and loaded[0]["action"] is None
    rng = _find(g, "Rozsah regulátoru")
    assert rng and rng[0]["ok"] == "todo"                       # výchozí 0–100
    assert rng[0]["action"]["tab"] == "tuning" and rng[0]["action"]["target"] == "set-pv_hi"
    client.patch(f"/workspaces/{wid}/settings", json={"pv_hi": 250.0})
    assert _find(_g(client, wid, "data"), "Rozsah regulátoru")[0]["ok"] == "ok"


def test_model_and_tuning_checks_follow_the_workspace(client, wid):
    client.post(f"/workspaces/{wid}/data/demo")
    g = _g(client, wid, "model")
    mdl = _find(g, "má identifikovaný model")
    assert mdl[0]["ok"] == "warn" and mdl[0]["action"] is None            # na záložce Model není kam odkazovat
    t = _g(client, wid, "tuning")
    assert t["checklist"][0]["ok"] == "warn" and t["checklist"][0]["action"]["tab"] == "model"
    assert len(t["checklist"]) == 1                                        # bez modelu zbytek nedává smysl

    client.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
    _wait(client, client.post(f"/workspaces/{wid}/identify").json())
    g = _g(client, wid, "model")
    assert _find(g, "Model ")[0]["ok"] in ("ok", "warn", "todo")
    fit = _find(g, "FIT")
    assert fit and fit[0]["ok"] in ("ok", "todo", "warn")
    assert _find(g, "identifikovaný") == [] or _find(g, "identifikovaný")[0]["ok"] == "ok"
    ok_model = [x for x in g["checklist"] if x["text"].startswith("Smyčka") and "model" in x["text"]]
    assert ok_model and ok_model[0]["ok"] == "ok"

    client.patch(f"/workspaces/{wid}/settings", json={"set1_gain": 1.0, "set1_ti": 100.0, "set2_gain": 1.0, "set2_ti": 100.0,
                                                      "set2_td": 0.0, "set1_td": 0.0})       # výchozí hodnoty = nezadáno
    t = _g(client, wid, "tuning")
    s1 = _find(t, "Sada 1")
    assert s1 and s1[0]["ok"] == "todo" and s1[0]["action"]["target"] == "set1-gain"
    ms = _find(t, "Ms =")
    assert ms and ms[0]["action"]["target"] == "method"
    client.patch(f"/workspaces/{wid}/settings", json={"set1_gain": 2.0, "set1_ti": 50.0})
    assert _find(_g(client, wid, "tuning"), "Sada 1")[0]["ok"] == "ok"
    client.patch(f"/workspaces/{wid}/settings", json={"set2_gain": 3.0})
    assert _find(_g(client, wid, "tuning"), "Sada 2")[0]["ok"] == "ok"
    live = _find(_g(client, wid, "tuning"), "Živé simulaci")
    assert live[0]["ok"] == "todo" and live[0]["action"]["tab"] == "live"


def test_apc_structures_have_checks_and_implementation(client, wid):
    client.post(f"/workspaces/{wid}/data/demo")
    client.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
    _wait(client, client.post(f"/workspaces/{wid}/identify").json())
    sm = client.get(f"/workspaces/{wid}/apc/smith").json()
    assert sm["checks"] and sm["checks"][0]["text"]
    ff = client.get(f"/workspaces/{wid}/apc/ff").json()
    assert ff["checks"] and "FfwdDisturbCompensat" in ff["impl_text"]
    rga = client.get(f"/workspaces/{wid}/apc/rga").json()
    assert rga["checks"] and rga["impl_text"]


# ---- čisté funkce app vrstvy
def test_parsers_split_content():
    md = "**K čemu:** něco.\n\n**Postup**\n1. **Data** – nahrajte soubor.\n2. Zkontrolujte graf model vs. data a rezidua.\n3. Hotovo: uložte."
    assert guides.intro_of(md).startswith("**K čemu:**") and "Postup" not in guides.intro_of(md)
    st = guides.parse_steps(md)
    assert st[0] == {"title": "Data", "text": "nahrajte soubor."}
    assert "vs. data" in st[1]["title"] or "vs. data" in st[1]["text"]
    assert st[2]["title"] == "Hotovo" and st[2]["text"] == "uložte."
    secs = guides.parse_sections("**A**\n| x |\n|---|\n| 1 |\n\n**B**\n- b", "def")
    assert [s["title"] for s in secs] == ["A", "B"] and "|---|" in secs[0]["md"]
    assert guides.parse_sections("| x |\n|---|", "def")[0]["title"] == "def"
    assert guides.parse_glossary("- **PV** – regulovaná veličina\n- bez pojmu") == [
        {"term": "PV", "text": "regulovaná veličina"}, {"term": "", "text": "bez pojmu"}]


def test_action_info_and_status():
    assert guides.action_info(None) is None
    assert guides.action_info("tab:model")["tab"] == "model"
    a = guides.action_info("add_loop")
    assert a["tab"] == "data" and a["target"] == "add-loop"
    assert guides.action_info("loop:2:data")["target"] == "loop:2"
    assert guides.action_info(guides.Act("tab:tuning", "set1-gain", "X")) == {"tab": "tuning", "target": "set1-gain", "label": "X"}
    assert [guides.check_status(x) for x in (True, False, None)] == ["ok", "warn", "todo"]
    assert isinstance(guides.Act("tab:tuning", "x"), str)       # starší rozhraní s ním pracují jako s řetězcem


def test_guide_texts_exist_in_both_languages():
    for tab in TABS:
        k = guides.tab_key(tab)
        for lang in ("cs", "en"):
            assert i18n.TEXTS[lang].get(f"tg_{k}_what"), (tab, lang)
