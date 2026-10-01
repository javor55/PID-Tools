"""
Automatické ukládání rozpracované práce do prohlížeče (IndexedDB – data zůstávají jen v počítači uživatele).

Při práci se projekt (včetně dat) ukládá nejvýš jednou za AUTOSAVE_S sekund a jen při změně. Po otevření aplikace
bez dat se zjistí, zda je uložená práce, a nabídne se „Obnovit“ (projekt se pak načte jako ze souboru).
"""
import datetime as _dt
import hashlib
import json
import time

import streamlit as st

from ..i18n import T
from .project import apply_project, gather_project, serialize_project
from .widgets import static_asset, v2_component

ss = st.session_state
AUTOSAVE_S = 20
def _component():
    return v2_component("pidtools_autosave", js=static_asset("autosave.js"))


def _trigger(name):
    v = ss.get("autosave_comp")
    return v.get(name) if isinstance(v, dict) else getattr(v, name, None)


def _on_found():
    ss["autosave_found"] = _trigger("found") or {}


def _on_project():
    raw = _trigger("project")
    if raw:
        try:
            apply_project(json.loads(raw))
            ss["autosave_restored"] = True
        except Exception as ex:
            ss["proj_err"] = str(ex)
    ss["autosave_mode"] = "idle"


def _mount(data):
    _component()(key="autosave_comp", data=data, on_found_change=_on_found, on_project_change=_on_project)


def offer_restore():
    """Úvodní obrazovka bez dat: zeptat se prohlížeče na uloženou práci a nabídnout obnovení."""
    mode = ss.get("autosave_mode") or ("probe" if "autosave_found" not in ss else "idle")
    _mount({"mode": mode})
    if mode in ("load", "clear"):
        ss["autosave_mode"] = "idle"
    found = ss.get("autosave_found") or {}
    if found.get("saved_at"):
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="center")
            c1.markdown(":material/history: " + T("as_found", t=found["saved_at"], n=found.get("loops") or "—"))
            c2.button(T("as_restore"), type="primary", icon=":material/restore:", width="stretch",
                      on_click=lambda: ss.update(autosave_mode="load"))
            c3.button(T("as_discard"), width="stretch", on_click=lambda: ss.update(autosave_mode="clear",
                                                                                  autosave_found={}))


def save(ctx):
    """Průběžné uložení (volá se na konci běhu s daty): nejvýš jednou za AUTOSAVE_S s a jen při změně."""
    if not ss.get("autosave_on", True):
        return
    if ss.get("autosave_mode") == "clear":
        _mount({"mode": "clear"})
        ss["autosave_mode"] = "idle"
        return
    now = time.time()
    data = {"mode": "idle"}
    if now - ss.get("_autosave_t", 0) >= AUTOSAVE_S:
        ss["_autosave_t"] = now
        try:
            js = serialize_project(gather_project(ctx, True))
            h = hashlib.sha1(js.encode("utf-8")).hexdigest()
            if h != ss.get("_autosave_hash"):
                ss["_autosave_hash"] = h
                ss["autosave_last"] = _dt.datetime.now().strftime("%H:%M:%S")
                from . import loops
                data = {"mode": "save", "json": js, "hash": h,
                        "saved_at": _dt.datetime.now().strftime("%d.%m.%Y %H:%M"),
                        "meta": {"loops": ", ".join(loops.name(i) for i in loops.ids())}}
        except Exception:
            pass
    _mount(data)
