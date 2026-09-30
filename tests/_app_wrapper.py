"""Spouštěč aplikace pro testy: umožní vložit projekt (jako by ho uživatel nahrál) před během aplikace."""
import json
import os
import sys

import streamlit as st

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from pidtools.ui.project import apply_project  # noqa: E402

if "test_inject" in st.session_state:
    apply_project(json.loads(st.session_state.pop("test_inject")))
exec(compile(open(os.path.join(ROOT, "app.py"), encoding="utf-8").read(), "app.py", "exec"))
