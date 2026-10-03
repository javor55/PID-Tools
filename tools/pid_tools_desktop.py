"""Vstupní bod desktopové aplikace pro PyInstaller (PID Tools.exe)."""
import sys

from pidtools.desktop import launch

if __name__ == "__main__":
    sys.exit(launch())
