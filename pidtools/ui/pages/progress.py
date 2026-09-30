"""Ukazatel postupu (vykreslí se nahoru do místa připraveného v app.py, až jsou známé stavy všech kroků)."""
import streamlit as st

from ...i18n import T

ss = st.session_state
STEPS = [("data", "prog_data"), ("model", "prog_model"), ("val", "prog_val"), ("tune", "prog_tune"),
         ("diag", "prog_diag"), ("save", "prog_save")]


def _next_hint(prog):
    for k_, _ in STEPS:
        v_ = prog.get(k_)
        if v_ == 0:
            continue
        if k_ == "data":
            return T("hint_data")
        if k_ == "model":
            return T("hint_model_none") if v_ is None else (T("hint_model_stale") if prog.get("model_stale")
                                                            else T("hint_model_low"))
        if k_ == "val":
            return T("hint_val_none") if v_ is None or prog.get("val_same") else T("hint_val_bad")
        if k_ == "tune":
            return T("hint_model_none") if v_ is None else (T("hint_tune_bad") if v_ == 2 else T("hint_tune"))
        if k_ == "diag":
            if v_ is None:
                continue
            return T("hint_diag")
        return T("hint_save")
    return None


def render(ctx, placeholder):
    prog = ctx.PROG
    prog["save"] = 0 if ss.get("proj_saved") else None
    chips = []
    for k_, lab_ in STEPS:
        v_ = prog.get(k_)
        cls_ = "sn" if v_ is None else f"s{v_}"
        ic_ = {None: "○", 0: "✓", 1: "⚠", 2: "✗"}[v_]
        chips.append(f"<span class='pid-chip {cls_}'>{ic_} {T(lab_)}</span>")
    placeholder.markdown(f"<div class='pid-prog'>{'<span class=pid-arrow>›</span>'.join(chips)}</div>"
                         f"<div class='pid-next'>{T('hint_next')}: {_next_hint(prog) or T('hint_done')}</div>",
                         unsafe_allow_html=True)
