import sys
from pathlib import Path
from PIL import Image
from PIL.ImageQt import ImageQt
import pillow_heif
from PySide6.QtCore import QTimer, Signal
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
    QStackedLayout, QSlider
)
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtGui import QPixmap, QPainter, QKeySequence, QShortcut
from PySide6.QtCore import Qt

class ImageView(QGraphicsView):
    zoomed = Signal(float)
    resetRequested = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event):
        if not (event.modifiers() & Qt.ControlModifier):
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        factor = 1.1 if delta > 0 else 1 / 1.1
        self.zoomed.emit(factor)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.resetRequested.emit()
        event.accept()


class HeicViewer(QMainWindow):

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".avif"}

    def __init__(self):
        super().__init__()

        self.setWindowTitle("HEIC Viewer")
        self.resize(800, 600)

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

        # ---- state ----
        self.files = None
        self.current_idx = None
        self.current_zoom = 1.0   # 1.0 = 100%
        self.user_zoomed = False

        # ---- shortcuts ----
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.next_image)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.prev_image)

        # ---- central layout ----
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ---- graphics view ----
        self.scene = QGraphicsScene(self)
        self.view = ImageView(self.scene, self)
        self.view.setStyleSheet("background: transparent; border: none;")

        self.view.setRenderHints(
            self.view.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        # signals from ImageView
        self.view.zoomed.connect(self.on_wheel_zoom)
        self.view.resetRequested.connect(self.reset_zoom)

        # ---- stacked pages ----
        self.stack = QStackedLayout()
        main_layout.addLayout(self.stack)

        # ===== Start page =====
        start_page = QWidget()
        start_layout = QVBoxLayout(start_page)

        self.open_button_center = QPushButton("Open Image")
        self.open_button_center.setFixedWidth(160)
        self.open_button_center.clicked.connect(self.open_file)

        start_layout.addStretch()
        start_layout.addWidget(self.open_button_center, alignment=Qt.AlignmentFlag.AlignCenter)
        start_layout.addStretch()

        # ===== Viewer page =====
        viewer_page = QWidget()
        viewer_layout = QVBoxLayout(viewer_page)

        # -- top bar --
        top_bar = QHBoxLayout()

        self.open_button_top = QPushButton("Open Image")
        self.open_button_top.setFixedWidth(120)
        self.open_button_top.clicked.connect(self.open_file)

        top_bar.addStretch()
        top_bar.addWidget(self.open_button_top)
        viewer_layout.addLayout(top_bar)

        # -- image view --
        viewer_layout.addWidget(self.view)

        # -- bottom zoom bar --
        zoom_bar = QHBoxLayout()
        zoom_bar.setContentsMargins(10, 6, 10, 10)
        zoom_bar.setSpacing(8)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 400)      # 10% → 400%
        self.zoom_slider.setValue(100)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setFixedWidth(220)
        self.zoom_slider.valueChanged.connect(self.on_slider_zoom)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        zoom_bar.addStretch()
        zoom_bar.addWidget(self.zoom_slider)
        zoom_bar.addWidget(self.zoom_label)
        zoom_bar.addStretch()

        viewer_layout.addLayout(zoom_bar)

        # ---- stack pages ----
        self.stack.addWidget(start_page)    # index 0
        self.stack.addWidget(viewer_page)   # index 1
        self.stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Zoom logic
    # ------------------------------------------------------------------

    def set_zoom(self, zoom: float):
        zoom = max(0.1, min(zoom, 4.0))

        factor = zoom / self.current_zoom
        self.current_zoom = zoom
        self.user_zoomed = True

        self.view.scale(factor, factor)
        self.update_zoom_label()

    def on_wheel_zoom(self, factor: float):
        new_zoom = self.current_zoom * factor
        new_zoom = max(0.1, min(new_zoom, 4.0))

        self.set_zoom(new_zoom)

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(new_zoom * 100))
        self.zoom_slider.blockSignals(False)

    def on_slider_zoom(self, value: int):
        self.set_zoom(value / 100.0)

    def update_zoom_label(self):
        self.zoom_label.setText(f"{int(self.current_zoom * 100)}%")

    def reset_zoom(self):
        self.user_zoomed = False

        self.view.resetTransform()
        self.current_zoom = 1.0

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(100)
        self.zoom_slider.blockSignals(False)

        self.update_zoom_label()

        QTimer.singleShot(0, self._fit_image)

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------

    def _fit_image(self):
        if hasattr(self, "pixmap_item") and not self.user_zoomed:
            self.view.fitInView(
                self.pixmap_item,
                Qt.AspectRatioMode.KeepAspectRatio
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_image()


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
        print(f"{path=}, {from_navigation=}")
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
        self.reset_zoom()
        img = Image.open(path)
        qimage = ImageQt(img)
        pixmap = QPixmap.fromImage(qimage)

        self.user_zoomed = False
        self.view.resetTransform()
        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.view.resetTransform()
        QTimer.singleShot(0, self._fit_image)
        self.view.show()
        self.stack.setCurrentIndex(1)

    # def _fit_image(self):
    #     if hasattr(self, "pixmap_item"):
    #         if not self.user_zoomed:
    #             self.view.fitInView(
    #                 self.pixmap_item,
    #                 Qt.AspectRatioMode.KeepAspectRatio
    #             )

    def next_image(self):
        if not self.files:
            return
        self.current_idx = min(self.current_idx + 1, len(self.files) - 1)
        self.handle_file(str(self.files[self.current_idx]), from_navigation=True)

    def prev_image(self):
        if not self.files:
            return
        self.current_idx = max(self.current_idx - 1, 0)
        self.handle_file(str(self.files[self.current_idx]), from_navigation=True)

    # def resizeEvent(self, event):
    #     super().resizeEvent(event)
    #     self._fit_image()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HeicViewer()
    window.show()
    sys.exit(app.exec())
