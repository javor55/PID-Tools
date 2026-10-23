"""
Výpočty pracovního prostoru v procesu úlohy (app.jobs): metoda se zavolá na odlehčené kopii (Workspace.lean)
a výsledek i změněný stav se vrátí; API ho po dokončení zapíše do prostoru (apply).
"""
import inspect

STATE = ("fit", "unc", "cv")          # atributy prostoru, které výpočty mění (vedle nastavení)


def run(ws, method, args=(), kwargs=None, steps=1, progress=None):
    """
    ws.method(*args, **kwargs) → dict(result, state = {atribut: hodnota}, settings). Průběh: metody hlásí
    (index, kód) – převede se na podíl z `steps` kroků.
    """
    fn = getattr(ws, method)
    kw = dict(kwargs or {})
    if progress is not None and "progress" in inspect.signature(fn).parameters:
        def prog(i, c=""):
            progress(min(float(i) / max(steps, 1), 0.99), str(c))
        kw["progress"] = prog
    res = fn(*args, **kw)
    return dict(result=res, state={k: getattr(ws, k, None) for k in STATE}, settings=ws.settings)


def apply(ws, out):
    """Výsledek úlohy → pracovní prostor (stav a nastavení)."""
    for k, v in out["state"].items():
        setattr(ws, k, v)
    ws.settings = dict(out["settings"])
