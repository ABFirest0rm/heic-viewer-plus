import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from heic_viewer.main_window import HeicViewer


def main():
    app = QApplication(sys.argv)

    window = HeicViewer()

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        QTimer.singleShot(0, lambda: window.handle_file(file_path))

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()