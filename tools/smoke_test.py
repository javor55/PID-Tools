"""
Smoke test of a built offline package, run with its own embedded Python from the app folder:

    PID-Tools\\python\\python.exe ..\\..\\tools\\smoke_test.py      (cwd = PID-Tools\\app)

Checks the computation core and the whole app on demo data (Streamlit AppTest, no browser).
"""
import os
import sys

sys.path.insert(0, os.getcwd())

from pidtools.core import demo_data, fit_model  # noqa: E402

t, sp, pv, mv, q = demo_data()
r = fit_model("I1D", t, pv, mv, 1.0)
print("core ok:", [round(x, 4) for x in r["p"]])

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(os.path.join(os.getcwd(), "app.py"), default_timeout=600)
at.run()
at.session_state["src"] = "demo"
at.run()
next(b for b in at.button if b.label == "Identify").click().run()
errors = [x.message for x in at.exception]
assert not errors, errors
assert len(at.tabs) == 6 and "fit" in at.session_state
print("app ok:", at.session_state["mcode"])
