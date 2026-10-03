"""
Desktopová aplikace PID Tools jako klasická aplikace pro Windows: složka s „PID Tools.exe“ (PyInstaller) a z ní
instalátor PID-Tools-<verze>-setup.exe (Inno Setup, instalace pro jednoho uživatele bez práv správce, zástupce
v nabídce Start a na ploše, odinstalace v Nastavení Windows) a přenosný ZIP (rozbalit a spustit).

    pip install -r requirements.txt -r requirements-desktop.txt pyinstaller
    python tools/build_desktop.py               # -> dist/PID Tools/PID Tools.exe, ZIP, (s Inno Setup) instalátor
    python tools/build_desktop.py --no-installer

Workflow .github/workflows/offline-package.yml to spouští na windows-latest. Na Linuxu vznikne linuxová verze
(stejný postup, užitečné pro kontrolu).
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "PID Tools"
# webová část a vývojové knihovny desktop nepotřebuje
EXCLUDE = ["streamlit", "tornado", "altair", "pydeck", "watchdog", "pytest", "IPython", "matplotlib", "tkinter", "pyarrow",
           "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia"]


def version():
    ns = {}
    exec((ROOT / "pidtools" / "__init__.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def pyinstaller(out):
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", NAME,
           "--icon", str(ROOT / "pidtools" / "assets" / "icon.ico"),
           "--distpath", str(out), "--workpath", str(out / "_build"), "--specpath", str(out / "_build"),
           "--collect-submodules", "pidtools", "--hidden-import", "asyncua",
           "--add-data", f"{ROOT / 'pidtools' / 'assets'}{sep}pidtools/assets",
           "--paths", str(ROOT)]
    for m in EXCLUDE:
        cmd += ["--exclude-module", m]
    cmd.append(str(ROOT / "tools" / "pid_tools_desktop.py"))
    subprocess.run(cmd, check=True, cwd=ROOT)
    return out / NAME


ISS = r"""
#define AppName "PID Tools"
#define AppVersion "{version}"
[Setup]
AppId={{{{6E0B7F7A-3C1D-4D5E-9A8B-2F4C6D8E0A11}}
AppName={{#AppName}}
AppVersion={{#AppVersion}}
AppPublisher=PID Tools
DefaultDirName={{localappdata}}\Programs\PID Tools
DefaultGroupName=PID Tools
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={out}
OutputBaseFilename=PID-Tools-{version}-setup
SetupIconFile={icon}
UninstallDisplayIcon={{app}}\PID Tools.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

[Files]
Source: "{src}\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{group}}\PID Tools"; Filename: "{{app}}\PID Tools.exe"
Name: "{{autodesktop}}\PID Tools"; Filename: "{{app}}\PID Tools.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\PID Tools.exe"; Description: "{{cm:LaunchProgram,PID Tools}}"; Flags: nowait postinstall skipifsilent
"""


def inno(app_dir, out, v):
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not Path(iscc).exists():
        print("Inno Setup not found – installer skipped.")
        return None
    iss = out / "_build" / "pidtools.iss"
    iss.write_text(ISS.format(version=v, out=out, icon=ROOT / "pidtools" / "assets" / "icon.ico", src=app_dir),
                   encoding="utf-8")
    subprocess.run([iscc, "/Q", str(iss)], check=True)
    return out / f"PID-Tools-{v}-setup.exe"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--no-installer", action="store_true")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    v = version()
    app_dir = pyinstaller(out)
    print("Application:", app_dir)
    zip_path = out / f"PID-Tools-{v}-desktop-win64-portable.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(app_dir.rglob("*")):
            z.write(f, Path(NAME) / f.relative_to(app_dir))
    print(f"Portable: {zip_path} ({zip_path.stat().st_size / 1e6:.0f} MB)")
    if not a.no_installer and os.name == "nt":
        print("Installer:", inno(app_dir, out, v))


if __name__ == "__main__":
    main()
