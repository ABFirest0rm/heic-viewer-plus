from PySide6.QtWidgets import QGraphicsView, QGraphicsRectItem
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPen, QColor

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