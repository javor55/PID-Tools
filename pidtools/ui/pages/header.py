"""Horní panel: nadpis, projekt, nápověda, nastavení a datová lišta (zdroj dat a souhrn)."""
import pandas as pd
import streamlit as st

from ...core import demo_data
from ...i18n import T
from .. import autosave, loops
from ..dataio import load_table
from ..project import load_project_file
from ..widgets import seg, sld

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
        src_opts = ["file", "demo"] + (["project"] if ss.get("proj", {}).get("data") else [])
        if ss.get("src") not in src_opts:
            ss["src"] = "file"
        src = seg(d1, T("source"), src_opts, "file", "src", format_func=lambda x: T("src_" + x), help=T("h_source"),
                  label_visibility="collapsed") or "file"
        ctx.df, ctx.fname, ctx.ckey = None, "demo", "demo"
        if src == "project":
            ctx.df = pd.DataFrame(ss.proj["data"]["cols"])
            ctx.fname = f"project|{ss.proj.get('fname_tag', ss.proj.get('tag', ''))}|{len(ctx.df)}"
            ctx.ckey = f"{ctx.fname}|{ss.get('proj_hash')}"
            d2.caption(T("proj_data_caption", n=len(ctx.df)))
        elif src == "file":
            cur_f = ss.get("up_file")
            with d2.popover(cur_f.name if cur_f is not None else T("tb_choose_file"), icon=":material/upload_file:",
                            width="stretch", type="secondary" if cur_f is not None else "primary"):
                f = st.file_uploader(T("upload"), type=["csv", "txt", "xlsx", "xls"], key="up_file")
            if f is not None:
                ctx.fname = f"{f.name}|{f.size}"
                ctx.ckey = f"{ctx.fname}|{f.file_id}"
                try:
                    with st.spinner(T("loading")):
                        ctx.df = load_table(ctx.ckey, f.name, f.getvalue())
                except Exception as ex:
                    st.error(T("err_read", ex=ex))
        else:
            t_, sp_, pv_, mv_, q_ = demo_data()
            ctx.df = pd.DataFrame({"Cas": t_, "LIC101.SP": sp_, "LIC101.PV": pv_, "LIC101.MV": mv_, "FI100.Pritok": q_})
            d2.download_button(T("demo_dl"), ctx.df.to_csv(index=False, sep=";", decimal=","), "demo_level.csv",
                               "text/csv", icon=":material/download:", help=T("demo_desc"), width="stretch")
        ctx.status_ph = d3.empty()
        _loop_switcher(d4)

    if ss.pop("autosave_restored", False):
        st.toast(T("as_restored"), icon=":material/restore:")
    if ctx.df is None:
        ctx.status_ph.caption(T("empty"))
        autosave.offer_restore()          # rozpracovaná práce uložená v prohlížeči
        st.info(T("empty"), icon=":material/upload_file:")
        st.stop()


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
