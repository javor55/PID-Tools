"""
Záložka Projekt a report.

Projekt = soubor s celou prací (všechny smyčky, modely, ladění, volitelně data) pro pokračování později nebo předání
kolegovi; navíc se práce průběžně ukládá do prohlížeče. Report = protokol z ladění (HTML, tisk do PDF) s tím,
co nastavit v PCS 7, robustností a očekávaným chováním původních a nových parametrů.
"""
import datetime as _dt
import re

import streamlit as st

from ...i18n import T
from .. import loops
from ..project import gather_project, serialize_project
from ..report import SECTIONS, STATUSES, build_report
from ..widgets import seg, tog

ss = st.session_state


def _base_name():
    """Základ názvu souboru: zařízení nebo názvy smyček + datum."""
    base = ss.get("rep_plant") or "_".join(loops.name(i) for i in loops.ids()) or "pid"
    return re.sub(r"[^\w.-]+", "_", base, flags=re.UNICODE).strip("_")[:60] + f"_{_dt.date.today():%Y-%m-%d}"


def render(ctx):
    with ctx.tabs["project"]:
        st.markdown(T("pj_intro"))
        if ctx.tabs["project"].open is False:   # sestavení projektu a reportu jen na otevřené záložce
            return
        c1, c2 = st.columns([1, 1.35], gap="large")
        base = _base_name()
        with c1:
            with st.container(border=True):
                st.markdown(f"#### {T('proj_title')}")
                st.caption(T("proj_save_help"))
                inc = tog(st, T("proj_include_data"), True, "proj_inc", help=T("h_proj_inc"))
                payload = gather_project(ctx, inc)
                ss["_proj_payload"] = payload
                st.download_button(T("proj_save"), lambda p=payload: serialize_project(p), f"{base}_projekt.json",
                                   "application/json", icon=":material/save:", type="primary", width="stretch",
                                   on_click="ignore")
                st.caption(T("pj_load_hint"))
            with st.container(border=True):
                st.markdown(f"#### {T('as_title')}")
                on = tog(st, T("as_on"), True, "autosave_on", help=T("h_as_on"))
                if on and ss.get("autosave_last"):
                    st.caption(T("as_last", t=ss["autosave_last"]))
                st.caption(T("as_help"))
                st.button(T("as_clear"), icon=":material/delete:",
                          on_click=lambda: ss.update(autosave_mode="clear", _autosave_hash=None, autosave_last=None))
        with c2:
            with st.container(border=True):
                st.markdown(f"#### {T('rep_title')}")
                st.caption(T("rep_help"))
                m1, m2 = st.columns(2)
                m1.text_input(T("rp_plant"), key="rep_plant", placeholder=T("rp_plant_ph"))
                m2.text_input(T("rp_author"), key="rep_author")
                seg(st, T("rp_status"), STATUSES, "draft", "rep_status", format_func=lambda x: T("rp_st_" + x))
                st.text_area(T("rep_comment"), key="rep_comment", height=90, placeholder=T("rp_comment_ph"))
                if "rep_sections" not in ss:
                    ss["rep_sections"] = list(SECTIONS)
                st.pills(T("rp_sections"), SECTIONS, selection_mode="multi", key="rep_sections",
                         format_func=lambda x: T("rp_sec_" + x), help=T("h_rp_sections"))
                charts = seg(st, T("rp_charts"), ["inline", "cdn"], "inline", "rep_charts",
                             format_func=lambda x: T("rp_ch_" + x), help=T("h_rp_charts")) or "inline"
                if st.button(T("rep_build"), icon=":material/description:"):
                    with st.spinner(T("rp_building")):
                        meta = {k: ss.get("rep_" + k) for k in ("plant", "author", "status", "comment")}
                        ss.report_html = build_report(ctx, meta, ss.get("rep_sections") or [], charts)
                if ss.get("report_html"):
                    st.download_button(T("rep_dl"), ss.report_html, f"{base}_protokol.html", "text/html",
                                       icon=":material/download:", type="primary", on_click="ignore")
                    st.caption(T("rp_pdf_hint"))
        if ss.get("report_html"):
            with st.expander(T("rp_preview"), expanded=True, icon=":material/preview:"):
                st.iframe(ss.report_html, height=720)
