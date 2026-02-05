import math
from pathlib import Path

from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtGui import (QShortcut, QKeySequence,
                           QPainter, QPixmap, QColor)
from PySide6.QtWidgets import (QMainWindow, QWidget,
                               QVBoxLayout, QGraphicsScene,
                               QSlider, QLabel, QSizePolicy,
                               QPushButton, QHBoxLayout,
                               QStackedLayout, QMessageBox,
                               QGraphicsRectItem, QFileDialog,
                               QProgressDialog, QApplication)
from PySide6.QtCore import Qt, QRectF, QTimer, QSettings

from .graphics_items import ClippedPixmapItem
from .image_view import ImageView
from .version import (APP_NAME, APP_VERSION,
                      check_for_updates, ORG_NAME,
                      SETTINGS_APP_NAME)
import pillow_heif
pillow_heif.register_heif_opener()

class HeicViewer(QMainWindow):
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif",
                  ".avif", ".webp", ".tif", ".tiff",
                  ".bmp", ".ico"}


    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, SETTINGS_APP_NAME)

        self._init_window()
        self._init_state()
        self._init_menu()
        self._init_shortcuts()
        self._init_view()
        self._init_controls()
        self._init_layout()

        QTimer.singleShot(0, self._check_for_updates)

    def _init_menu(self):
        menubar = self.menuBar()

        self.help_menu = menubar.addMenu("Help")

        about_action = self.help_menu.addAction("About")
        about_action.triggered.connect(self.show_about_dialog)

    def _init_window(self):
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(900, 600)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def _init_state(self):
        # File navigation
        self.files = None
        self.current_idx = None
        self.last_open_dir = self.settings.value("last_open_dir", "", str)

        # View state
        self.current_zoom = 1.0
        self.user_zoomed = False
        self.view_rotation = 0
        self.is_zoom_actual_size = False
        self.flip_h = False
        self.flip_v = False

        # Crop state
        self.crop_mode = False
        self.crop_rect = None
        self._crop_start = None
        self._crop_item = None
        self._crop_overlay_items = []

        # Undo / redo
        self.undo_stack = []
        self.redo_stack = []

    def _init_shortcuts(self):
        # Keyboard Shortcuts
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.next_image)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.prev_image)

        QShortcut(QKeySequence(Qt.Key_F11), self, activated=self.toggle_fullscreen)

        QShortcut(QKeySequence.Undo, self, activated=self.undo)
        QShortcut(QKeySequence.Redo, self, activated=self.redo)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.zoom_actual_size)

        QShortcut(QKeySequence(Qt.Key_Return), self, activated=self._on_crop_enter)
        QShortcut(QKeySequence(Qt.Key_Enter), self, activated=self._on_crop_enter)

        QShortcut(QKeySequence("Ctrl+Right"), self, activated=lambda: self.rotate_and_flip(90))
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=lambda: self.rotate_and_flip(-90))

        QShortcut(QKeySequence("Ctrl+Shift+Left"), self, activated=self.flip_horizontal)
        QShortcut(QKeySequence("Ctrl+Shift+Right"), self, activated=self.flip_horizontal)
        QShortcut(QKeySequence("Ctrl+Shift+Up"), self, activated=self.flip_vertical)
        QShortcut(QKeySequence("Ctrl+Shift+Down"), self, activated=self.flip_vertical)

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._on_escape)

    def _init_view(self):
        self.scene = QGraphicsScene(self)
        self.view = ImageView(self.scene, self, self)
        self.view.setAcceptDrops(False)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setRenderHints(QPainter.SmoothPixmapTransform)
        self.view.zoomed.connect(self.on_wheel_zoom)
        self.view.resetRequested.connect(self.reset_zoom)

    def _init_controls(self):
        # Zoom controls
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(220)
        self.zoom_slider.valueChanged.connect(self.on_slider_zoom)
        self.zoom_slider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignCenter)

        self.actual_size_btn = QPushButton("1:1")
        self.actual_size_btn.setToolTip("Actual Size 1:1 (Ctrl+F)")
        self.actual_size_btn.clicked.connect(self.zoom_actual_size)

        # Buttons
        self.open_button_top = QPushButton("Open")
        self.open_button_top.clicked.connect(self.open_file)

        self.convert_btn = QPushButton("Convert Original")
        self.convert_btn.setToolTip(
            "Convert the original image to another format.\n"
            "PNG is saved lossless.\n"
            "JPEG, WEBP, HEIC, and AVIF use high-quality compression."
        )
        self.convert_btn.clicked.connect(self.convert_image)

        self.save_as_btn = QPushButton("Save As")
        self.save_as_btn.setToolTip(
            "Save a copy with edits applied.\n"
            "PNG is saved lossless.\n"
            "JPEG, WEBP, HEIC, and AVIF use high-quality compression."
        )
        self.save_as_btn.setEnabled(False)
        self.save_as_btn.clicked.connect(self.save_as_view)

        self.rotate_left_btn = QPushButton("⟲")
        self.rotate_left_btn.setToolTip("Rotate 90° Left (Ctrl + ←)")
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_and_flip(-90))

        self.rotate_right_btn = QPushButton("⟳")
        self.rotate_right_btn.setToolTip("Rotate 90° Right (Ctrl + →)")
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_and_flip(90))

        self.flip_h_btn = QPushButton("⇋")
        self.flip_h_btn.setToolTip("Flip Horizontal (Ctrl + Shift + ← / →)")
        self.flip_h_btn.clicked.connect(self.flip_horizontal)

        self.flip_v_btn = QPushButton("⇅")
        self.flip_h_btn.setToolTip("Flip Horizontal (Ctrl + Shift + ← / →)")
        self.flip_v_btn.clicked.connect(self.flip_vertical)

        self.crop_btn = QPushButton("Crop")
        self.crop_btn.clicked.connect(self.enter_crop_mode)

        self.crop_done_btn = QPushButton("Done")
        self.crop_done_btn.setToolTip("Done (Enter)")
        self.crop_done_btn.setVisible(False)
        self.crop_done_btn.clicked.connect(self.commit_crop)

        self.crop_cancel_btn = QPushButton("Cancel")
        self.crop_cancel_btn.setToolTip("Cancel (Esc)")
        self.crop_cancel_btn.setVisible(False)
        self.crop_cancel_btn.clicked.connect(self.cancel_crop)

        self.undo_btn = QPushButton("Undo Crop")
        self.undo_btn.setToolTip(
            "Ctrl + Z\n"
            "CAUTION:\n"
            "Restores the image to the state before the last crop.\n"
            "Any rotation or flip applied after that crop will be lost."
        )
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo)

        self.redo_btn = QPushButton("Redo Crop")
        self.redo_btn.setToolTip(
            "CTRL + Y\n"
            "CAUTION:\n"
            "Reapplies the last undone crop.\n"
            "Any rotation or flip applied after that crop will be lost."
        )

        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.redo)

        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setToolTip("Fullscreen mode")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        self.exit_fullscreen_btn = QPushButton("✕")
        self.exit_fullscreen_btn.setToolTip("Exit Fullscreen (Esc)")
        self.exit_fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        # Exit fullscreen overlay
        self.exit_fs_widget = QWidget(self.view)
        self.exit_fs_widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.exit_fs_widget.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 80);
                border-radius: 6px;
            }
        """)
        exit_fs_layout = QHBoxLayout(self.exit_fs_widget)
        exit_fs_layout.setContentsMargins(6, 6, 6, 6)
        exit_fs_layout.addStretch()
        exit_fs_layout.addWidget(self.exit_fullscreen_btn)
        self.exit_fs_widget.setVisible(False)

    def _init_layout(self):
        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedLayout()
        main_layout.addLayout(self.stack)

        start_page = QWidget()
        start_layout = QVBoxLayout(start_page)

        open_center = QPushButton("Open Image")
        open_center.setFixedWidth(180)
        open_center.clicked.connect(self.open_file)

        start_layout.addStretch()
        start_layout.addWidget(open_center, alignment=Qt.AlignCenter)
        start_layout.addStretch()

        viewer_page = QWidget()
        viewer_layout = QVBoxLayout(viewer_page)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)

        self.top_bar_widget = QWidget()
        top_bar = QHBoxLayout(self.top_bar_widget)
        top_bar.setContentsMargins(6, 6, 6, 6)

        top_bar.addWidget(self.convert_btn)
        top_bar.addWidget(self.crop_btn)
        top_bar.addWidget(self.crop_done_btn)
        top_bar.addWidget(self.crop_cancel_btn)
        top_bar.addWidget(self.rotate_left_btn)
        top_bar.addWidget(self.rotate_right_btn)
        top_bar.addWidget(self.flip_h_btn)
        top_bar.addWidget(self.flip_v_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.open_button_top)
        top_bar.addWidget(self.save_as_btn)

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

        viewer_layout.addWidget(self.top_bar_widget)
        viewer_layout.addWidget(self.view, stretch=1)
        viewer_layout.addWidget(self.exit_fs_widget)
        viewer_layout.addWidget(self.bottom_bar_widget)

        self.stack.addWidget(start_page)
        self.stack.addWidget(viewer_page)
        self.stack.setCurrentIndex(0)

    def _set_crop_ui(self, enabled: bool):
        self.crop_btn.setEnabled(not enabled)
        self.crop_done_btn.setVisible(enabled)
        self.crop_cancel_btn.setVisible(enabled)

        for btn in (
                self.rotate_left_btn,
                self.rotate_right_btn,
                self.convert_btn,
                self.flip_h_btn,
                self.flip_v_btn,
                self.open_button_top,
        ):
            btn.setEnabled(not enabled)

    # Crop Button
    def enter_crop_mode(self):
        self.crop_mode = True

        self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self._set_crop_ui(True)

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
        self.view.viewport().unsetCursor()
        self._set_crop_ui(False)

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

        self.undo_stack.append(self._capture_view_state())
        self.redo_stack.clear()
        self._update_undo_redo_buttons()

        # Convert crop rect to scene coordinates
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
        self._sync_zoom_ui_from_view()

        self.save_as_btn.setEnabled(True)

        self.exit_crop_mode()

    def update_crop_overlay(self, crop_rect: QRectF):
        self.clear_crop_overlay()

        if not self.pixmap_item:
            return

        img_rect = self.pixmap_item.boundingRect()

        dim_color = QColor(0, 0, 0, 140)

        top = QRectF(
            img_rect.left(),
            img_rect.top(),
            img_rect.width(),
            crop_rect.top() - img_rect.top()
        )

        bottom = QRectF(
            img_rect.left(),
            crop_rect.bottom(),
            img_rect.width(),
            img_rect.bottom() - crop_rect.bottom()
        )

        left = QRectF(
            img_rect.left(),
            crop_rect.top(),
            crop_rect.left() - img_rect.left(),
            crop_rect.height()
        )

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

        self.view.setTransform(state["transform"])
        self.scene.setSceneRect(state["scene_rect"])

        self.current_zoom = state["zoom"]
        self.view_rotation = state["rotation"]

        self.pixmap_item.clearClipRect()

        full_rect = self.pixmap_item.sceneBoundingRect()

        if state["scene_rect"] != full_rect:
            self.pixmap_item.setClipRect(state["scene_rect"])
            self.crop_rect = state["scene_rect"]
        else:
            self.crop_rect = None

        self.update_zoom_label()
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(self.current_zoom * 100))
        self.zoom_slider.blockSignals(False)

        self.user_zoomed = True
        self.save_as_btn.setEnabled(True)

    def undo(self):
        if not self.undo_stack:
            return

        self.redo_stack.append(self._capture_view_state())

        state = self.undo_stack.pop()
        self._restore_view_state(state)

        self._update_undo_redo_buttons()

    def redo(self):
        if not self.redo_stack:
            return

        self.undo_stack.append(self._capture_view_state())

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
            "AVIF (*.avif);;"""
            "WEBP (*.webp)"
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

        elif selected_filter.startswith("WEBP") and out_path.suffix.lower() != ".webp":
            out_path = out_path.with_suffix(".webp")

        progress = QProgressDialog("Converting image...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        try:
            img = Image.open(current_path)
            img = ImageOps.exif_transpose(img)
            img.load()

            suffix = Path(out_path).suffix.lower()
            save_kwargs = {}

            if suffix in (".jpg", ".jpeg"):
                save_kwargs["quality"] = 95
                save_kwargs["subsampling"] = 0
            elif suffix == ".png":
                save_kwargs["compress_level"] = 9
            elif suffix == ".webp":
                save_kwargs["quality"] = 90
                save_kwargs["method"] = 6

            img.save(out_path, **save_kwargs)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Conversion Failed",
                f"Could not convert image:\n\n{current_path.name}\n\n{str(e)}"
            )
            return

        finally:
            progress.close()


        self.statusBar().showMessage(
            f"Converted to {Path(out_path).name}", 3000
        )
        QTimer.singleShot(3000, lambda: self.update_image_info(current_path, img))

    def save_as_view(self):
        if self.files is None or self.current_idx is None:
            return
        current_path = self.files[self.current_idx]
        filters = (
            "JPEG (*.jpg *.jpeg);;"
            "PNG (*.png);;"
            "HEIC (*.heic *.heif);;"
            "AVIF (*.avif);;"
            "WEBP (*.webp)"
        )
        out_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Edited Image As",
            str(current_path.with_name(
                current_path.stem + "_edited" + current_path.suffix
            )),
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

        elif selected_filter.startswith("WEBP") and out_path.suffix.lower() != ".webp":
            out_path = out_path.with_suffix(".webp")

        progress = QProgressDialog("Saving image...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        try:
            img = Image.open(self.files[self.current_idx])
            img = ImageOps.exif_transpose(img)
            img.load()

            if self.crop_rect:

                left = int(self.crop_rect.left())
                top = int(self.crop_rect.top())
                right = int(self.crop_rect.right())
                bottom = int(self.crop_rect.bottom())
                img = img.crop((left, top, right, bottom))

            img = self.apply_view_rotation(img)

            if self.flip_h:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            if self.flip_v:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)

            suffix = Path(out_path).suffix.lower()
            save_kwargs = {}

            if suffix in (".jpg", ".jpeg"):
                save_kwargs["quality"] = 95
                save_kwargs["subsampling"] = 0
            elif suffix == ".png":
                save_kwargs["compress_level"] = 9
            elif suffix == ".webp":
                save_kwargs["quality"] = 90
                save_kwargs["method"] = 6

            img.save(out_path, **save_kwargs)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save the edited image:\n\n{out_path.name}\n\n{str(e)}"
            )
            return

        finally:
            progress.close()

        self.save_as_btn.setEnabled(False)

        self.statusBar().showMessage(
            f"Saved as {Path(out_path).name}", 3000
        )
        QTimer.singleShot(3000, lambda: self.update_image_info(current_path, img))


    def apply_view_rotation(self, img):
        if self.view_rotation == 0:
            return img
        return img.rotate(-self.view_rotation, expand=True)

    def rotate_and_flip(self, delta):
        if not hasattr(self, "pixmap_item"):
            return

        self.view_rotation = (self.view_rotation + delta) % 360

        center_scene = self.view.mapToScene(self.view.viewport().rect().center())
        keep_zoom = self.user_zoomed or self.is_zoom_actual_size

        self._apply_base_transform()

        if keep_zoom:
            self.view.scale(self.current_zoom, self.current_zoom)
            self.view.centerOn(center_scene)
            self._sync_zoom_ui_from_view()
        else:
            self.user_zoomed = False
            QTimer.singleShot(0, self._fit_image)

        self.save_as_btn.setEnabled(True)

    def on_wheel_zoom(self, factor):
        new_zoom = self.current_zoom * factor
        new_zoom = max(0.1, min(new_zoom, 4.0))

        self.set_zoom(new_zoom)

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(new_zoom * 100))
        self.zoom_slider.blockSignals(False)

    def on_slider_zoom(self, value):
        self.set_zoom(value / 100.0)

    def update_zoom_label(self):
        self.zoom_label.setText(f"{int(self.current_zoom * 100)}%")

    def reset_zoom(self):
        self.user_zoomed = False
        self.is_zoom_actual_size = False
        QTimer.singleShot(0, self._fit_image)

    def _apply_base_transform(self):

        self.view.resetTransform()

        sx = -1 if self.flip_h else 1
        sy = -1 if self.flip_v else 1
        self.view.scale(sx, sy)
        self.view.rotate(self.view_rotation)

    def _fit_image(self):
        if hasattr(self, "pixmap_item") and not self.user_zoomed:
            self.view.fitInView(
                self.scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio
            )
            self._sync_zoom_ui_from_view()
            return
        self._sync_zoom_ui_from_view()

    def _fit_scene_rect_preserving_base(self, rect):

        if rect.isEmpty():
            return

        self._apply_base_transform()
        vp = self.view.viewport().rect()
        mapped = self.view.transform().mapRect(rect)

        if mapped.isEmpty():
            return

        margin = 6.0
        avail_w = max(1.0, vp.width() - margin)
        avail_h = max(1.0, vp.height() - margin)

        rw = max(1e-6, mapped.width())
        rh = max(1e-6, mapped.height())

        s = min(avail_w / rw, avail_h / rh)

        self.view.scale(s, s)
        self.view.centerOn(rect.center())
        self._sync_zoom_ui_from_view()

    def _transform_scale(self, t):
        return math.hypot(t.m11(), t.m12())

    def _sync_zoom_ui_from_view(self):
        self.current_zoom = self._transform_scale(self.view.transform())

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(round(self.current_zoom * 100)))
        self.zoom_slider.blockSignals(False)

        self.update_zoom_label()

    def set_zoom(self, zoom: float):
        zoom = max(0.1, min(zoom, 4.0))

        cur = max(self.current_zoom, 1e-6)
        factor = zoom / cur

        self.view.scale(factor, factor)

        self.user_zoomed = True
        self.is_zoom_actual_size = False
        self._sync_zoom_ui_from_view()

        self.update_zoom_label()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_image()
        self._position_exit_fs_widget()

    def open_file(self):
        start_dir = self.last_open_dir or str(Path.home() / "Pictures")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            start_dir,
            "Images (*.heic *.heif *.avif *.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp *.ico);;All Files (*)",
        )

        if file_path:
            self.handle_file(file_path)
            self.last_open_dir = str(Path(file_path).parent)
            self.settings.setValue("last_open_dir", self.last_open_dir)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.crop_mode:
            if not self.confirm_discard_crop():
                return
            self.clear_crop_preview()
            self.exit_crop_mode()

        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return

        file_path = urls[0].toLocalFile()
        self.handle_file(file_path)
        event.acceptProposedAction()

    def handle_file(self, file_path, from_navigation=False):
        path = Path(file_path)
        if not path.exists():
            QMessageBox.critical(
                self,
                "File not found",
                f"Could not find file:\n\n{path.name}\n"
            )
            return

        parent = path.parent

        if not from_navigation:
            files = [p for p in parent.iterdir()
                     if p.is_file() and p.suffix.lower() in HeicViewer.IMAGE_EXTS]
            files.sort()

            if path not in files:
                return

            self.files = files
            self.current_idx = files.index(path)


        self.reset_view_state()
        self.setWindowTitle(f"{path.name} — {APP_NAME} v{APP_VERSION}")

        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            img.load()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Failed to Open Image",
                f"Could not open the image:\n\n{path.name}\n\n{str(e)}"
            )
            return

        self.update_image_info(path, img)
        qimage = ImageQt(img)
        pixmap = QPixmap.fromImage(qimage)

        self.scene.clear()
        self.pixmap_item = ClippedPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.stack.setCurrentIndex(1)
        self.help_menu.menuAction().setVisible(False)
        QTimer.singleShot(0, self._fit_image)

    def reset_view_state(self):
        self.user_zoomed = False
        self.view_rotation = 0
        self.current_zoom = 1.0
        self.crop_rect = None
        self.is_zoom_actual_size = False

        self.flip_h = False
        self.flip_v = False

        self.save_as_btn.setEnabled(False)
        self.view.resetTransform()

        if hasattr(self, "pixmap_item") and self.pixmap_item:
            self.pixmap_item.clearClipRect()

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
            QTimer.singleShot(0, self._position_exit_fs_widget)

    def zoom_actual_size(self):
        if not hasattr(self, "pixmap_item"):
            return

        if self.is_zoom_actual_size:
            self.is_zoom_actual_size = False
            self.reset_zoom()
            return

        self.is_zoom_actual_size = True
        self.user_zoomed = True
        self.current_zoom = 1.0

        center_scene = self.view.mapToScene(self.view.viewport().rect().center())

        self._apply_base_transform()
        self.view.scale(1.0, 1.0)
        self.view.centerOn(center_scene)

        self._sync_zoom_ui_from_view()

    def _on_escape(self):
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

    def set_ui_visible(self, visible: bool):
        self.top_bar_widget.setVisible(visible)
        self.bottom_bar_widget.setVisible(visible)

    def update_image_info(self, path, img):
        width, height = img.size

        size_bytes = path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)

        ext = path.suffix.upper().replace(".", "")

        self.statusBar().showMessage(
            f"{width} × {height}   |   {size_mb:.2f} MB   |   {ext}"
        )


    def flip_horizontal(self):
        if not hasattr(self, "pixmap_item"):
            return

        self.flip_h = not self.flip_h
        self.rotate_and_flip(0)

    def flip_vertical(self):
        if not hasattr(self, "pixmap_item"):
            return

        self.flip_v = not self.flip_v
        self.rotate_and_flip(0)

    def _position_exit_fs_widget(self):
        if not self.exit_fs_widget.isVisible():
            return

        margin = 12
        size = self.exit_fs_widget.sizeHint()
        vp = self.view.viewport().rect()

        x = vp.right() - size.width() - margin
        y = vp.top() + margin

        self.exit_fs_widget.setGeometry(x, y, size.width(), size.height())

    def _check_for_updates(self):
        try:
            latest = check_for_updates(APP_VERSION)
        except Exception:
            return
        if latest:
            QMessageBox.information(
                self,
                "Update Available",
                f"New version available: {latest}\n\nVisit GitHub to download."
            )

    def show_about_dialog(self):
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            (
                f"<b>{APP_NAME}</b><br>"
                f"Version {APP_VERSION}<br><br>"
                "A lightweight desktop tool to view, crop, and convert modern image formats.<br><br>"
                "Built with PySide6 (Qt), Pillow, and pillow-heif.<br>"
                'Project page: <a href="https://github.com/ABFirest0rm/heic-viewer-plus">'
                "github.com/ABFirest0rm/heic-viewer-plus</a><br>"
                "Licenses available on GitHub."
            ),
        )
