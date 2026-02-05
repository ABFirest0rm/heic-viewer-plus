from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsPixmapItem

class ClippedPixmapItem(QGraphicsPixmapItem):

    def __init__(self, pixmap):
        super().__init__(pixmap)
        self._clip_rect = None

    # selected crop
    def setClipRect(self, rect):
        self._clip_rect = rect
        self.update()

    # reset crop area
    def clearClipRect(self):
        self._clip_rect = None
        self.update()

    # canvas boundary
    def boundingRect(self):
        if self._clip_rect:
            return self._clip_rect
        return super().boundingRect()

    # restrcit mouse intearaction region
    def shape(self):
        path = QPainterPath()
        if self._clip_rect:
            path.addRect(self._clip_rect)
        else:
            path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        if self._clip_rect:
            painter.setClipRect(self._clip_rect)
        super().paint(painter, option, widget)