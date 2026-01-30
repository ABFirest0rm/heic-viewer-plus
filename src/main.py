import sys
from pathlib import Path
from PIL import Image
from PIL.ImageQt import ImageQt
import pillow_heif
pillow_heif.register_heif_opener()
print("HEIF support registered")

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QWidget,
    QLabel,
    QHBoxLayout,
    QStackedLayout
)
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import Qt

class HeicViewer(QMainWindow):

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".avif"}

    def __init__(self):
        super().__init__()

        self.setWindowTitle("HEIC Viewer")
        self.resize(800, 600)

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

        self.files = None
        self.current_idx = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setStyleSheet("background: transparent; border: none;")

        self.view.setRenderHints(
            self.view.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        self.stack = QStackedLayout()
        main_layout.addLayout(self.stack)

        start_page = QWidget()
        start_layout = QVBoxLayout(start_page)

        self.open_button_center = QPushButton("Open Image")
        self.open_button_center.setFixedWidth(160)
        self.open_button_center.clicked.connect(self.open_file)

        start_layout.addStretch()
        start_layout.addWidget(
            self.open_button_center,
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        start_layout.addStretch()

        viewer_page = QWidget()
        viewer_layout = QVBoxLayout(viewer_page)

        top_bar = QHBoxLayout()

        self.open_button_top = QPushButton("Open Image")
        self.open_button_top.setFixedWidth(120)
        self.open_button_top.clicked.connect(self.open_file)

        top_bar.addStretch()
        top_bar.addWidget(self.open_button_top)

        viewer_layout.addLayout(top_bar)
        viewer_layout.addWidget(self.view)

        self.stack.addWidget(start_page)  # index 0
        self.stack.addWidget(viewer_page)  # index 1

        self.stack.setCurrentIndex(0)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "Downloads",
            "Images (*.heic *.heif *.avif *.jpg *.jpeg);;All Files (*)",
        )

        print(f"File opened: {file_path}")
        print(f"File opened _: {_}")

        if file_path:
            self.handle_file(file_path)
            # print("Selected file:", file_path)

    def dragEnterEvent(self, event):
        print("dragEnterEvent:", event)
        print("dragEnterEvent mimedata:", event.mimeData())
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        print(urls)
        if not urls:
            return

        file_path = urls[0].toLocalFile()
        self.handle_file(file_path)

    def handle_file(self, file_path, from_navigation=False):

        path = Path(file_path)
        parent = path.parent

        if not from_navigation:
            print("BUILDING FILE LIST")
            files = [p for p in parent.iterdir()
                     if p.is_file() and p.suffix.lower() in HeicViewer.IMAGE_EXTS]
            files.sort()

            if path not in files:
                return

            self.files = files
            self.current_idx = files.index(path)

        # self.label.setText(str(path))
        print(f"Showing [{self.current_idx + 1}/{len(self.files)}]: {path.name}")
        img = Image.open(path)
        qimage = ImageQt(img)
        pixmap = QPixmap.fromImage(qimage)

        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.view.fitInView(
            self.pixmap_item,
            Qt.AspectRatioMode.KeepAspectRatio
        )
        self.view.show()

        self.stack.setCurrentIndex(1)

    def keyPressEvent(self, event):
        if not hasattr(self, "files"):
            return

        if event.key() == Qt.Key_Right:
            self.current_idx = min(self.current_idx + 1, len(self.files) - 1)

        elif event.key() == Qt.Key_Left:
            self.current_idx = max(self.current_idx - 1, 0)
        else:
            return

        self.handle_file(str(self.files[self.current_idx]), from_navigation=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "pixmap_item"):
            self.view.fitInView(
                self.pixmap_item,
                Qt.AspectRatioMode.KeepAspectRatio
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HeicViewer()
    window.show()
    sys.exit(app.exec())
