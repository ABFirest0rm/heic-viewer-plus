import sys
from pathlib import Path
from PIL import Image
from PIL.ImageQt import ImageQt
import pillow_heif
from PySide6.QtCore import QTimer, Signal, QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsRectItem
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsRectItem
from PySide6.QtWidgets import QSizePolicy


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
    QStackedLayout, QSlider, QMessageBox
)
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QPainter, QKeySequence, QShortcut, QPainterPath
from PySide6.QtCore import Qt


class ClippedPixmapItem(QGraphicsPixmapItem):
    """A QGraphicsPixmapItem that can be clipped to a specific rect"""

    def __init__(self, pixmap):
        super().__init__(pixmap)
        self._clip_rect = None

    # selected crop
    def setClipRect(self, rect):
        self._clip_rect = rect
        self.update()

    # reset crop area
    def clearClipRect(self):
        """Remove clipping"""
        self._clip_rect = None
        self.update()

    # canvas boundary
    def boundingRect(self):
        """Return the clipped bounding rect if clip is set"""
        if self._clip_rect:
            return self._clip_rect
        return super().boundingRect()

    # restrcit mouse intearaction region
    def shape(self):
        """Return the clipped shape"""
        path = QPainterPath()
        if self._clip_rect:
            path.addRect(self._clip_rect)
        else:
            path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        """Paint with clipping if set"""
        if self._clip_rect:
            painter.setClipRect(self._clip_rect)
        super().paint(painter, option, widget)


class ImageView(QGraphicsView):
    zoomed = Signal(float)
    resetRequested = Signal()

    def __init__(self, scene, controller, parent=None):
        super().__init__(scene, parent)

        self.controller = controller
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

    def mousePressEvent(self, event):
        ctrl = self.controller

        if not ctrl.crop_mode:
            return super().mousePressEvent(event)

        if event.button() != Qt.LeftButton:
            return

        ctrl._crop_start = self.mapToScene(event.position().toPoint())

        if ctrl._crop_item:
            ctrl.scene.removeItem(ctrl._crop_item)

        ctrl._crop_item = QGraphicsRectItem()
        ctrl._crop_item.setPen(QPen(QColor(255, 255, 255), 1, Qt.DashLine))
        ctrl._crop_item.setBrush(QColor(255, 255, 255, 40))
        ctrl._crop_item.setZValue(20)

        ctrl.scene.addItem(ctrl._crop_item)
        event.accept()

    def mouseMoveEvent(self, event):
        ctrl = self.controller

        if not ctrl.crop_mode or ctrl._crop_start is None:
            return super().mouseMoveEvent(event)

        current = self.mapToScene(event.position().toPoint())
        rect = QRectF(ctrl._crop_start, current).normalized()

        ctrl._crop_item.setRect(rect)
        ctrl.update_crop_overlay(rect)

        event.accept()

    def mouseReleaseEvent(self, event):
        ctrl = self.controller

        if not ctrl.crop_mode:
            return super().mouseReleaseEvent(event)

        ctrl._crop_start = None
        event.accept()


class HeicViewer(QMainWindow):
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".avif"}

    def __init__(self):
        super().__init__()

        # --------------------------------------------------
        # Window setup
        # --------------------------------------------------
        self.setWindowTitle("HEIC Viewer")
        self.resize(900, 600)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # --------------------------------------------------
        # State
        # --------------------------------------------------
        self.files = None
        self.current_idx = None

        self.current_zoom = 1.0
        self.user_zoomed = False
        self.view_dirty = False
        self.view_rotation = 0
        self.is_zoom_actual_size = False

        self.crop_mode = False
        self.crop_rect = None
        self._crop_start = None
        self._crop_item = None
        self._crop_overlay_items = []

        self.undo_stack = []
        self.redo_stack = []

        # --------------------------------------------------
        # Shortcuts
        # --------------------------------------------------
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.next_image)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.prev_image)
        QShortcut(QKeySequence(Qt.Key_F11), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence.Undo, self, activated=self.undo)
        QShortcut(QKeySequence.Redo, self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.zoom_actual_size)

        self.crop_done_shortcut_return = QShortcut(QKeySequence(Qt.Key_Return), self)
        self.crop_done_shortcut_enter = QShortcut(QKeySequence(Qt.Key_Enter), self)
        self.crop_done_shortcut_return.activated.connect(self._on_crop_enter)
        self.crop_done_shortcut_enter.activated.connect(self._on_crop_enter)

        # --------------------------------------------------
        # Central widget
        # --------------------------------------------------
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --------------------------------------------------
        # Graphics view
        # --------------------------------------------------
        self.scene = QGraphicsScene(self)
        self.view = ImageView(self.scene, self, self)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self.view.zoomed.connect(self.on_wheel_zoom)
        self.view.resetRequested.connect(self.reset_zoom)

        # --------------------------------------------------
        # Zoom widgets (CREATE ONCE)
        # --------------------------------------------------
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(220)
        self.zoom_slider.valueChanged.connect(self.on_slider_zoom)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)

        self.actual_size_btn = QPushButton("1:1")
        self.actual_size_btn.setToolTip("Actual Size (Ctrl+1)")
        self.actual_size_btn.clicked.connect(self.zoom_actual_size)

        # --------------------------------------------------
        # Buttons
        # --------------------------------------------------
        self.open_button_top = QPushButton("Open")
        self.open_button_top.clicked.connect(self.open_file)

        self.convert_btn = QPushButton("Convert Original")
        self.convert_btn.clicked.connect(self.convert_image)

        self.save_as_btn = QPushButton("Save As")
        self.save_as_btn.setEnabled(False)
        self.save_as_btn.clicked.connect(self.save_as_view)

        self.rotate_left_btn = QPushButton("⟲")
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_view(-90))

        self.rotate_right_btn = QPushButton("⟳")
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_view(90))

        self.crop_btn = QPushButton("Crop")
        self.crop_btn.clicked.connect(self.enter_crop_mode)

        self.crop_done_btn = QPushButton("Done")
        self.crop_done_btn.setVisible(False)
        self.crop_done_btn.clicked.connect(self.commit_crop)

        self.crop_cancel_btn = QPushButton("Cancel")
        self.crop_cancel_btn.setVisible(False)
        self.crop_cancel_btn.clicked.connect(self.cancel_crop)

        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo)

        self.redo_btn = QPushButton("Redo")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.redo)

        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        # --- Exit fullscreen button (CREATE ONCE) ---
        self.exit_fullscreen_btn = QPushButton("✕")
        self.exit_fullscreen_btn.setToolTip("Exit Fullscreen (Esc)")
        self.exit_fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        # --- Exit fullscreen widget (CREATE ONCE) ---
        self.exit_fs_widget = QWidget(self)
        exit_fs_layout = QHBoxLayout(self.exit_fs_widget)
        exit_fs_layout.setContentsMargins(6, 6, 6, 6)

        exit_fs_layout.addStretch()
        exit_fs_layout.addWidget(self.exit_fullscreen_btn)

        self.exit_fs_widget.setVisible(False)

        # --------------------------------------------------
        # Stacked pages
        # --------------------------------------------------
        self.stack = QStackedLayout()
        main_layout.addLayout(self.stack)

        # ---------------- Start page ----------------
        start_page = QWidget()
        start_layout = QVBoxLayout(start_page)

        open_center = QPushButton("Open Image")
        open_center.setFixedWidth(180)
        open_center.clicked.connect(self.open_file)

        start_layout.addStretch()
        start_layout.addWidget(open_center, alignment=Qt.AlignCenter)
        start_layout.addStretch()

        # ---------------- Viewer page ----------------
        viewer_page = QWidget()
        viewer_layout = QVBoxLayout(viewer_page)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)

        # -------- Top bar --------
        self.top_bar_widget = QWidget()
        top_bar = QHBoxLayout(self.top_bar_widget)
        top_bar.setContentsMargins(6, 6, 6, 6)

        top_bar.addWidget(self.convert_btn)
        top_bar.addWidget(self.crop_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.rotate_left_btn)
        top_bar.addWidget(self.rotate_right_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.open_button_top)
        top_bar.addWidget(self.save_as_btn)

        # -------- Bottom bar --------
        self.bottom_bar_widget = QWidget()
        bottom_bar = QHBoxLayout(self.bottom_bar_widget)
        bottom_bar.setContentsMargins(6, 6, 6, 6)

        bottom_bar.addWidget(self.undo_btn)
        bottom_bar.addWidget(self.redo_btn)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.zoom_slider)
        bottom_bar.addWidget(self.zoom_label)
        bottom_bar.addWidget(self.actual_size_btn)
        bottom_bar.addWidget(self.fullscreen_btn)

        # -------- Assemble viewer --------
        viewer_layout.addWidget(self.top_bar_widget)
        viewer_layout.addWidget(self.view, stretch=1)
        viewer_layout.addWidget(self.exit_fs_widget)
        viewer_layout.addWidget(self.bottom_bar_widget)

        # -------- Stack --------
        self.stack.addWidget(start_page)
        self.stack.addWidget(viewer_page)
        self.stack.setCurrentIndex(0)

    # Crop Button
    def enter_crop_mode(self):
        self.crop_mode = True

        # self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)

        self.crop_btn.setEnabled(False)
        self.crop_done_btn.setVisible(True)
        self.crop_cancel_btn.setVisible(True)

        self.rotate_left_btn.setEnabled(False)
        self.rotate_right_btn.setEnabled(False)
        self.convert_btn.setEnabled(False)
        self.save_as_btn.setEnabled(False)

    def confirm_discard_crop(self) -> bool:
        if self._crop_item is None:
            return True

        reply = QMessageBox.question(
            self,
            "Discard Crop?",
            "You have an unfinished crop.\n\nDiscard it?",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel
        )

        return reply == QMessageBox.Discard

    def exit_crop_mode(self):
        self.crop_mode = False

        # self.view.unsetCursor()
        self.view.viewport().unsetCursor()

        self.crop_btn.setEnabled(True)
        self.crop_done_btn.setVisible(False)
        self.crop_cancel_btn.setVisible(False)

        self.rotate_left_btn.setEnabled(True)
        self.rotate_right_btn.setEnabled(True)
        self.convert_btn.setEnabled(True)

    # Cancel Button
    def cancel_crop(self):
        if not self.confirm_discard_crop():
            return
        self.clear_crop_preview()
        self.exit_crop_mode()

    def commit_crop(self):
        if self._crop_item is None:
            self.exit_crop_mode()
            return

        # Save undo state
        self.undo_stack.append(self._capture_view_state())
        self.redo_stack.clear()
        self._update_undo_redo_buttons()

        # Convert crop rect to SCENE coordinates
        selection_scene_rect = self._crop_item.mapRectToScene(
            self._crop_item.rect()
        )

        # Clamp crop to image bounds (both in scene space)
        image_scene_rect = self.pixmap_item.sceneBoundingRect()
        final_crop = selection_scene_rect.intersected(image_scene_rect)

        if final_crop.isEmpty():
            final_crop = selection_scene_rect

        self.crop_rect = final_crop

        # Remove crop visuals
        self.clear_crop_preview()

        # Non-destructive crop: clip the pixmap item to the crop rect
        self.pixmap_item.setClipRect(final_crop)

        # Update scene rect to the crop area
        self.scene.setSceneRect(final_crop)

        # Fit new scene
        self.view.fitInView(final_crop, Qt.AspectRatioMode.KeepAspectRatio)

        # Sync zoom UI
        t = self.view.transform()
        self.current_zoom = t.m11()
        self.update_zoom_label()
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(self.current_zoom * 100))
        self.zoom_slider.blockSignals(False)

        self.view_dirty = True
        self.save_as_btn.setEnabled(True)

        self.exit_crop_mode()

    def focus_on_crop(self, rect: QRectF):
        if not rect or not rect.isValid():
            return

        # we are explicitly controlling the view now
        self.user_zoomed = True

        # fit view to crop rect
        self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

        # extract resulting zoom from view transform
        t = self.view.transform()
        self.current_zoom = t.m11()  # scale factor

        # sync UI
        self.update_zoom_label()

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(self.current_zoom * 100))
        self.zoom_slider.blockSignals(False)

    def update_crop_overlay(self, crop_rect: QRectF):
        self.clear_crop_overlay()

        if not self.pixmap_item:
            return

        img_rect = self.pixmap_item.boundingRect()

        dim_color = QColor(0, 0, 0, 140)

        # Top
        top = QRectF(
            img_rect.left(),
            img_rect.top(),
            img_rect.width(),
            crop_rect.top() - img_rect.top()
        )

        # Bottom
        bottom = QRectF(
            img_rect.left(),
            crop_rect.bottom(),
            img_rect.width(),
            img_rect.bottom() - crop_rect.bottom()
        )

        # Left
        left = QRectF(
            img_rect.left(),
            crop_rect.top(),
            crop_rect.left() - img_rect.left(),
            crop_rect.height()
        )

        # Right
        right = QRectF(
            crop_rect.right(),
            crop_rect.top(),
            img_rect.right() - crop_rect.right(),
            crop_rect.height()
        )

        for rect in (top, bottom, left, right):
            if rect.isValid() and not rect.isEmpty():
                item = QGraphicsRectItem(rect)
                item.setBrush(dim_color)
                item.setPen(Qt.NoPen)
                item.setZValue(10)
                self.scene.addItem(item)
                self._crop_overlay_items.append(item)

    def _on_crop_enter(self):
        if self.crop_mode:
            self.commit_crop()

    def clear_crop_overlay(self):
        for item in self._crop_overlay_items:
            self.scene.removeItem(item)
        self._crop_overlay_items.clear()

    def clear_crop_preview(self):
        if self._crop_item:
            self.scene.removeItem(self._crop_item)
            self._crop_item = None
        self.clear_crop_overlay()

    def _capture_view_state(self):
        return {
            "zoom": self.current_zoom,
            "rotation": self.view_rotation,
            "transform": self.view.transform(),
            "scene_rect": self.scene.sceneRect(),
        }

    def _restore_view_state(self, state):
        if not state:
            return

        # restore transform & scene
        self.view.setTransform(state["transform"])
        self.scene.setSceneRect(state["scene_rect"])

        # restore zoom & rotation bookkeeping
        self.current_zoom = state["zoom"]
        self.view_rotation = state["rotation"]

        # IMPORTANT: restore crop clip
        if self.crop_rect:
            self.pixmap_item.clearClipRect()

        # reapply clip if scene rect != full image
        if state["scene_rect"] != self.pixmap_item.sceneBoundingRect():
            self.pixmap_item.setClipRect(state["scene_rect"])
            self.crop_rect = state["scene_rect"]
        else:
            self.crop_rect = None

        # sync UI
        self.update_zoom_label()
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(self.current_zoom * 100))
        self.zoom_slider.blockSignals(False)

        self.user_zoomed = True
        self.view_dirty = True
        self.save_as_btn.setEnabled(True)

    def undo(self):
        if not self.undo_stack:
            return

        # save current state for redo
        self.redo_stack.append(self._capture_view_state())

        # restore last undo state
        state = self.undo_stack.pop()
        self._restore_view_state(state)

        self._update_undo_redo_buttons()

    def redo(self):
        if not self.redo_stack:
            return

        # save current state for undo
        self.undo_stack.append(self._capture_view_state())

        # restore last redo state
        state = self.redo_stack.pop()
        self._restore_view_state(state)

        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        self.undo_btn.setEnabled(bool(self.undo_stack))
        self.redo_btn.setEnabled(bool(self.redo_stack))

    def convert_image(self):
        if self.files is None or self.current_idx is None:
            return
        current_path = self.files[self.current_idx]
        filters = (
            "JPEG (*.jpg *.jpeg);;"
            "PNG (*.png);;"
            "HEIC (*.heic *.heif);;"
            "AVIF (*.avif)"
        )
        out_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Convert Image",
            str(current_path.with_suffix("")),
            filters
        )

        if not out_path:
            return

        out_path = Path(out_path)

        if selected_filter.startswith("JPEG") and out_path.suffix.lower() not in (".jpg", ".jpeg"):
            out_path = out_path.with_suffix(".jpg")

        elif selected_filter.startswith("PNG") and out_path.suffix.lower() != ".png":
            out_path = out_path.with_suffix(".png")

        elif selected_filter.startswith("HEIC") and out_path.suffix.lower() not in (".heic", ".heif"):
            out_path = out_path.with_suffix(".heic")

        elif selected_filter.startswith("AVIF") and out_path.suffix.lower() != ".avif":
            out_path = out_path.with_suffix(".avif")

        img = Image.open(self.files[self.current_idx])

        suffix = Path(out_path).suffix.lower()
        save_kwargs = {}

        if suffix in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 95
            save_kwargs["subsampling"] = 0
        elif suffix == ".png":
            save_kwargs["compress_level"] = 9

        img.save(out_path, **save_kwargs)

        self.statusBar().showMessage(
            f"Converted to {Path(out_path).name}", 3000
        )

    def apply_view_rotation(self, img: Image.Image) -> Image.Image:
        if self.view_rotation == 0:
            return img
        # Qt rotation is CW, PIL rotate is CCW
        return img.rotate(-self.view_rotation, expand=True)

    def save_as_view(self):
        if self.files is None or self.current_idx is None or not self.view_dirty:
            return
        current_path = self.files[self.current_idx]
        filters = (
            "JPEG (*.jpg *.jpeg);;"
            "PNG (*.png);;"
            "HEIC (*.heic *.heif);;"
            "AVIF (*.avif)"
        )
        out_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Edited Image As",
            str(current_path.with_name(
                current_path.stem + "_edited" + current_path.suffix
            )),
            "Images (*.jpg *.jpeg *.png *.heic *.heif *.avif)"
        )

        if not out_path:
            return

        out_path = Path(out_path)

        if selected_filter.startswith("JPEG") and out_path.suffix.lower() not in (".jpg", ".jpeg"):
            out_path = out_path.with_suffix(".jpg")

        elif selected_filter.startswith("PNG") and out_path.suffix.lower() != ".png":
            out_path = out_path.with_suffix(".png")

        elif selected_filter.startswith("HEIC") and out_path.suffix.lower() not in (".heic", ".heif"):
            out_path = out_path.with_suffix(".heic")

        elif selected_filter.startswith("AVIF") and out_path.suffix.lower() != ".avif":
            out_path = out_path.with_suffix(".avif")

        img = Image.open(self.files[self.current_idx])

        if self.crop_rect:
            # Convert float coords to int for PIL
            left = int(self.crop_rect.left())
            top = int(self.crop_rect.top())
            right = int(self.crop_rect.right())
            bottom = int(self.crop_rect.bottom())
            img = img.crop((left, top, right, bottom))

        img = self.apply_view_rotation(img)
        # crop will be applied here later

        suffix = Path(out_path).suffix.lower()
        save_kwargs = {}

        if suffix in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 95
            save_kwargs["subsampling"] = 0
        elif suffix == ".png":
            save_kwargs["compress_level"] = 9

        img.save(out_path, **save_kwargs)

        self.statusBar().showMessage(
            f"Saved as {Path(out_path).name}", 3000
        )

    def rotate_view(self, delta):
        self.view_rotation = (self.view_rotation + delta) % 360

        self.view.resetTransform()
        self.view.rotate(self.view_rotation)
        self.view.scale(self.current_zoom, self.current_zoom)

        self.view_dirty = True
        self.save_as_btn.setEnabled(True)
        QTimer.singleShot(0, self._fit_image)

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
        self.current_zoom = 1.0

        self.view.resetTransform()
        self.view.rotate(self.view_rotation)  # keep rotation
        self.view.scale(1.0, 1.0)

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(100)
        self.zoom_slider.blockSignals(False)

        QTimer.singleShot(0, self._fit_image)


    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------

    def _fit_image(self):
        if hasattr(self, "pixmap_item") and not self.user_zoomed:
            self.view.fitInView(
                self.scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio
            )
        t = self.view.transform()
        self.current_zoom = t.m11()

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(self.current_zoom * 100))
        self.zoom_slider.blockSignals(False)

        self.update_zoom_label()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_image()

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "Downloads",
            "Images (*.heic *.heif *.avif *.jpg *.jpeg *.png);;All Files (*)",
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
        if self.crop_mode:
            return
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
        # self.reset_zoom()
        self.reset_view_state()
        self.setWindowTitle(f"{path.name} — HEIC Viewer")

        img = Image.open(path)
        qimage = ImageQt(img)
        pixmap = QPixmap.fromImage(qimage)

        # self.user_zoomed = False
        # self.view_rotation = 0
        # self.current_zoom = 1.0
        # self.view_dirty = False
        # self.save_as_btn.setEnabled(False)
        # self.view.resetTransform()

        self.scene.clear()
        self.pixmap_item = ClippedPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        # self.view.resetTransform()
        self.stack.setCurrentIndex(1)
        QTimer.singleShot(0, self._fit_image)
        # self.view.show()

    def reset_view_state(self):
        self.user_zoomed = False
        self.view_rotation = 0
        self.current_zoom = 1.0
        self.view_dirty = False
        self.crop_rect = None

        self.save_as_btn.setEnabled(False)

        self.view.resetTransform()

        # Clear any existing clip from previous crop
        if hasattr(self, 'pixmap_item') and self.pixmap_item:
            self.pixmap_item.clearClipRect()

    # def _fit_image(self):
    #     if hasattr(self, "pixmap_item"):
    #         if not self.user_zoomed:
    #             self.view.fitInView(
    #                 self.pixmap_item,
    #                 Qt.AspectRatioMode.KeepAspectRatio
    #             )

    def next_image(self):
        if not self.files or self.crop_mode:
            return
        self.current_idx = min(self.current_idx + 1, len(self.files) - 1)
        self.handle_file(str(self.files[self.current_idx]), from_navigation=True)

    def prev_image(self):
        if not self.files or self.crop_mode:
            return
        self.current_idx = max(self.current_idx - 1, 0)
        self.handle_file(str(self.files[self.current_idx]), from_navigation=True)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.top_bar_widget.setVisible(True)
            self.bottom_bar_widget.setVisible(True)
            self.exit_fs_widget.setVisible(False)
        else:
            self.showFullScreen()
            self.top_bar_widget.setVisible(False)
            self.bottom_bar_widget.setVisible(False)
            self.exit_fs_widget.setVisible(True)

    def zoom_actual_size(self):
        if not hasattr(self, "pixmap_item"):
            return

        if self.is_zoom_actual_size:
            self.reset_zoom()
            self.is_zoom_actual_size = False
            return

        self.is_zoom_actual_size = True
        self.user_zoomed = True
        self.current_zoom = 1.0

        self.view.resetTransform()
        self.view.rotate(self.view_rotation)
        self.view.scale(1.0, 1.0)
        self.view.centerOn(self.pixmap_item)

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(100)
        self.zoom_slider.blockSignals(False)
        self.update_zoom_label()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.crop_mode:
                self.cancel_crop()
                return
            if self.isFullScreen():
                self.toggle_fullscreen()
                return
            if self.is_zoom_actual_size:
                self.reset_zoom()
                self.is_zoom_actual_size = False
                return


        super().keyPressEvent(event)

    def set_ui_visible(self, visible: bool):
        self.top_bar_widget.setVisible(visible)
        self.bottom_bar_widget.setVisible(visible)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HeicViewer()
    window.show()
    sys.exit(app.exec())