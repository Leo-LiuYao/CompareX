"""Fluent-style pill segment switch (shared paint logic)."""
from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRectF, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QMouseEvent, QPen
from PyQt6.QtWidgets import QWidget, QSizePolicy

from qfluentwidgets.common.font import getFont


class SegmentSwitch(QWidget):
    """Two-segment pill: rounded track + sliding highlight."""

    value_changed = pyqtSignal(str)

    ITEM_GAP = 0
    ITEM_PAD_H = 10
    TRACK_H = 26
    TRACK_RADIUS = 7
    THUMB_INSET = 2

    def __init__(
        self,
        items: Tuple[Tuple[str, str], ...],
        *,
        initial: str,
        tooltip: str = '',
        parent=None,
    ):
        super().__init__(parent)
        self.ITEMS = items
        self._value = initial
        self._colors: Dict[str, str] = {}
        self._hover_index = -1
        self._item_rects: List[QRectF] = []
        self._thumb_x = 0.0
        self._thumb_w = 48.0

        self._anim = QPropertyAnimation(self, b'thumbX', self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setFixedHeight(32)
        self.setFixedWidth(self._natural_width())
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)

    def get_thumb_x(self) -> float:
        return self._thumb_x

    def set_thumb_x(self, x: float):
        self._thumb_x = x
        self.update()

    thumbX = pyqtProperty(float, get_thumb_x, set_thumb_x)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, *, animate: bool = True, emit: bool = True):
        valid = {k for k, _ in self.ITEMS}
        if value not in valid:
            return
        changed = self._value != value
        self._value = value
        self._layout_items()
        self._move_thumb(animate=animate)
        self.update()
        if emit and changed:
            self.value_changed.emit(value)

    def set_item_labels(
        self,
        items: Tuple[Tuple[str, str], ...],
        *,
        tooltip: str = '',
    ):
        self.ITEMS = items
        if tooltip:
            self.setToolTip(tooltip)
        self.setFixedWidth(self._natural_width())
        self._layout_items()
        self._move_thumb(animate=False)
        self.update()

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self.update()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        self._hover_index = -1
        self.update()

    def _label_font(self, *, selected: bool = False) -> QFont:
        return getFont(11, QFont.Weight.DemiBold if selected else QFont.Weight.Normal)

    def _natural_width(self) -> int:
        fm = QFontMetrics(self._label_font())
        total = self.THUMB_INSET * 2
        for i, (_, label) in enumerate(self.ITEMS):
            total += fm.horizontalAdvance(label) + self.ITEM_PAD_H * 2
            if i < len(self.ITEMS) - 1:
                total += self.ITEM_GAP
        return max(total, 80)

    def _track_rect(self) -> QRectF:
        return QRectF(0, (self.height() - self.TRACK_H) / 2, self.width(), self.TRACK_H)

    def _layout_items(self):
        self._item_rects = []
        track = self._track_rect()
        fm = QFontMetrics(self._label_font())
        x = track.x() + self.THUMB_INSET
        y = track.y()
        h = track.height()
        for i, (_, label) in enumerate(self.ITEMS):
            item_w = fm.horizontalAdvance(label) + self.ITEM_PAD_H * 2
            self._item_rects.append(QRectF(x, y, item_w, h))
            x += item_w + self.ITEM_GAP

    def _selected_index(self) -> int:
        for i, (key, _) in enumerate(self.ITEMS):
            if key == self._value:
                return i
        return 0

    def _target_thumb(self) -> Tuple[float, float]:
        idx = self._selected_index()
        if not self._item_rects:
            self._layout_items()
        if idx >= len(self._item_rects):
            return 0.0, self._thumb_w
        rect = self._item_rects[idx]
        inset = self.THUMB_INSET
        return rect.x() + inset / 2, max(24.0, rect.width() - inset)

    def _move_thumb(self, *, animate: bool):
        x, w = self._target_thumb()
        self._thumb_w = w
        if animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._thumb_x)
            self._anim.setEndValue(x)
            self._anim.start()
        else:
            self._thumb_x = x
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_items()
        self._move_thumb(animate=False)

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_items()
        self._move_thumb(animate=False)

    def mousePressEvent(self, event: QMouseEvent):
        if not self.isEnabled():
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        for i, (key, _) in enumerate(self.ITEMS):
            if i < len(self._item_rects) and self._item_rects[i].contains(event.position()):
                self.set_value(key, animate=True, emit=True)
                return

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.isEnabled():
            if self._hover_index != -1:
                self._hover_index = -1
                self.update()
            return
        hover = -1
        for i, rect in enumerate(self._item_rects):
            if rect.contains(event.position()):
                hover = i
                break
        if hover != self._hover_index:
            self._hover_index = hover
            self.update()

    def leaveEvent(self, event):
        self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)

        c = self._colors
        disabled = not self.isEnabled()
        if disabled:
            dim = QColor(c.get('text_dim', '#9E9E9E'))
            accent = dim
            muted = dim
            fg = dim
            track_bg = QColor(c.get('panel_border', '#E5E5E5'))
            thumb_bg = track_bg
            border = track_bg
        else:
            accent = QColor(c.get('accent', '#0078D4'))
            muted = QColor(c.get('text_muted', '#888'))
            fg = QColor(c.get('foreground', '#333'))
            track_bg = QColor(c.get('canvas_bg', '#EBEBEB'))
            thumb_bg = QColor(c.get('panel_bg', '#FFFFFF'))
            border = QColor(c.get('panel_border', '#E5E5E5'))

        if not self._item_rects:
            self._layout_items()

        track = self._track_rect()

        # Track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_bg)
        painter.drawRoundedRect(track, self.TRACK_RADIUS, self.TRACK_RADIUS)

        # Sliding highlight
        thumb = QRectF(
            self._thumb_x,
            track.y() + self.THUMB_INSET,
            self._thumb_w,
            track.height() - self.THUMB_INSET * 2,
        )
        painter.setBrush(thumb_bg)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(thumb, self.TRACK_RADIUS - 2, self.TRACK_RADIUS - 2)

        # Labels
        for i, (key, label) in enumerate(self.ITEMS):
            if i >= len(self._item_rects):
                continue
            rect = self._item_rects[i]
            selected = key == self._value
            hovered = i == self._hover_index

            painter.setFont(
                self._label_font(selected=selected and not disabled)
            )
            if disabled:
                painter.setPen(dim)
            elif selected:
                painter.setPen(accent)
            elif hovered:
                painter.setPen(fg)
            else:
                painter.setPen(muted)

            painter.drawText(
                rect.toRect(),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
