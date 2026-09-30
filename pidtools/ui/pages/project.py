"""Záložka Projekt a report: uložení projektu smyčky a HTML reportu."""
import streamlit as st

from ...i18n import T
from ..project import build_project, build_report
from ..widgets import tog

ss = st.session_state


def render(ctx):
    with ctx.tabs["project"]:
        c1, c2 = st.columns(2, gap="large")
        tagn = (ss.get("loop_tag") or "smycka").replace(" ", "_")
        with c1:
            with st.container(border=True):
                st.markdown(f"#### {T('proj_title')}")
                st.caption(T("proj_save_help"))
                inc = tog(st, T("proj_include_data"), True, "proj_inc", help=T("h_proj_inc"))
                if st.button(T("proj_build"), icon=":material/inventory_2:"):
                    ss.proj_json = build_project(ctx, inc)
                if ss.get("proj_json"):
                    st.download_button(T("proj_save"), ss.proj_json, f"{tagn}_pid_projekt.json", "application/json",
                                       icon=":material/save:", type="primary",
                                       on_click=lambda: ss.update(proj_saved=True))
        with c2:
            with st.container(border=True):
                st.markdown(f"#### {T('rep_title')}")
                st.caption(T("rep_help"))
                author = st.text_input(T("rep_author"), key="rep_author")
                comment = st.text_area(T("rep_comment"), key="rep_comment", height=100)
                if st.button(T("rep_build"), icon=":material/description:"):
                    ss.report_html = build_report(ctx, author, comment)
                if ss.get("report_html"):
                    st.download_button(T("rep_dl"), ss.report_html, f"{tagn}_report.html", "text/html",
                                       icon=":material/download:", type="primary",
                                       on_click=lambda: ss.update(proj_saved=True))
