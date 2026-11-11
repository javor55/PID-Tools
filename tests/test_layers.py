"""Hranice vrstev (plán v2, kap. 7): core neimportuje app / api / ui / desktop, app neimportuje api / ui / desktop,
controllers (profily) nezávisí na zbytku balíčku."""
import ast
import os

import pytest

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pidtools")
FORBIDDEN = {
    "core": {"app", "api", "ui", "desktop"},
    "app": {"api", "ui", "desktop"},
    "controllers": {"app", "api", "ui", "desktop", "core", "i18n"},
}


def _imports(path):
    """Podbalíčky `pidtools.X`, které soubor importuje (absolutně i relativně), včetně importů uvnitř funkcí."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    here = os.path.relpath(os.path.dirname(path), ROOT).split(os.sep)     # balíček souboru, např. ["app", "apc"]
    found = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            if n.level == 0:
                full = (n.module or "").split(".")
                if full[0] != "pidtools":
                    continue
                full = full[1:]
            else:
                full = here[:len(here) - (n.level - 1)] + ((n.module or "").split(".") if n.module else [])
            if full and full[0]:
                found.add(full[0])
            elif not full or not full[0]:                      # `from pidtools import x` / `from .. import x`
                found.update(a.name for a in n.names)
        elif isinstance(n, ast.Import):
            for a in n.names:
                parts = a.name.split(".")
                if parts[0] == "pidtools" and len(parts) > 1:
                    found.add(parts[1])
    return found


def _files(pkg):
    for d, _, fs in os.walk(os.path.join(ROOT, pkg)):
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(d, f)


@pytest.mark.parametrize("pkg", list(FORBIDDEN))
def test_layer_boundaries(pkg):
    bad = []
    for p in _files(pkg):
        for m in _imports(p) & FORBIDDEN[pkg]:
            bad.append(f"{os.path.relpath(p, ROOT)} importuje {m}")
    assert not bad, "\n".join(bad)


def test_core_import_does_not_load_upper_layers():
    """Za běhu: import pidtools.core nenačte app, api ani rozhraní."""
    import subprocess
    import sys
    code = ("import sys, pidtools.core, pidtools.core.controller; "
            "bad = [m for m in sys.modules if m.split('.')[:2] in (['pidtools','app'],['pidtools','api'],"
            "['pidtools','ui'],['pidtools','desktop'])]; print(','.join(bad)); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
