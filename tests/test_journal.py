"""Deník ladění (E10, app vrstva): neměnnost snímku, porovnání, obnova a zpětný chod, převod live_runs, starý projekt, přílohy, report."""
import base64
import json
import os

import pytest

from pidtools.app import journal as jr
from pidtools.app import project as prj
from pidtools.app import report as rpt
from pidtools.app.domain.journal import FORMAT, Snapshot
from pidtools.app.workspace.loops import Project

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    p = Project()
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        p.apply_project(prj.load_project(f.read()))
    return p


@pytest.fixture()
def cs():
    """Texty v češtině (výchozí jazyk testů je angličtina); po testu zpět."""
    from pidtools import i18n
    i18n.set_lang_provider(None)
    i18n.set_lang("cs")
    yield
    i18n.set_lang("en")


@pytest.fixture()
def proj():
    return _load("golden/tic001.json")


def test_snapshot_content_and_immutability(proj):
    s = jr.create(proj, label="první", author="Novák")
    assert (s.id, s.v, s.status, s.author, s.kind) == ("j1", 1, "draft", "Novák", "manual")
    c = s.content
    assert c["model"]["code"] and c["results"]["2"]["Ms"] > 0 and c["controller"]["version"] == 1
    assert c["data"]["sources"] and len(c["data"]["sources"][0]["sha256"]) == 64
    assert {"block", "sets", "method", "scenario", "apc", "record"} <= set(c)
    assert s.verify() and s.history[0]["status"] == "draft"
    # pozdější změna pracovního prostoru snímek nemění; obsah ani otisk nejdou přepsat
    proj.state.set(set2_gain=123.0)
    assert s.content["sets"]["set2_gain"] != 123.0 and s.verify()
    with pytest.raises(AttributeError):
        s.content = {}
    with pytest.raises(AttributeError):
        s.sha256 = "x"
    s.content["sets"]["set2_gain"] = 5.0                  # úprava mimo aplikaci (v paměti) se pozná
    assert not s.verify()
    s2 = jr.create(proj)
    assert s2.v == 2 and s2.content["sets"]["set2_gain"] == 123.0


def test_status_notes_attachments(proj):
    s = jr.create(proj)
    jr.set_status(proj, s.id, "deployed", "Svoboda", "nasazeno v PCS 7")
    jr.set_status(proj, s.id, "verified")
    assert [h["status"] for h in s.history] == ["draft", "deployed", "verified"] and s.history[1]["author"] == "Svoboda"
    with pytest.raises(ValueError):
        jr.set_status(proj, s.id, "bogus")
    with pytest.raises(ValueError):
        jr.add_note(proj, s.id, "  ")
    jr.add_note(proj, s.id, "po výpadku čerpadla", "Novák")
    assert s.notes[0]["text"] == "po výpadku čerpadla"
    _, a = jr.add_attachment(proj, s.id, "foto.png", base64.b64encode(b"x" * 100).decode(), "image/png", "snímek")
    assert a["size"] == 100 and jr.attachment(proj, s.id, a["id"])["data"]
    with pytest.raises(ValueError):
        jr.add_attachment(proj, s.id, "big.bin", base64.b64encode(b"0" * (jr.MAX_ATTACHMENT + 1)).decode())
    with pytest.raises(ValueError):
        jr.add_attachment(proj, s.id, "bad.bin", "***")
    assert s.verify()                                      # stav, poznámky a přílohy obsah nemění


def test_compare(proj):
    a = jr.create(proj)
    proj.state.set(set2_gain=proj.state.get("set2_gain") * 2, set2_ti=77.0)
    b = jr.create(proj)
    d = jr.compare(proj, a.id, b.id)
    keys = {(r["section"], r["key"]) for r in d["rows"]}
    assert ("sets", "set2_gain") in keys and ("sets", "set2_ti") in keys
    assert not any(sec in ("model", "controller") for sec, _ in keys)        # nezměněno se neukazuje
    assert jr.compare(proj, a.id, a.id)["rows"] == []
    with pytest.raises(KeyError):
        jr.compare(proj, a.id, "j99")


def test_restore_roundtrip_is_nondestructive(proj):
    ws = proj.state
    g0, ti0 = ws.get("set2_gain"), ws.get("set2_ti")
    snap = jr.create(proj, label="základ")
    ws.set(set2_gain=g0 * 3, set2_ti=ti0 * 3)
    changed = (ws.get("set2_gain"), ws.get("set2_ti"))
    out = jr.restore(proj, snap.id)
    assert (ws.get("set2_gain"), ws.get("set2_ti")) == (g0, ti0)
    auto = out["autosave"]
    assert auto.kind == "restore" and auto.content["sets"]["set2_gain"] == changed[0] and snap.name in auto.label
    assert out["data_changed"] == [] and len(proj.journal) == 2
    jr.restore(proj, auto.id)                              # zpět na stav před obnovením
    assert (ws.get("set2_gain"), ws.get("set2_ti")) == changed


def test_project_file_roundtrip_and_old_project(proj):
    s = jr.create(proj, author="Novák")
    jr.add_attachment(proj, s.id, "a.txt", base64.b64encode(b"hello").decode())
    jr.set_status(proj, s.id, "deployed")
    text = prj.serialize_project(proj.to_project(include_data=False))
    d = json.loads(text)
    assert d["journal"][0]["format"] == FORMAT and d["version"] == 3
    p2 = Project()
    p2.apply_project(prj.load_project(text))
    s2 = p2.journal[0]
    assert s2.verify() and s2.sha256 == s.sha256 and s2.status == "deployed" and s2.attachments[0]["size"] == 5
    # starý projekt (v1, v3 bez klíče journal) se načte s prázdným deníkem
    for name in ("data/project_v1.json", "golden/tic001.json"):
        assert _load(name).journal == []
    # novější verze snímku se odmítne
    bad = dict(d["journal"][0], version=99)
    with pytest.raises(ValueError):
        Snapshot.from_dict(bad)


def test_live_runs_migrate_into_journal(proj):
    run = {"when": "2026-11-12T10:00:00", "struct": "ff", "kpi": {"1": {"iae": 1.5}, "2": {"iae": 0.9}}}
    proj.state.set(live_runs=[run, dict(run, when="2026-11-12T11:00:00", struct="pid")])
    text = prj.serialize_project(proj.to_project(include_data=False))
    assert "live_runs" in json.loads(text)["state"]
    p2 = Project()
    p2.apply_project(prj.load_project(text))                # načtení převede starší souhrny do deníku
    assert [s.kind for s in p2.journal] == ["live_migrated"] * 2
    assert p2.journal[0].created.startswith("2026-11-12T10:00") and p2.journal[0].content["live"]["kpi"]["2"]["iae"] == 0.9
    assert "live_runs" not in p2.state.settings
    assert "live_runs" not in json.loads(prj.serialize_project(p2.to_project()))["state"]
    s = jr.add_live(p2, run)                                # živý zápis „Zapsat výsledek do deníku“
    assert s.kind == "live" and s.verify()


def test_report_from_snapshot_and_sections(proj, cs):
    s = jr.create(proj, author="Novák")
    jr.set_status(proj, s.id, "deployed")
    proj.state.set(set2_gain=proj.state.get("set2_gain") * 2)
    jr.create(proj)
    ids = ["data", "controller", "scenario", "field", "history", "tuning"]
    html = jr.report_snapshot(proj, s.id, {"plant": "K2"}, ids)
    for title in ("Data a signály", "Regulátor a blok", "Scénář", "Ověření v provozu", "Historie změn"):
        assert title in html
    assert "v1" in html and "b-deployed" in html and "SHA-256" in html
    # report běžného stavu: nové sekce navíc, původní beze změny
    base = proj.report_html({"plant": "K2"}, rpt.SECTIONS, "cdn")
    ext = proj.report_html({"plant": "K2"}, rpt.SECTIONS + ["history", "data"], "cdn")
    assert "Historie změn" in ext and "Historie změn" not in base and "Data a signály" not in base
    assert [x["id"] for x in rpt.section_info()] == rpt.ALL_SECTIONS and set(rpt.SECTIONS) <= set(rpt.ALL_SECTIONS)
    # souhrnný report všech smyček
    rows = jr.summary_rows(proj, [{"name": proj.names()[0], "finding": "oscilace"}])
    assert "oscilace" in rpt.build_summary(rows, {"plant": "K2"})


def test_registry_sections_have_texts():
    from pidtools.i18n import TEXTS
    for sec in rpt.REGISTRY:
        for lang in ("cs", "en"):
            assert TEXTS[lang].get("rp_sec_" + sec.id) and TEXTS[lang].get("h_rp_sec_" + sec.id), (sec.id, lang)
