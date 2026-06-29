"""Single-image zoom preview dialog."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QWidget, QLabel
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent, QImage, QColor
from PyQt6.QtCore import Qt, QPoint, QRectF
from typing import Optional
import numpy as np

from config import MIN_ZOOM, MAX_ZOOM, ZOOM_WHEEL_FACTOR, ZOOM_WHEEL_DEGREES
from core.image_loader import ImageInfo, ImageLoader
from ui.compare_dialog import array_to_qimage
from ui.theme import get_colors


class PreviewCanvas(QWidget):
    def __init__(self, image_info: ImageInfo, image_loader: ImageLoader):
        super().__init__()
        self.image_loader = image_loader
        self.image_info = image_info
        self.qimage: Optional[QImage] = None
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._panning = False
        self._pan_start: Optional[QPoint] = None
        self._pan_origin = (0.0, 0.0)
        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._load()

    def _load(self):
        pil = self.image_loader.load_full_image(self.image_info.path)
        if pil is None:
            return
        if pil.mode == 'RGBA':
            arr = np.array(pil)
        else:
            arr = np.array(pil.convert('RGB'))
        self.qimage = array_to_qimage(arr)
        self._fit_view()
        self.update()

    def _fit_view(self):
        if not self.qimage or self.qimage.isNull() or self.width() < 10:
            return
        iw, ih = self.qimage.width(), self.qimage.height()
        scale = min(self.width() / iw, self.height() / ih) * 0.95
        self.zoom = max(MIN_ZOOM, min(1.0, scale))
        self.pan_x = 0.0
        self.pan_y = 0.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_view()
        self.update()

    def paintEvent(self, event):
        colors = get_colors()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(colors['canvas_bg']))
        if not self.qimage or self.qimage.isNull():
            painter.setPen(QColor(colors['text_muted']))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "无法加载图片")
            return
        iw, ih = self.qimage.width(), self.qimage.height()
        base = min(self.width() / iw, self.height() / ih)
        scale = base * self.zoom
        dw, dh = iw * scale, ih * scale
        x = (self.width() - dw) / 2 + self.pan_x
        y = (self.height() - dh) / 2 + self.pan_y
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(QRectF(x, y, dw, dh), self.qimage, QRectF(0, 0, iw, ih))
        painter.setPen(QColor(colors['text_muted']))
        painter.drawText(
            8, self.height() - 8,
            f"滚轮缩放 · 拖拽平移 · R 适应窗口 · Esc 关闭 · {int(self.zoom * 100)}%",
        )

    def wheelEvent(self, event: QWheelEvent):
        if not self.qimage:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        steps = delta / ZOOM_WHEEL_DEGREES
        factor = ZOOM_WHEEL_FACTOR ** steps
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._pan_start = event.pos()
            self._pan_origin = (self.pan_x, self.pan_y)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning and self._pan_start:
            d = event.pos() - self._pan_start
            self.pan_x = self._pan_origin[0] + d.x()
            self.pan_y = self._pan_origin[1] + d.y()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.window().close()
        elif event.key() == Qt.Key.Key_R:
            self._fit_view()
            self.update()
        else:
            super().keyPressEvent(event)


class ImagePreviewDialog(QDialog):
    def __init__(self, image_info: ImageInfo, image_loader: ImageLoader, parent=None):
        super().__init__(parent)
        w, h = image_info.resolution
        self.setWindowTitle(f"{image_info.name}  ({w}×{h})")
        self.resize(min(1200, max(640, w)), min(900, max(480, h)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = PreviewCanvas(image_info, image_loader)
        layout.addWidget(self.canvas, stretch=1)
        meta = QLabel(f"{image_info.path}")
        colors = get_colors()
        meta.setStyleSheet(
            f"color: {colors['text_dim']}; font-size: 10px; padding: 4px 8px; "
            f"background: {colors['panel_bg']};"
        )
        meta.setWordWrap(True)
        layout.addWidget(meta)

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.setFocus()
