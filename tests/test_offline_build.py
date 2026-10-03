"""Offline package builder: the generated launcher must be plain ASCII (cmd.exe reads .bat files in the OEM code page)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location("build_offline", ROOT / "tools" / "build_offline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_launcher_is_ascii():
    b = _builder()
    b.LAUNCHER.replace("\n", "\r\n").encode("ascii")
    assert "python\\python.exe" in b.LAUNCHER and "streamlit run app.py" in b.LAUNCHER
    b.LAUNCHER_DESKTOP.replace("\n", "\r\n").encode("ascii")
    assert "pythonw.exe" in b.LAUNCHER_DESKTOP and "-m pidtools.desktop" in b.LAUNCHER_DESKTOP


def test_readme_and_app_files():
    b = _builder()
    b.README_TXT.format(version=b.version()).encode("utf-8")
    assert all((ROOT / f).exists() for f in b.APP_FILES)


def test_desktop_build_script():
    """Desktopová aplikace jako exe: ikona existuje, šablona instalátoru Inno Setup se dá vyplnit."""
    spec = importlib.util.spec_from_file_location("build_desktop", ROOT / "tools" / "build_desktop.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (ROOT / "pidtools" / "assets" / "icon.ico").exists() and (ROOT / "pidtools" / "assets" / "icon.png").exists()
    iss = mod.ISS.format(version=mod.version(), out="dist", icon="icon.ico", src="dist\\PID Tools")
    assert "PrivilegesRequired=lowest" in iss and "{app}\\PID Tools.exe" in iss and "{#AppVersion}" in iss
    assert "streamlit" in mod.EXCLUDE and "pyarrow" in mod.EXCLUDE
