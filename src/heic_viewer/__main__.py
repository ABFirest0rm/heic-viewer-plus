import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from pathlib import Path

from heic_viewer.main_window import HeicViewer

def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "HeicViewerPlus.App"
        )

    icon_path = None

    if hasattr(sys, "_MEIPASS"):
        icon_path = Path(sys._MEIPASS) / "assets/icon.png"

    app = QApplication(sys.argv)

    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))

    window = HeicViewer()

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        QTimer.singleShot(0, lambda: window.handle_file(file_path))

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()