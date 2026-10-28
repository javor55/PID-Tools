"""
Backend jako samostatný program (sidecar okna desktopu, M22): PyInstaller „onedir“ z pidtools.api.sidecar.

    pip install -r requirements-api.txt pyinstaller
    (cd frontend && npm ci && npm run build)          # rozhraní -> pidtools/api/ui (do balíčku jde jako data)
    python tools/build_sidecar.py                     # -> dist/pidtools-api/
    python tools/build_sidecar.py --smoke             # po sestavení spustí „--smoke“ zabaleného programu

Název programu podle konvence sidecaru Tauri 2 (`externalBin`): <název>-<cílová trojice>[.exe], např.
`pidtools-api-x86_64-pc-windows-msvc.exe`, na Linuxu `pidtools-api-x86_64-unknown-linux-gnu`. Tauri při balení
zkopíruje tento jediný soubor vedle aplikace (bez přípony trojice); složku `_internal` (knihovny a data onedir) je
potřeba přidat jako `resources` a sidecar spouštět z téže složky. Bez Qt a Streamlitu.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "pidtools-api"
# desktop (Qt), webová část a vývojové knihovny sidecar nepotřebuje
EXCLUDE = ["PySide6", "shiboken6", "pyqtgraph", "streamlit", "tornado", "altair", "pydeck", "watchdog", "pytest",
           "IPython", "matplotlib", "tkinter", "pyarrow", "playwright", "pidtools.desktop", "pidtools.ui"]


def target_triple():
    m = platform.machine().lower()
    arch = "aarch64" if m in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "win32":
        return f"{arch}-pc-windows-msvc"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin"
    return f"{arch}-unknown-linux-gnu"


def exe_name(triple):
    return f"{NAME}-{triple}" + (".exe" if sys.platform == "win32" else "")


def pyinstaller(out, triple):
    sep = os.pathsep
    ui = ROOT / "pidtools" / "api" / "ui"
    if not (ui / "index.html").exists():
        sys.exit("Missing pidtools/api/ui – build the frontend first: cd frontend && npm ci && npm run build")
    full = f"{NAME}-{triple}"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--console", "--name", full,
           "--distpath", str(out), "--workpath", str(out / "_build"), "--specpath", str(out / "_build"),
           "--collect-submodules", "pidtools", "--collect-submodules", "uvicorn", "--collect-data", "plotly",
           "--hidden-import", "asyncua",
           "--add-data", f"{ui}{sep}pidtools/api/ui",
           "--add-data", f"{ROOT / 'static' / 'fonts'}{sep}static/fonts",
           "--add-data", f"{ROOT / 'pidtools' / 'i18n' / '*.json'}{sep}pidtools/i18n",
           "--paths", str(ROOT)]
    icon = ROOT / "pidtools" / "assets" / "icon.ico"
    if sys.platform == "win32" and icon.exists():
        cmd += ["--icon", str(icon)]
    for m in EXCLUDE:
        cmd += ["--exclude-module", m]
    cmd.append(str(ROOT / "tools" / "pidtools_api.py"))
    subprocess.run(cmd, check=True, cwd=ROOT)
    target = out / NAME
    if target.exists():
        shutil.rmtree(target)
    (out / full).rename(target)
    return target


def dir_size(p):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--target-triple", default=None, help="default: from this machine")
    ap.add_argument("--smoke", action="store_true", help="run the built program with --smoke")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    triple = a.target_triple or target_triple()
    app_dir = pyinstaller(out, triple)
    exe = app_dir / exe_name(triple)
    shutil.rmtree(out / "_build", ignore_errors=True)
    print(f"Sidecar: {exe} (onedir {dir_size(app_dir) / 1e6:.0f} MB)")
    if a.smoke:
        sys.exit(subprocess.run([str(exe), "--smoke"], check=False).returncode)


if __name__ == "__main__":
    main()
