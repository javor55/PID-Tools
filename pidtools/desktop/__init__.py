"""
Desktopová aplikace PID Tools pro inženýrské stanice (Qt / PySide6, grafy pyqtgraph).

Používá stejné jádro (pidtools.core) a aplikační vrstvu (pidtools.app) jako webová aplikace a stejný formát
projektu. Spuštění: python -m pidtools.desktop
"""


def launch(argv=None):
    """
    Start s úvodní obrazovkou: okno s ikonou se ukáže hned (než se načtou knihovny a sestaví okna), pak se spustí
    aplikace (pidtools.desktop.main.run). Používá ho python -m pidtools.desktop i PID Tools.exe.
    """
    import sys
    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QSplashScreen

    from .. import __version__

    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    splash = None
    if "--smoke" not in argv:
        pm = QPixmap(380, 200)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        icon = QPixmap(str(Path(__file__).resolve().parents[1] / "assets" / "icon.png"))
        if not icon.isNull():
            p.drawPixmap(24, 40, icon.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        p.setPen(QColor("#1f2933"))
        p.setFont(QFont("Segoe UI", 20, QFont.Bold))
        p.drawText(164, 92, "PID Tools")
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QColor("#64748b"))
        p.drawText(166, 116, f"{__version__} · PIDConL tuning")
        p.drawText(166, 150, "Loading …")
        p.setPen(QColor("#cbd5e1"))
        p.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
        p.end()
        splash = QSplashScreen(pm)
        splash.show()
        app.processEvents()
    from .main import run
    return run(argv, splash)
