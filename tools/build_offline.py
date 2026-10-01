"""
Build a portable offline package of PID Tools for Windows (x64).

The result is a folder / ZIP with an embedded Python, all libraries and the application. On the target PC it is
just unzipped (e.g. from a USB stick) and started with PID-Tools.bat – no installation, no admin rights, no internet.

Run on a Windows PC with internet access and Python 3.11 (the same minor version as the embedded one):

    python tools/build_offline.py            # -> dist/PID-Tools-<version>-win64-offline.zip
    python tools/build_offline.py --no-zip   # folder only (dist/PID-Tools)

The GitHub workflow .github/workflows/offline-package.yml runs this script on windows-latest.
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_VERSION = "3.11.9"          # last 3.11 release with an embeddable package
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
APP_FILES = ["app.py", "pidtools", ".streamlit", "LICENSE", "README.md", "CHANGELOG.md", "docs"]

LAUNCHER = r"""@echo off
rem PID Tools – offline package. Starts the app and opens it in the default browser.
rem Close this window to stop the app.
setlocal
cd /d "%~dp0app"
set PYTHONNOUSERSITE=1
set PORT=8501
echo Starting PID Tools on http://localhost:%PORT% ...
start "" /b cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:%PORT%"
"%~dp0python\python.exe" -m streamlit run app.py --server.headless true --server.port %PORT% ^
    --browser.gatherUsageStats false --server.fileWatcherType none
pause
"""

README_TXT = """PID Tools {version} – offline package for Windows (x64)

1. Copy the whole folder to the target PC (e.g. C:\\Tools\\PID-Tools). The path should not be too long.
2. Double-click PID-Tools.bat. A console window starts the app and the browser opens http://localhost:8501
   (if not, open the address manually).
3. Close the console window to stop the app.

No installation, no admin rights and no internet are needed. To uninstall, delete the folder.
Work in progress is autosaved in the browser; projects (JSON) and reports (HTML) are downloaded to the PC.
Documentation: README.md and the docs folder.
"""


def version():
    ns = {}
    exec((ROOT / "pidtools" / "__init__.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def build(out_dir: Path, make_zip: bool):
    pkg = out_dir / "PID-Tools"
    if pkg.exists():
        shutil.rmtree(pkg)
    py_dir, app_dir = pkg / "python", pkg / "app"
    py_dir.mkdir(parents=True)

    print(f"Downloading embedded Python {PY_VERSION} ...")
    with urllib.request.urlopen(EMBED_URL) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(py_dir)

    # embedded Python ignores site-packages unless enabled in the ._pth file
    pth = next(py_dir.glob("python*._pth"))
    lines = [ln for ln in pth.read_text().splitlines() if ln.strip() and ln.strip() != "#import site"]
    pth.write_text("\n".join(lines + ["Lib\\site-packages", "import site"]) + "\n")

    site = py_dir / "Lib" / "site-packages"
    print("Installing libraries ...")
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
           "--target", str(site), "-r", str(ROOT / "requirements.txt")]
    if os.name != "nt":   # cross-build from Linux/macOS: Windows wheels only (+ Windows-only dependencies)
        cmd += ["--platform", "win_amd64", "--python-version", "3.11", "--implementation", "cp",
                "--only-binary=:all:", "colorama"]
    subprocess.run(cmd, check=True)
    # test suites of numpy / scipy / pandas / pyarrow are not needed at run time (~100 MB)
    for d in sorted(site.rglob("tests"), key=lambda x: len(x.parts), reverse=True):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)

    print("Copying the application ...")
    app_dir.mkdir()
    for name in APP_FILES:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, app_dir / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.exists():
            shutil.copy2(src, app_dir / name)

    v = version()
    (pkg / "PID-Tools.bat").write_text(LAUNCHER.replace("\n", "\r\n"), encoding="ascii")
    (pkg / "README.txt").write_text(README_TXT.format(version=v).replace("\n", "\r\n"), encoding="utf-8")

    if make_zip:
        zip_path = out_dir / f"PID-Tools-{v}-win64-offline.zip"
        print(f"Creating {zip_path.name} ...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in sorted(pkg.rglob("*")):
                z.write(f, f.relative_to(out_dir))
        print(f"Done: {zip_path} ({zip_path.stat().st_size / 1e6:.0f} MB)")
    else:
        print(f"Done: {pkg}")
    size = sum(f.stat().st_size for f in pkg.rglob("*") if f.is_file())
    print(f"Package size: {size / 1e6:.0f} MB unpacked")
    return pkg


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"), help="output directory (default: dist)")
    ap.add_argument("--no-zip", action="store_true", help="build the folder only")
    a = ap.parse_args()
    build(Path(a.out), not a.no_zip)
