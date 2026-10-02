"""Horní panel: nadpis, projekt, nápověda, nastavení a datová lišta (zdroj dat a souhrn)."""
import datetime as dt

import pandas as pd
import streamlit as st

from ... import __version__
from ...app import opc
from ...app.dataset import DEMO_SET1, demo_frame
from ...i18n import T
from .. import autosave, loops
from ..dataio import load_table
from ..project import load_project_file
from ..widgets import num, seg, sld

ss = st.session_state


def render(ctx):
    """Vykreslí horní panel a načte data do ctx.df (bez dat zastaví běh s výzvou k nahrání)."""
    hc1, hc2 = st.columns([3, 1.6], vertical_alignment="center")
    hc1.title(T("title"))
    with hc2:
        b1, b2, b3 = st.columns(3)
        with b1.popover(T("tb_project"), icon=":material/folder_open:", width="stretch"):
            st.text_input(T("loop_tag"), key="loop_tag", placeholder="LIC101", help=T("h_loop_tag"))
            st.file_uploader(T("proj_load"), type=["json"], key="proj_up", help=T("h_proj_load"),
                             on_change=load_project_file)
            if ss.get("proj_err"):
                st.error(T("err_proj", ex=ss.pop("proj_err")))
            st.caption(T("proj_help"))
        with b2.popover(T("tb_help"), icon=":material/help:", width="stretch"):
            st.markdown(f"**{T('guide_title')}**")
            st.markdown(T("guide_body"))
            st.divider()
            st.markdown(f"**{T('gloss_title')}**")
            st.markdown(T("gloss_body"))
            st.divider()
            st.markdown(f"**{T('about_title')}**")
            st.markdown(T("about_body", v=__version__))
        with b3.popover(T("tb_settings"), icon=":material/settings:", width="stretch"):
            st.radio("Jazyk / Language", ["cs", "en"], key="lang", horizontal=True,
                     format_func=lambda x: {"cs": "Čeština", "en": "English"}[x])
            st.caption(T("theme_hint"))
            ctx.H = sld(st, T("plot_height"), 300, 900, 460, "plot_h", step=20, help=T("h_plot_h"))

    with st.container(border=True):
        n_loops = len(loops.ids())  # od tří smyček má přepínač vlastní řádek pod zdrojem dat
        if n_loops <= 2:
            d1, d2, d3, d4 = st.columns([1.5, 1.6, 2.6, 1.6 if n_loops == 1 else 2.7], vertical_alignment="center")
        else:
            d1, d2, d3 = st.columns([1.5, 1.6, 4.2], vertical_alignment="center")
            d4 = st.container()
        src_opts = ["file", "demo"] + (["project"] if ss.get("proj", {}).get("data") else []) + \
            (["opc"] if opc.available() else [])
        if ss.get("src") not in src_opts:
            ss["src"] = "file"
        src = seg(d1, T("source"), src_opts, "file", "src", format_func=lambda x: T("src_" + x), help=T("h_source"),
                  label_visibility="collapsed") or "file"
        ctx.df, ctx.fname, ctx.ckey = None, "demo", "demo"
        ss["_src_prev"], ss["_src_now"] = ss.get("_src_now"), src
        if src == "project":
            ctx.df = pd.DataFrame(ss.proj["data"]["cols"])
            ctx.fname = f"project|{ss.proj.get('fname_tag', ss.proj.get('tag', ''))}|{len(ctx.df)}"
            ctx.ckey = f"{ctx.fname}|{ss.get('proj_hash')}"
            d2.caption(T("proj_data_caption", n=len(ctx.df)))
        elif src == "opc":
            _opc(d2)
            od = ss.get("opc_df")
            if od is not None:
                ctx.df = od["df"]
                ctx.fname = f"opc|{od['stamp']}|{len(ctx.df)}"
                ctx.ckey = ctx.fname
        elif src == "file":
            f = _file(d2)
            if f is not None:
                ctx.fname = f"{f['name']}|{f['size']}"
                ctx.ckey = f"{ctx.fname}|{f['id']}"
                try:
                    with st.spinner(T("loading")):
                        ctx.df = load_table(ctx.ckey, f["name"], f["data"])
                except Exception as ex:
                    st.error(T("err_read", ex=ex))
        else:
            ctx.df = demo_frame()
            if loops.active() == loops.ids()[0] and (ss.get("set1_gain", 1.0), ss.get("set1_ti", 100.0)) == (1.0, 100.0):
                # „současné“ parametry ukázkové smyčky (odtokový ventil → záporné zesílení), dokud je uživatel nezmění
                ss["set1_gain"], ss["set1_ti"], ss["set1_td"] = DEMO_SET1
                ss["_set1_demo"] = True
            d2.download_button(T("demo_dl"), ctx.df.to_csv(index=False, sep=";", decimal=","), "demo_level.csv",
                               "text/csv", icon=":material/download:", help=T("demo_desc"), width="stretch")
        if src != "demo" and ss.get("_set1_demo"):
            # ukázkové „současné“ parametry nepatří k vlastním datům – vrátit výchozí, pokud je uživatel nezměnil
            if (ss.get("set1_gain"), ss.get("set1_ti"), ss.get("set1_td", 0.0)) == (-2.0, 200.0, 0.0):
                ss["set1_gain"], ss["set1_ti"], ss["set1_td"] = 1.0, 100.0, 0.0
            ss["_set1_demo"] = False
        ctx.status_ph = d3.empty()
        _loop_switcher(d4)

    if ss.pop("autosave_restored", False):
        st.toast(T("as_restored"), icon=":material/restore:")
    if ctx.df is None:
        ctx.status_ph.caption(T("empty"))
        autosave.offer_restore()          # rozpracovaná práce uložená v prohlížeči
        st.info(T("empty"), icon=":material/upload_file:")
        st.stop()
    _swap_fit(ctx.fname)


def _opc(cont):
    """Zdroj OPC UA (jen čtení): server, hledání tagů, historie posledních hodin → dlouhá tabulka (Tag, Time, Value)."""
    od = ss.get("opc_df")
    with cont.popover(T("src_opc") + (f" · {od['n']}" if od else ""), icon=":material/lan:", width="stretch",
                      type="secondary" if od else "primary"):
        st.caption(T("opc_intro"))
        url = st.text_input(T("opc_url"), key="opc_url", value=ss.get("opc_url", "opc.tcp://localhost:4840"))
        c1, c2 = st.columns(2)
        user = c1.text_input(T("opc_user"), key="opc_user")
        pw = c2.text_input(T("opc_pw"), key="opc_pw", type="password")
        q = st.text_input(T("opc_search_ph"), key="opc_q")
        if st.button(T("opc_find"), key="g_opc_find", icon=":material/search:"):
            try:
                with opc.Connection(url, user or None, pw) as c, st.spinner(T("loading")):
                    ss["opc_found"] = {it.node_id: it.path for it in c.find(q)}
            except Exception as ex:
                st.error(T("opc_failed", e=ex))
        found = ss.get("opc_found") or {}
        pick = st.multiselect(T("opc_selected"), list(found), format_func=lambda n: found.get(n, n), key="opc_pick")
        hours = num(T("opc_web_hours"), "opc_hours", 8.0, min_value=0.01, max_value=24.0 * 365)
        if st.button(T("opc_history"), key="g_opc_hist", type="primary", disabled=not pick, icon=":material/download:"):
            try:
                end = dt.datetime.now(dt.timezone.utc)
                with opc.Connection(url, user or None, pw) as c, st.spinner(T("loading")):
                    h = c.history(pick, end - dt.timedelta(hours=hours), end + dt.timedelta(minutes=1))
                df = opc.to_frame(h, {n: found.get(n, n) for n in pick})
                if df.empty:
                    st.warning(T("opc_empty"))
                else:
                    ss["opc_df"] = dict(df=df, stamp=end.strftime("%Y%m%d%H%M%S"), n=df["Tag"].nunique())
                    st.rerun()
            except Exception as ex:
                st.error(T("opc_failed", e=ex))
        if od:
            st.caption(T("opc_web_loaded", n=len(od["df"]), k=od["n"]))


def _file(cont):
    """
    Nahraný soubor {name, size, id, data}. Pamatuje si ho i po přepnutí na demo / projekt (nahrávací widget se pak
    nevykresluje a Streamlit soubor zahodí); zapomene ho jen po odebrání souboru v nahrávacím poli.
    """
    keep = ss.get("_up_keep")
    cur = ss.get("up_file")
    with cont.popover(cur.name if cur is not None else keep["name"] if keep else T("tb_choose_file"),
                      icon=":material/upload_file:", width="stretch",
                      type="secondary" if cur is not None or keep else "primary"):
        f = st.file_uploader(T("upload"), type=["csv", "txt", "xlsx", "xls"], key="up_file")
        if f is None and keep:
            st.caption(T("up_kept", f=keep["name"]))
    if f is not None:
        if not keep or keep["id"] != f.file_id:
            keep = ss["_up_keep"] = dict(name=f.name, size=f.size, id=f.file_id, data=f.getvalue())
    elif keep and ss.get("_src_prev") == "file" and ss.get("_up_seen"):
        keep = ss["_up_keep"] = None      # soubor odebraný v nahrávacím poli
    ss["_up_seen"] = f is not None
    return keep


def _swap_fit(fname):
    """
    Identifikace patří k datům: při přepnutí zdroje (demo ↔ soubor ↔ projekt) se model předchozích dat odloží
    a obnoví se ten, který k novým datům už byl (jinak se ladění počítalo se starým modelem na nových datech).
    """
    prev = ss.get("_fit_src")
    ss["_fit_src"] = fname
    if prev is None or prev == fname or (ss.get("fit") or {}).get("key") == "__restore__":
        return
    store = ss.setdefault("_fit_by_src", {})
    if "fit" in ss:
        store[prev] = dict(fit=ss.pop("fit"), mcode=ss.get("mcode"))
    saved = store.pop(fname, None)
    if saved:
        ss["fit"] = saved["fit"]
        if saved["mcode"]:
            ss["mcode"] = saved["mcode"]


def render_status(ctx):
    """Souhrn dat v datové liště (po výběru sloupců a normování)."""
    tag_txt = ss.get("loop_tag") or ""
    status = T("status", n=len(ctx.t), ts=f"{ctx.Ts:.3g}", dur=f"{ctx.t[-1]:.0f}", pvr=f"{ctx.pv_lo:g}–{ctx.pv_hi:g}",
               mvr=f"{ctx.mv_lo:g}–{ctx.mv_hi:g}")
    ctx.status_ph.markdown(f"<div class='pid-status' style='margin:0'>{('<b>' + tag_txt + '</b> · ') if tag_txt else ''}"
                         f"{status}</div>", unsafe_allow_html=True)


def _loop_switcher(cont):
    """
    Smyčky projektu. S jednou smyčkou jen nenápadné „+ smyčka“; s více přepínač (platí pro všechny záložky)
    a menu pro přidání / odstranění.
    """
    lids = loops.ids()
    if len(lids) == 1:
        cont.button(T("loop_add"), icon=":material/add:", type="tertiary", on_click=loops.add, help=T("h_loop_add"))
        return
    if ss.get("loop_sel") not in lids:
        ss["loop_sel"] = loops.active()
    c1, c2 = cont.columns([5, 1] if len(lids) <= 2 else [12, 1], vertical_alignment="center")
    names = {i: loops.name(i) for i in lids}
    c1.segmented_control(T("loop"), lids, key="loop_sel", format_func=names.get, on_change=loops.on_select,
                         label_visibility="collapsed", help=T("h_loop_sel"), width="stretch")
    with c2.popover("", icon=":material/more_vert:", help=T("h_loop_menu")):
        st.button(T("loop_add"), icon=":material/add:", on_click=loops.add, width="stretch")
        st.button(T("loop_del", n=loops.name(loops.active())), icon=":material/delete:", width="stretch",
                  on_click=loops.remove, args=(loops.active(),))
        st.caption(T("loop_rename_hint"))
