import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from .main_window import HeicViewer

def run():
    app = QApplication(sys.argv)

    ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "icon.png"
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    window = HeicViewer()
    window.show()

    sys.exit(app.exec())
