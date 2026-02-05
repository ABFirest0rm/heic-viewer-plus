import sys
from PySide6.QtWidgets import QApplication
from .main_window import HeicViewer

def run():
    app = QApplication(sys.argv)
    window = HeicViewer()
    window.show()
    sys.exit(app.exec())
