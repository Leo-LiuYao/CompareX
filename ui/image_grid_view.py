"""
Main display - single-folder list / multi-folder column grid (Ocolor style).
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QGridLayout, QPushButton, QFrame, QSizePolicy, QApplication,
    QRubberBand,
)
from PyQt6.QtGui import (
    QPixmap, QImage, QDragEnterEvent, QDropEvent, QMouseEvent, QPainter, QColor, QFont, QFontMetrics,
    QContextMenuEvent, QWheelEvent, QDragMoveEvent, QDragLeaveEvent, QNativeGestureEvent,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QEvent
from typing import List, Optional, Set, Dict
import logging
import sys

from core.image_loader import ImageInfo
from core.thumbnail_service import ThumbnailService
from config import (
    THUMB_SCALE_PRESETS, DEFAULT_THUMB_SCALE,
    THUMB_WHEEL_PIXEL_THRESHOLD, THUMB_MOUSE_WHEEL_NOTCHES, ZOOM_WHEEL_DEGREES,
)
from PIL import Image

from utils.cache import image_cache
from i18n import tr
from utils.file_utils import validate_folder_path, format_file_size
from ui.theme import get_colors
from ui.folder_drag import folder_path_from_mime, start_folder_drag
from qfluentwidgets import FluentIcon as FIF, Theme, isDarkTheme
from ui.qt_icons import close_button_style, CLOSE_BTN_ICON, CLOSE_BTN_SIZE
from ui.gesture_zoom import enable_pinch_gestures, try_handle_pinch_event

logger = logging.getLogger(__name__)

BASE_THUMB_W, BASE_THUMB_H = 96, 72
MIN_THUMB_SCALE = THUMB_SCALE_PRESETS[0]
MAX_THUMB_SCALE = THUMB_SCALE_PRESETS[-1]
# Grid thumbnails Cmd/Ctrl+wheel: separate trackpad vs mouse accumulation
THUMB_SOURCE_W = int(BASE_THUMB_W * MAX_THUMB_SCALE)
THUMB_SOURCE_H = int(BASE_THUMB_H * MAX_THUMB_SCALE)


def _thumb_preset_index(scale: float) -> int:
    return min(
        range(len(THUMB_SCALE_PRESETS)),
        key=lambda i: abs(THUMB_SCALE_PRESETS[i] - scale),
    )


def step_thumb_scale(scale: float, zoom_in: bool) -> float:
    idx = _thumb_preset_index(scale)
    if zoom_in:
        idx = min(len(THUMB_SCALE_PRESETS) - 1, idx + 1)
    else:
        idx = max(0, idx - 1)
    return THUMB_SCALE_PRESETS[idx]


def thumb_scale_to_slider_index(scale: float) -> int:
    return _thumb_preset_index(scale)


def slider_index_to_thumb_scale(index: int) -> float:
    idx = max(0, min(len(THUMB_SCALE_PRESETS) - 1, index))
    return THUMB_SCALE_PRESETS[idx]


def _is_trackpad_wheel(event: QWheelEvent) -> bool:
    pd = event.pixelDelta()
    return pd.y() != 0 or pd.x() != 0


def _wheel_zoom_modifier(modifiers) -> bool:
    """Ctrl (Win/Linux) or Command (macOS) + wheel zoom."""
    return bool(
        modifiers
        & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
    )


def _preview_grid_view(widget: QWidget):
    w = widget
    while w:
        if hasattr(w, '_handle_thumb_wheel') and hasattr(w, '_thumb_scale'):
            return w
        w = w.parentWidget()
    return None


def _forward_thumb_wheel(widget: QWidget, event: QWheelEvent) -> bool:
    view = _preview_grid_view(widget)
    if view is not None and _wheel_zoom_modifier(event.modifiers()):
        return view._handle_thumb_wheel(event)
    return False


def _forward_pinch_zoom(widget: QWidget, event) -> bool:
    view = _preview_grid_view(widget)
    if view is None:
        return False
    return view._process_preview_pinch_event(event)


class PreviewGridInteractionMixin:
    """Thumbnail wheel zoom + rubber-band selection on empty area."""

    def _init_preview_interaction(self):
        self._wheel_accum_trackpad = 0
        self._wheel_accum_mouse = 0.0
        self._native_pinch_active = False
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.container)
        self._rubber_band.hide()
        self._marquee_origin = QPoint()
        self._marquee_active = False
        for target in (self, self.viewport(), self.container):
            enable_pinch_gestures(target)
            target.installEventFilter(self)
        self.container.setMouseTracking(True)

    def _track_native_pinch(self, event) -> None:
        if event.type() != QEvent.Type.NativeGesture:
            return
        if not isinstance(event, QNativeGestureEvent):
            return
        if event.gestureType() != Qt.NativeGestureType.ZoomNativeGesture:
            return
        if event.isBeginEvent():
            self._native_pinch_active = True
        elif event.isEndEvent():
            self._native_pinch_active = False

    def _process_preview_pinch_event(self, event) -> bool:
        """Handle preview pinch; return True if event consumed."""
        self._track_native_pinch(event)

        if (
            event.type() == QEvent.Type.Gesture
            and sys.platform == 'darwin'
            and self._native_pinch_active
        ):
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None:
                event.accept(pinch)
            return True

        pixels = try_handle_pinch_event(event, thumb_mode=True)
        if pixels is None:
            return False
        if pixels != 0:
            self._apply_thumb_pinch_pixels(pixels)
        return True

    def _iter_selectable_cells(self) -> List["SelectableImageCell"]:
        raise NotImplementedError

    def _iter_thumb_cells(self) -> List["SelectableImageCell"]:
        """Resize all cells that depend on thumbnail scale (incl. placeholders)."""
        return self._iter_selectable_cells()

    def _point_blocks_marquee(self, pos: QPoint) -> bool:
        w = self.container.childAt(pos)
        while w and w is not self.container:
            if isinstance(w, (SelectableImageCell, ColumnHeader)):
                return True
            w = w.parentWidget()
        return False

    def _apply_thumb_pinch_pixels(self, pixels: float) -> bool:
        if pixels == 0:
            return True
        self._wheel_accum_trackpad += pixels
        if abs(self._wheel_accum_trackpad) < THUMB_WHEEL_PIXEL_THRESHOLD:
            return True
        zoom_in = self._wheel_accum_trackpad > 0
        self._wheel_accum_trackpad = 0
        new_scale = step_thumb_scale(self._thumb_scale, zoom_in)
        if abs(new_scale - self._thumb_scale) > 0.01:
            self._thumb_scale = new_scale
            self._apply_thumb_scale()
            self._emit_thumb_scale_changed()
        return True

    def _handle_thumb_wheel(self, event: QWheelEvent) -> bool:
        if _is_trackpad_wheel(event):
            pd = event.pixelDelta()
            dy = pd.y() if pd.y() != 0 else pd.x()
            if dy == 0:
                return False
            if self._apply_thumb_pinch_pixels(dy):
                event.accept()
                return True
            return False
        else:
            ad = event.angleDelta().y()
            if ad == 0:
                return False
            self._wheel_accum_mouse += ad / float(ZOOM_WHEEL_DEGREES)
            if abs(self._wheel_accum_mouse) < THUMB_MOUSE_WHEEL_NOTCHES:
                event.accept()
                return True
            zoom_in = self._wheel_accum_mouse > 0
            self._wheel_accum_mouse = 0.0

        new_scale = step_thumb_scale(self._thumb_scale, zoom_in)
        if abs(new_scale - self._thumb_scale) > 0.01:
            self._thumb_scale = new_scale
            self._apply_thumb_scale()
            self._emit_thumb_scale_changed()
        event.accept()
        return True

    def get_thumb_scale(self) -> float:
        return self._thumb_scale

    def set_thumb_scale(self, scale: float, *, emit: bool = True):
        new_scale = THUMB_SCALE_PRESETS[_thumb_preset_index(scale)]
        if abs(new_scale - self._thumb_scale) < 0.01:
            return
        self._thumb_scale = new_scale
        self._wheel_accum_trackpad = 0
        self._wheel_accum_mouse = 0.0
        self._apply_thumb_scale()
        if emit:
            self._emit_thumb_scale_changed()

    def _emit_thumb_scale_changed(self):
        if hasattr(self, 'thumb_scale_changed'):
            self.thumb_scale_changed.emit(self._thumb_scale)

    def _apply_cell_thumb_sizes(self):
        w = int(BASE_THUMB_W * self._thumb_scale)
        h = int(BASE_THUMB_H * self._thumb_scale)
        SelectableImageCell.set_thumb_size(w, h)
        for cell in self._iter_thumb_cells():
            cell.apply_thumb_size()

    def eventFilter(self, obj, event):
        if obj in (self, self.viewport(), self.container):
            if self._process_preview_pinch_event(event):
                return True
        if obj is self.container and event.type() == QEvent.Type.Wheel:
            if _wheel_zoom_modifier(event.modifiers()):
                if self._handle_thumb_wheel(event):
                    return True
        if obj is self.container:
            if self._handle_marquee_event(event):
                return True
        return super().eventFilter(obj, event)

    def _event_pos(self, event) -> QPoint:
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def _handle_marquee_event(self, event) -> bool:
        et = event.type()
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            pos = self._event_pos(event)
            if self._point_blocks_marquee(pos):
                return False
            self._marquee_active = True
            self._marquee_origin = pos
            self._rubber_band.setGeometry(QRect(pos, QSize()))
            self._rubber_band.show()
            return True

        if et == QEvent.Type.MouseMove and self._marquee_active:
            pos = self._event_pos(event)
            self._rubber_band.setGeometry(QRect(self._marquee_origin, pos).normalized())
            return True

        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if not self._marquee_active:
                return False
            self._marquee_active = False
            self._rubber_band.hide()
            rect = self._rubber_band.geometry()
            if rect.width() < 4 and rect.height() < 4:
                if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self.selected.clear()
                self._refresh_selection()
                self.selection_changed.emit(self.get_selected())
                return True
            paths = set()
            for cell in self._iter_selectable_cells():
                if cell.image_info and cell.geometry().intersects(rect):
                    paths.add(cell.image_info.path)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.selected.update(paths)
            else:
                self.selected = paths
            self._refresh_selection()
            self.selection_changed.emit(self.get_selected())
            return True

        return False


class SelectableImageCell(QWidget):
    """Borderless selectable image cell."""

    clicked = pyqtSignal(object, object)
    right_clicked = pyqtSignal(object, object)
    double_clicked = pyqtSignal(object)

    THUMB_W, THUMB_H = BASE_THUMB_W, BASE_THUMB_H
    _theme: Dict[str, str] = get_colors()

    @classmethod
    def set_theme(cls, colors: Dict[str, str]):
        cls._theme = colors

    @classmethod
    def set_thumb_size(cls, width: int, height: int):
        cls.THUMB_W = max(48, width)
        cls.THUMB_H = max(36, height)

    @classmethod
    def reset_thumb_size(cls):
        cls.THUMB_W, cls.THUMB_H = BASE_THUMB_W, BASE_THUMB_H

    @staticmethod
    def _label_font() -> QFont:
        font = QFont()
        font.setPointSize(8)
        return font

    def _elided_label_text(self, max_width: int) -> str:
        if not self._label_text:
            return ""
        fm = QFontMetrics(self._label_font())
        return fm.elidedText(
            self._label_text, Qt.TextElideMode.ElideMiddle, max(0, max_width),
        )

    def _update_label_tooltip(self):
        if not self._label_text:
            self.setToolTip("")
            return
        elided = self._elided_label_text(self.width() - 4)
        self.setToolTip(self._label_text if elided != self._label_text else "")

    def _scaled_thumb(self) -> Optional[QPixmap]:
        if self._source_pixmap and not self._source_pixmap.isNull():
            return self._source_pixmap.scaled(
                self.THUMB_W, self.THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if self._pixmap and not self._pixmap.isNull():
            return self._pixmap
        return None

    def _thumb_draw_geometry(self) -> tuple[int, int, int, int]:
        """Thumbnail paint rect (x, y, w, h)."""
        w = self.width()
        y_top = 2
        scaled = self._scaled_thumb()
        if scaled is not None:
            px = (w - scaled.width()) // 2
            return px, y_top, scaled.width(), scaled.height()
        return 0, y_top, w, self.THUMB_H

    @classmethod
    def _label_area_height(cls, show_meta: bool) -> int:
        """Height of caption area below image."""
        h = 2 + 11  # spacing + filename
        if show_meta:
            h += 1 + 10  # spacing + dimensions/size line
        return h

    def _cell_height(self) -> int:
        """Cell total height from actual thumbnail paint height."""
        label_h = self._label_area_height(self.show_meta)
        _, py, _, ph = self._thumb_draw_geometry()
        if self.image_info is None and self._scaled_thumb() is None:
            return py + self.THUMB_H + label_h
        return py + ph + label_h

    def __init__(self, image_info: Optional[ImageInfo] = None, label_text: str = "", show_meta: bool = True):
        super().__init__()
        self.image_info = image_info
        self.selected = False
        self.show_meta = show_meta
        self._pixmap: Optional[QPixmap] = None
        self._source_pixmap: Optional[QPixmap] = None
        self._thumb_loading = False
        self._label_text = label_text or (image_info.name if image_info else "")
        self._meta_text = ""
        if image_info and show_meta:
            w, h = image_info.resolution
            self._meta_text = f"{w}×{h}  {format_file_size(image_info.file_size)}"

        self.setFixedSize(self.THUMB_W + 8, self._cell_height())
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if image_info:
            self._load_thumbnail()
        else:
            self._update_label_tooltip()

    def reload_thumbnail(self, force: bool = False):
        if self.image_info:
            if force or self._source_pixmap is None or self._source_pixmap.isNull():
                self._request_thumbnail()
            else:
                self.apply_thumb_size()

    def apply_thumb_size(self):
        self.setFixedSize(self.THUMB_W + 8, self._cell_height())
        self._update_label_tooltip()
        self.update()

    @staticmethod
    def _pil_to_source_pixmap(thumb: Image.Image) -> QPixmap:
        if thumb.mode != 'RGB':
            thumb = thumb.convert('RGB')
        arr = thumb.tobytes()
        qimg = QImage(
            arr, thumb.width, thumb.height, thumb.width * 3, QImage.Format.Format_RGB888,
        ).copy()
        return QPixmap.fromImage(qimg)

    def _apply_pil_thumbnail(self, thumb: Image.Image):
        try:
            thumb = thumb.copy()
        except Exception:
            self._thumb_loading = False
            self.update()
            return
        self._source_pixmap = self._pil_to_source_pixmap(thumb)
        self._pixmap = None
        self._thumb_loading = False
        self.apply_thumb_size()

    def _request_thumbnail(self):
        if not self.image_info or self._thumb_loading:
            return
        if self.image_info.thumbnail is not None:
            self._apply_pil_thumbnail(self.image_info.thumbnail)
            return
        cached = image_cache.get_thumbnail(self.image_info.path)
        if cached is not None:
            self._apply_pil_thumbnail(cached)
            return
        self._thumb_loading = True
        path = self.image_info.path
        ThumbnailService.instance().request(
            path,
            (THUMB_SOURCE_W, THUMB_SOURCE_H),
            self._on_async_thumbnail,
        )

    def _on_async_thumbnail(self, path: str, thumb: object):
        try:
            from shiboken6 import isValid
            if not isValid(self):
                return
        except Exception:
            pass
        if not self.image_info or self.image_info.path != path:
            return
        if thumb is None:
            self._thumb_loading = False
            self.update()
            return
        self._apply_pil_thumbnail(thumb)

    def _load_thumbnail(self):
        self._request_thumbnail()

    def set_selected(self, selected: bool):
        self.selected = selected
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        t = self._theme
        sel = QColor(t.get('selection', '#4caf50'))

        px, py, pw, ph = self._thumb_draw_geometry()
        content_h = py + ph + self._label_area_height(self.show_meta)

        if self.selected:
            painter.fillRect(0, 0, w, content_h, QColor(sel.red(), sel.green(), sel.blue(), 40))
            painter.setPen(sel)
            painter.drawRect(1, 1, w - 3, content_h - 2)
        scaled = self._scaled_thumb()
        if scaled is not None:
            painter.drawPixmap(px, py, scaled)
        elif self.image_info is None:
            painter.setPen(QColor(t.get('text_dim', '#555')))
            painter.drawText(0, 0, w, self.THUMB_H, Qt.AlignmentFlag.AlignCenter, "—")
        elif self._thumb_loading:
            painter.fillRect(px, py, pw if pw else w, ph if ph else self.THUMB_H, QColor(t.get('panel_bg', '#222')))
            painter.setPen(QColor(t.get('text_dim', '#555')))
            painter.drawText(
                px, py, pw if pw else w, ph if ph else self.THUMB_H,
                Qt.AlignmentFlag.AlignCenter, "…",
            )

        y_text = py + ph + 2
        if self._label_text:
            painter.setPen(QColor(t.get('text_muted', '#999')))
            painter.setFont(self._label_font())
            painter.drawText(
                2, y_text, w - 4, 12, Qt.AlignmentFlag.AlignCenter,
                self._elided_label_text(w - 4),
            )
            y_text += 12
        if self._meta_text and self.show_meta:
            painter.setPen(QColor(t.get('text_dim', '#555')))
            meta_font = QFont()
            meta_font.setPointSize(7)
            painter.setFont(meta_font)
            painter.drawText(2, y_text, w - 4, 10, Qt.AlignmentFlag.AlignCenter, self._meta_text)

    def mousePressEvent(self, event: QMouseEvent):
        if self.image_info and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.image_info, event)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.image_info and event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.image_info)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent):
        if self.image_info:
            self.right_clicked.emit(self.image_info, event.globalPos())
            event.accept()

    def wheelEvent(self, event: QWheelEvent):
        if _forward_thumb_wheel(self, event):
            return
        super().wheelEvent(event)

    def event(self, event):
        if _forward_pinch_zoom(self, event):
            return True
        return super().event(event)


class ColumnHeader(QWidget):
    """Multi-folder column header with remove button; draggable."""

    remove_clicked = pyqtSignal(str)
    right_clicked = pyqtSignal(str, object)
    reorder_drop = pyqtSignal(str, str)  # source_path, target_path

    _theme: Dict[str, str] = get_colors()

    @classmethod
    def set_theme(cls, colors: Dict[str, str]):
        cls._theme = colors

    def __init__(self, folder_name: str, folder_path: str, file_count: int):
        super().__init__()
        self.folder_path = folder_path
        self.folder_name = folder_name
        self._file_count = file_count
        self._drop_highlight = False
        self._drag_started = False
        self._press_pos = QPoint()
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.title = QLabel(folder_name)
        layout.addWidget(self.title)

        self.count = QLabel(tr('col_count', n=file_count))
        layout.addWidget(self.count)
        layout.addStretch()

        self.rm_btn = QPushButton()
        self.rm_btn.setFlat(True)
        self.rm_btn.setFixedSize(CLOSE_BTN_SIZE, CLOSE_BTN_SIZE)
        self.rm_btn.setIconSize(QSize(CLOSE_BTN_ICON, CLOSE_BTN_ICON))
        self.rm_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.rm_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rm_btn.setToolTip(tr('remove_column_tip'))
        self.rm_btn.clicked.connect(lambda: self.remove_clicked.emit(self.folder_path))
        layout.addWidget(self.rm_btn)

        self.setFixedWidth(SelectableImageCell.THUMB_W + 8)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._apply_style()

    def update_column_width(self):
        self.setFixedWidth(SelectableImageCell.THUMB_W + 8)

    def _apply_style(self):
        t = self._theme
        self.title.setStyleSheet(
            f"color: {t['foreground']}; font-size: 11px; font-weight: bold; background: transparent;"
        )
        self.count.setStyleSheet(
            f"color: {t['text_dim']}; font-size: 9px; background: transparent;"
        )
        icon_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
        self.rm_btn.setIcon(FIF.CLOSE.icon(icon_theme))
        self.rm_btn.setStyleSheet(close_button_style(t, 'QPushButton'))
        border = f"1px dashed {t['accent']}" if self._drop_highlight else f"1px solid {t['panel_border']}"
        bg = f"{t['accent']}33" if self._drop_highlight else t['panel_bg']
        self.setStyleSheet(
            f"background: {bg}; border-bottom: {border};"
        )

    def retranslate_ui(self):
        self.count.setText(tr('col_count', n=self._file_count))
        self.rm_btn.setToolTip(tr('remove_column_tip'))

    def refresh_theme(self):
        self._apply_style()

    def set_drop_highlight(self, highlighted: bool):
        if self._drop_highlight != highlighted:
            self._drop_highlight = highlighted
            self._apply_style()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and not self._drag_started
            and (event.position().toPoint() - self._press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._drag_started = True
            start_folder_drag(self, self.folder_path)
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        src = folder_path_from_mime(event.mimeData())
        if src and src != self.folder_path:
            event.acceptProposedAction()
            self.set_drop_highlight(True)

    def dragMoveEvent(self, event: QDragMoveEvent):
        src = folder_path_from_mime(event.mimeData())
        if src and src != self.folder_path:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self.set_drop_highlight(False)

    def dropEvent(self, event: QDropEvent):
        self.set_drop_highlight(False)
        src = folder_path_from_mime(event.mimeData())
        if src and src != self.folder_path:
            self.reorder_drop.emit(src, self.folder_path)
        event.acceptProposedAction()

    def contextMenuEvent(self, event: QContextMenuEvent):
        self.right_clicked.emit(self.folder_path, event.globalPos())
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        if _forward_thumb_wheel(self, event):
            return
        super().wheelEvent(event)

    def event(self, event):
        if _forward_pinch_zoom(self, event):
            return True
        return super().event(event)


class DropZoneWidget(QWidget):
    folders_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self._colors = get_colors()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon = QLabel("📂")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint1 = QLabel("拖动文件夹到此空白区域")
        self.hint1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint2 = QLabel("最多支持 12 个文件夹")
        self.hint2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.icon)
        layout.addWidget(self.hint1)
        layout.addWidget(self.hint2)
        layout.addStretch()
        self.apply_theme(self._colors)

    def retranslate_ui(self):
        self.hint1.setText(tr('drop_hint1'))
        self.hint2.setText(tr('drop_hint2', n=12))

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self.setStyleSheet(f"background: {colors['background']};")
        self.icon.setStyleSheet("font-size: 52px; background: transparent;")
        self.hint1.setStyleSheet(
            f"color: {colors['text_muted']}; font-size: 14px; background: transparent;"
        )
        self.hint2.setStyleSheet(
            f"color: {colors['text_dim']}; font-size: 11px; background: transparent;"
        )

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        folders = [url.toLocalFile() for url in event.mimeData().urls() if validate_folder_path(url.toLocalFile())]
        if folders:
            self.folders_dropped.emit(folders)
        event.acceptProposedAction()


class SingleFolderView(PreviewGridInteractionMixin, QScrollArea):
    selection_changed = pyqtSignal(list)
    thumb_scale_changed = pyqtSignal(float)
    image_context_menu = pyqtSignal(object, object)
    view_context_menu = pyqtSignal(object)
    image_double_clicked = pyqtSignal(object)

    MIN_COLS = 1
    MAX_COLS = 14

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self._colors = get_colors()
        self._thumb_scale = DEFAULT_THUMB_SCALE
        self.container = QWidget()
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(8, 6, 8, 6)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWidget(self.container)
        self.cells: List[SelectableImageCell] = []
        self.selected: Set[str] = set()
        self._last_clicked_path: Optional[str] = None
        self._images: List[ImageInfo] = []
        self._folder_name = ""
        self.container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.container.customContextMenuRequested.connect(
            lambda pos: self.view_context_menu.emit(self.container.mapToGlobal(pos))
        )
        self._init_preview_interaction()
        self.apply_theme(self._colors)

    def _iter_selectable_cells(self) -> List[SelectableImageCell]:
        return self.cells

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        SelectableImageCell.set_theme(colors)
        self.setStyleSheet(f"QScrollArea {{ background: {colors['background']}; border: none; }}")
        self.container.setStyleSheet(f"background: {colors['background']};")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.cells:
            self._reflow_grid()
        elif self._images:
            self._layout_images()

    def set_images(self, images: List[ImageInfo], folder_name: str = ""):
        self._images = images
        self._folder_name = folder_name
        self._layout_images()

    def wheelEvent(self, event: QWheelEvent):
        if _wheel_zoom_modifier(event.modifiers()):
            if self._handle_thumb_wheel(event):
                return
        super().wheelEvent(event)

    def event(self, event):
        if self._process_preview_pinch_event(event):
            return True
        return super().event(event)

    def reset_thumb_scale(self):
        self.set_thumb_scale(DEFAULT_THUMB_SCALE)

    def _apply_thumb_scale(self):
        self._apply_cell_thumb_sizes()
        if self.cells:
            self._reflow_grid()
        elif self._images:
            self._layout_images()

    def _reflow_grid(self):
        for cell in self.cells:
            self.grid.removeWidget(cell)
        cols = self._calc_cols()
        for i, cell in enumerate(self.cells):
            self.grid.addWidget(cell, i // cols, i % cols)
        self.container.adjustSize()

    def _calc_cols(self) -> int:
        vw = max(200, self.viewport().width() - 16)
        cell_w = SelectableImageCell.THUMB_W + 8 + self.grid.spacing()
        cols = max(self.MIN_COLS, vw // cell_w)
        return min(self.MAX_COLS, max(1, cols))

    def _layout_images(self):
        self._clear()
        images = self._images
        if not images:
            self.selected.clear()
            self.selection_changed.emit([])
            return

        w = int(BASE_THUMB_W * self._thumb_scale)
        h = int(BASE_THUMB_H * self._thumb_scale)
        SelectableImageCell.set_thumb_size(w, h)

        cols = self._calc_cols()
        for i, img in enumerate(images):
            cell = SelectableImageCell(img, img.name, show_meta=True)
            cell.clicked.connect(self._on_cell_clicked)
            cell.right_clicked.connect(self.image_context_menu.emit)
            cell.double_clicked.connect(self.image_double_clicked.emit)
            self.cells.append(cell)
            self.grid.addWidget(cell, i // cols, i % cols)

        self.container.adjustSize()
        self._refresh_selection()
        self.selection_changed.emit(self.get_selected())

    def _clear(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cells.clear()

    def _on_cell_clicked(self, image_info: ImageInfo, event: QMouseEvent):
        path = image_info.path
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.selected.symmetric_difference_update({path})
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self._last_clicked_path:
            paths = [c.image_info.path for c in self.cells if c.image_info]
            try:
                start, end = sorted([paths.index(self._last_clicked_path), paths.index(path)])
                self.selected.update(paths[start:end + 1])
            except ValueError:
                self.selected.add(path)
        else:
            self.selected = {path}
        self._last_clicked_path = path
        self._refresh_selection()
        self.selection_changed.emit(self.get_selected())

    def _refresh_selection(self):
        for cell in self.cells:
            if cell.image_info:
                cell.set_selected(cell.image_info.path in self.selected)

    def get_selected(self) -> List[ImageInfo]:
        return [c.image_info for c in self.cells if c.image_info and c.image_info.path in self.selected]

    def select_all(self):
        self.selected = {c.image_info.path for c in self.cells if c.image_info}
        self._refresh_selection()
        self.selection_changed.emit(self.get_selected())

    def clear_selection(self):
        self.selected.clear()
        self._refresh_selection()
        self.selection_changed.emit([])


class MultiFolderGridView(PreviewGridInteractionMixin, QScrollArea):
    selection_changed = pyqtSignal(list)
    thumb_scale_changed = pyqtSignal(float)
    folder_remove_requested = pyqtSignal(str)
    folder_reorder_requested = pyqtSignal(int, int)
    image_context_menu = pyqtSignal(object, object)
    folder_context_menu = pyqtSignal(str, object)
    view_context_menu = pyqtSignal(object)
    image_double_clicked = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self._colors = get_colors()
        self._thumb_scale = DEFAULT_THUMB_SCALE
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(8, 6, 8, 8)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.container)
        self.cells: List[List[SelectableImageCell]] = []
        self._headers: List[ColumnHeader] = []
        self._row_nums: List[QLabel] = []
        self._row_lines: List[QWidget] = []
        self._folder_paths: List[str] = []
        self.selected: Set[str] = set()
        self._last_clicked_path: Optional[str] = None
        self.container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.container.customContextMenuRequested.connect(
            lambda pos: self.view_context_menu.emit(self.container.mapToGlobal(pos))
        )
        self._init_preview_interaction()
        self.apply_theme(self._colors)

    def _iter_selectable_cells(self) -> List[SelectableImageCell]:
        return [cell for row in self.cells for cell in row if cell.image_info]

    def _iter_thumb_cells(self) -> List[SelectableImageCell]:
        return [cell for row in self.cells for cell in row]

    def wheelEvent(self, event: QWheelEvent):
        if _wheel_zoom_modifier(event.modifiers()):
            if self._handle_thumb_wheel(event):
                return
        super().wheelEvent(event)

    def event(self, event):
        if self._process_preview_pinch_event(event):
            return True
        return super().event(event)

    def reset_thumb_scale(self):
        self.set_thumb_scale(DEFAULT_THUMB_SCALE)

    def _sync_row_heights(self):
        """Equal row height for image and placeholder cells after zoom."""
        for row in self.cells:
            if not row:
                continue
            max_h = max(cell._cell_height() for cell in row)
            for cell in row:
                w = cell.width()
                if cell.height() != max_h:
                    cell.setFixedSize(w, max_h)

    def _apply_thumb_scale(self):
        self._apply_cell_thumb_sizes()
        self._sync_row_heights()
        for hdr in self._headers:
            hdr.update_column_width()
        self.container.adjustSize()

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        SelectableImageCell.set_theme(colors)
        ColumnHeader.set_theme(colors)
        self.setStyleSheet(f"QScrollArea {{ background: {colors['background']}; border: none; }}")
        self.container.setStyleSheet(f"background: {colors['background']};")
        for hdr in self._headers:
            hdr.refresh_theme()
        for lbl in self._row_nums:
            lbl.setStyleSheet(
                f"color: {colors['text_dim']}; font-size: 10px; background: transparent;"
            )
        for line in self._row_lines:
            line.setStyleSheet(f"background: {colors['panel_border']};")
        self.viewport().update()

    def retranslate_ui(self):
        for hdr in self._headers:
            hdr.retranslate_ui()

    def set_grid(
        self,
        folder_names: List[str],
        folder_paths: List[str],
        file_counts: List[int],
        grid: List[List[Optional[ImageInfo]]],
    ):
        self._clear()
        if not grid:
            return

        self._folder_paths = list(folder_paths)
        w = int(BASE_THUMB_W * self._thumb_scale)
        h = int(BASE_THUMB_H * self._thumb_scale)
        SelectableImageCell.set_thumb_size(w, h)

        header = QHBoxLayout()
        header.setSpacing(0)
        row_num = QLabel("")
        row_num.setFixedWidth(28)
        header.addWidget(row_num)
        self._headers = []
        self._row_nums = []
        self._row_lines = []
        for name, path, count in zip(folder_names, folder_paths, file_counts):
            hdr = ColumnHeader(name, path, count)
            hdr.remove_clicked.connect(self.folder_remove_requested.emit)
            hdr.right_clicked.connect(self.folder_context_menu.emit)
            hdr.reorder_drop.connect(self._on_header_reorder_drop)
            header.addWidget(hdr)
            self._headers.append(hdr)
        header.addStretch()
        self.layout.addLayout(header)

        for row_idx, row in enumerate(grid):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(0)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            num = QLabel(str(row_idx + 1))
            num.setFixedWidth(28)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(
                f"color: {self._colors['text_dim']}; font-size: 10px; background: transparent;"
            )
            row_layout.addWidget(num)
            self._row_nums.append(num)

            row_cells = []
            for img in row:
                cell = SelectableImageCell(img, img.name if img else "", show_meta=True)
                cell.clicked.connect(self._on_cell_clicked)
                cell.right_clicked.connect(self.image_context_menu.emit)
                cell.double_clicked.connect(self.image_double_clicked.emit)
                row_cells.append(cell)
                row_layout.addWidget(cell)

            row_layout.addStretch()
            self.layout.addLayout(row_layout)
            self.cells.append(row_cells)

            if row_idx < len(grid) - 1:
                line = QWidget()
                line.setFixedHeight(1)
                line.setStyleSheet(f"background: {self._colors['panel_border']};")
                self.layout.addWidget(line)
                self._row_lines.append(line)

        self.layout.addStretch()
        self.selected.clear()
        self.selection_changed.emit([])

    def _on_header_reorder_drop(self, source_path: str, target_path: str):
        try:
            from_idx = self._folder_paths.index(source_path)
            to_idx = self._folder_paths.index(target_path)
        except ValueError:
            return
        if from_idx != to_idx:
            self.folder_reorder_requested.emit(from_idx, to_idx)

    def _clear(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.layout():
                self._clear_layout(item.layout())
            elif item.widget():
                item.widget().deleteLater()
        self.cells.clear()
        self._headers.clear()
        self._row_nums.clear()
        self._row_lines.clear()
        self._folder_paths.clear()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.layout():
                self._clear_layout(item.layout())
            elif item.widget():
                item.widget().deleteLater()

    def _on_cell_clicked(self, image_info: ImageInfo, event: QMouseEvent):
        path = image_info.path
        modifiers = event.modifiers()
        all_paths = [c.image_info.path for row in self.cells for c in row if c.image_info]

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.selected.symmetric_difference_update({path})
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self._last_clicked_path:
            try:
                start, end = sorted([all_paths.index(self._last_clicked_path), all_paths.index(path)])
                self.selected.update(all_paths[start:end + 1])
            except ValueError:
                self.selected.add(path)
        else:
            self.selected = {path}

        self._last_clicked_path = path
        self._refresh_selection()
        self.selection_changed.emit(self.get_selected())

    def _refresh_selection(self):
        for row in self.cells:
            for cell in row:
                if cell.image_info:
                    cell.set_selected(cell.image_info.path in self.selected)

    def get_selected(self) -> List[ImageInfo]:
        result, seen = [], set()
        for row in self.cells:
            for cell in row:
                if cell.image_info and cell.image_info.path in self.selected:
                    if cell.image_info.path not in seen:
                        result.append(cell.image_info)
                        seen.add(cell.image_info.path)
        return result

    def select_all(self):
        self.selected = {
            c.image_info.path for row in self.cells for c in row if c.image_info
        }
        self._refresh_selection()
        self.selection_changed.emit(self.get_selected())

    def clear_selection(self):
        self.selected.clear()
        self._refresh_selection()
        self.selection_changed.emit([])

    def select_row(self, row_index: int):
        if row_index < 0 or row_index >= len(self.cells):
            return
        self.selected = {
            c.image_info.path for c in self.cells[row_index] if c.image_info
        }
        self._refresh_selection()
        self.selection_changed.emit(self.get_selected())
        if self.cells[row_index]:
            first = next(c for c in self.cells[row_index] if c.image_info)
            self.ensureWidgetVisible(first, 0, 80)
