"""Funkce úloh pro tests/test_jobs.py (podřízený proces je musí importovat podle jména modulu)."""
import time


def slow(n, dt=0.05, progress=None):
    for i in range(n):
        time.sleep(dt)
        if progress:
            progress((i + 1) / n, f"krok {i + 1}")
    return n * 2


def fail():
    raise ValueError("chybný vstup")


def ident(code):
    """Skutečný výpočet: identifikace na ukázkových datech."""
    from pidtools.app.workspace import Workspace
    s = Workspace()
    s.load_demo()
    s.set(chosen=[code])
    s.identify()
    return s.fit["res"][code]["p"]
