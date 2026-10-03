"""Vstupní bod desktopové aplikace pro PyInstaller (PID Tools.exe)."""
import sys

from pidtools.desktop.main import run

if __name__ == "__main__":
    sys.exit(run())
