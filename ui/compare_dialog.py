"""
Compare window - side-by-side slots / Tab preview / crop / pixel compare.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QFrame,
    QFileDialog, QMessageBox, QMenu,
    QLineEdit, QTextEdit, QPlainTextEdit, QScrollArea, QAbstractSpinBox,
    QSpinBox, QSizePolicy,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, Slider, ComboBox, CaptionLabel,
    InfoBar, InfoBarPosition,
)
from PyQt6.QtGui import (
    QPainter, QKeyEvent, QWheelEvent, QMouseEvent, QPen, QImage, QColor, QCursor,
    QPainterPath, QBrush, QFont, QShortcut, QKeySequence, QIcon,
)
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QRectF, QEvent, QTimer
from typing import List, Optional, Dict, Tuple
import logging
import math
import re
from pathlib import Path
import cv2
import numpy as np

from ui.fluent_integration import (
    style_compact_button, style_compact_input, style_dialog_checkbox, sync_fluent_slider,
    fit_checkbox_width, fit_compact_button_width, fit_dialog_toolbar_button,
    dialog_combo_stylesheet,
    style_dialog_combo, apply_dialog_checkbox_theme, DialogCheckBox,
    style_compact_dialog_slider, fit_dialog_combo_width,
    enable_slider_keyboard_tune,
    DIALOG_TOOLBAR_HEIGHT, DIALOG_TOOLBAR_FONT,
)
from config import (
    COMPARE_WINDOW_WIDTH, COMPARE_WINDOW_HEIGHT, APP_ICON_PATH,
    MIN_ZOOM, MAX_ZOOM, ZOOM_WHEEL_FACTOR, ZOOM_WHEEL_DEGREES,
    ZOOM_SLIDER_STEPS, ZOOM_SLIDER_UI_MAX,
    PIXEL_INSPECTOR_MIN_SCALE, PIXEL_INSPECTOR_SCALE_PRESETS, PIXEL_RGB_DETAIL_SCALE,
    MAX_PIXEL_RGB_LABELS, MAX_SCALE,
)
from core.image_loader import ImageInfo, ImageLoader
from core.folder_manager import FolderManager
from core.tools import ComparisonTools, Rect, CropRegion
from ui.pixel_detail_panel import PixelDetailPanel
from ui.diff_map_panel import DiffMapPanel
from ui.styles import get_stylesheet
from ui.theme import get_colors, is_dark_theme
from ui.gesture_zoom import enable_pinch_gestures, try_handle_pinch_event, wheel_event_pixel_delta, zoom_factor_from_pixels
from utils.image_utils import compute_diff_map
from utils.color_view import ColorViewParams, apply_color_view
from ui.color_view_panel import ColorViewPanel
from ui.custom_tool_panel import CustomToolPanel
from ui.custom_tools_editor_dialog import CustomToolsEditorDialog
from ui.metrics_panel import MetricsPanel
from ui.metrics_worker import MetricsComputeWorker, MetricsExportWorker
from extensions.custom_tool_runtime import run_custom_tool
from extensions.custom_tool_store import load_custom_tools
from utils.image_metrics import format_metric_value
from utils.platform_utils import schedule_macos_native_fullscreen_button, exit_window_fullscreen
from i18n import tr

logger = logging.getLogger(__name__)

CROP_SHAPE_OPTIONS = (
    ('rect', 'crop_rect'),
    ('square', 'crop_square'),
    ('circle', 'crop_circle'),
)


def _compare_menu_style(colors: Dict[str, str]) -> str:
    return (
        f"QMenu {{ background: {colors['panel_bg']}; color: {colors['foreground']}; "
        f"border: 1px solid {colors['panel_border']}; padding: 4px; }}"
        f"QMenu::item {{ padding: 6px 24px; }}"
        f"QMenu::item:selected {{ background: {colors['accent']}; }}"
    )


def _crop_shape_from_index(index: int) -> str:
    if 0 <= index < len(CROP_SHAPE_OPTIONS):
        return CROP_SHAPE_OPTIONS[index][0]
    return 'rect'


def _compare_vsep() -> QFrame:
    sep = QFrame()
    sep.setObjectName("compareToolbarSep")
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFixedSize(1, 18)
    return sep


def _compare_group() -> Tuple[QWidget, QHBoxLayout]:
    box = QWidget()
    box.setObjectName("compareToolGroup")
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    return box, lay


def _style_dialog_control(widget, *, width: Optional[int] = None):
    style_compact_input(widget, height=DIALOG_TOOLBAR_HEIGHT, font_size=DIALOG_TOOLBAR_FONT)
    if width is not None:
        widget.setFixedWidth(width)


def _style_dialog_button(btn, *, width: Optional[int] = None):
    fit_dialog_toolbar_button(btn, min_width=width or 0)


def _fit_zoom_group(dialog: "CompareDialog"):
    if not hasattr(dialog, '_zoom_group'):
        return
    if hasattr(dialog, '_reset_view_btn'):
        _style_dialog_button(dialog._reset_view_btn)
    dialog._zoom_group.setMinimumWidth(0)
    dialog._zoom_group.setMaximumWidth(16777215)
    dialog._zoom_group.adjustSize()
    dialog._zoom_group.setFixedWidth(dialog._zoom_group.sizeHint().width())


def _style_dialog_spinbox(spin: QSpinBox, *, width: int = 48):
    _style_dialog_control(spin, width=width)
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
    spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def array_to_qimage(arr: np.ndarray) -> QImage:
    if arr is None:
        return QImage()
    if not arr.flags['C_CONTIGUOUS']:
        arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        return QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
    if arr.shape[2] == 4:
        return QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    rgb = np.ascontiguousarray(arr[:, :, :3])
    return QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()


def cell_rectf(cell: Tuple[float, float, float, float]) -> QRectF:
    x, y, w, h = cell
    return QRectF(x, y, w, h)


def zoom_slider_hi(max_zoom_limit: float) -> float:
    return max(MIN_ZOOM * 2, min(max_zoom_limit, ZOOM_SLIDER_UI_MAX))


def zoom_to_slider_pos(zoom: float, max_zoom_limit: float) -> int:
    lo, hi = MIN_ZOOM, zoom_slider_hi(max_zoom_limit)
    z = max(lo, min(hi, zoom))
    if hi <= lo:
        return 0
    t = (math.log(z) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return int(round(t * ZOOM_SLIDER_STEPS))


def slider_pos_to_zoom(pos: int, max_zoom_limit: float) -> float:
    lo, hi = MIN_ZOOM, zoom_slider_hi(max_zoom_limit)
    if ZOOM_SLIDER_STEPS <= 0 or hi <= lo:
        return lo
    t = max(0.0, min(1.0, pos / ZOOM_SLIDER_STEPS))
    return lo * ((hi / lo) ** t)


def crop_widget_rect_from_points(p1: QPoint, p2: QPoint, shape: str) -> QRect:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    if shape == 'rect':
        return QRect(
            min(p1.x(), p2.x()), min(p1.y(), p2.y()),
            abs(dx), abs(dy),
        )
    side = max(abs(dx), abs(dy))
    if side <= 0:
        return QRect(p1.x(), p1.y(), 0, 0)
    left = p1.x() if dx >= 0 else p1.x() - side
    top = p1.y() if dy >= 0 else p1.y() - side
    return QRect(left, top, side, side)


class ImageSlot:
    def __init__(self, image_info: ImageInfo):
        self.info = image_info
        self.source_array: Optional[np.ndarray] = None
        self.array: Optional[np.ndarray] = None
        self.qimage: Optional[QImage] = None


class CompareCanvas(QWidget):
    """Compare canvas."""

    status_changed = pyqtSignal(str)
    rgb_copied = pyqtSignal(int, int, int)
    zoom_changed = pyqtSignal(float)
    pixel_samples_changed = pyqtSignal(list)
    slots_content_changed = pyqtSignal()
    active_slot_changed = pyqtSignal(int)

    def __init__(
        self,
        images: List[ImageInfo],
        image_loader: ImageLoader,
        slot_pools: Optional[List[List[ImageInfo]]] = None,
        groups: Optional[List[List[ImageInfo]]] = None,
        folder_name_map: Optional[Dict[str, str]] = None,
    ):
        super().__init__()
        self.image_loader = image_loader
        self._folder_name_map: Dict[str, str] = folder_name_map or {}
        self.slots: List[ImageSlot] = [ImageSlot(img) for img in images]
        self.slot_pools: List[List[ImageInfo]] = slot_pools or [[img] for img in images]
        if len(self.slot_pools) < len(self.slots):
            for i in range(len(self.slot_pools), len(self.slots)):
                self.slot_pools.append([self.slots[i].info])

        self.slot_indices: List[int] = []
        for i, slot in enumerate(self.slots):
            pool = self.slot_pools[i]
            idx = next((j for j, p in enumerate(pool) if p.path == slot.info.path), 0)
            self.slot_indices.append(idx)

        self.groups = groups or [images]
        self.group_index = 0
        for gi, g in enumerate(self.groups):
            if len(g) == len(images) and all(
                a.path == b.path for a, b in zip(g, images)
            ):
                self.group_index = gi
                break

        self.global_zoom = 1.0
        self.global_pan_x = 0.0
        self.global_pan_y = 0.0

        self.crop_rect_image: Optional[QRect] = None
        self.crop_shape = 'rect'
        self.drawing_crop = False
        self.crop_start_widget: Optional[QPoint] = None
        self.crop_draft_widget: Optional[QRect] = None

        self.panning = False
        self.pan_start: Optional[QPoint] = None
        self.pan_start_offset = (0.0, 0.0)
        self._active_slot_index = 0
        self._custom_tool_modified: set = set()
        self._hover_slot_index = 0

        self._tab_preview_slot: Optional[int] = None
        self._tab_preview_backup: Optional[ImageInfo] = None

        self._slot_layouts: List[Dict] = []

        self._layout_cols: Optional[int] = None
        self._layout_rows: Optional[int] = None

        self.show_histogram = False
        self.show_slot_overlay = True
        self.show_metrics_overlay = False
        self.metrics_baseline_idx = 0
        self.slot_metrics: Dict[int, Dict[str, Optional[float]]] = {}
        self.metrics_enabled_keys: List[str] = []
        self.metrics_baseline_label = 'Baseline'
        self.eyedropper_enabled = False
        self.pixel_inspector_enabled = False
        self.pixel_inspector_min_scale = PIXEL_INSPECTOR_MIN_SCALE
        self._sample_x: Optional[int] = None
        self._sample_y: Optional[int] = None
        self._eyedropper_click_pending = False
        self._eyedropper_press_pos: Optional[QPoint] = None
        self._copy_format = 'rgb'
        self._copy_enabled = False
        self._slot_histograms: List[Optional[Dict[str, np.ndarray]]] = []
        self._colors = get_colors()
        self._cell_hover = QColor(255, 255, 255, 8)
        self.color_view_params = ColorViewParams()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 400)
        enable_pinch_gestures(self)

        self._load_all_slots()

    def apply_theme(self, colors: Optional[Dict[str, str]] = None):
        if colors is None:
            colors = get_colors()
        self._colors = colors
        dark = colors.get('canvas_bg', '').lower() in ('#1a1a1a', '#1a1a1aff')
        self._cell_hover = QColor(255, 255, 255, 8) if dark else QColor(0, 0, 0, 18)
        self.update()

    def _c(self, key: str) -> QColor:
        return QColor(self._colors[key])

    def _load_slot(self, slot: ImageSlot, img_info: ImageInfo, slot_index: Optional[int] = None):
        pil = self.image_loader.load_full_image(img_info.path)
        if pil is None:
            return
        if pil.mode == 'RGBA':
            arr = np.array(pil)
        elif pil.mode == 'RGB':
            arr = np.array(pil)
        else:
            arr = np.array(pil.convert('RGB'))
        slot.info = img_info
        slot.source_array = arr
        if slot_index is None:
            slot_index = self.slots.index(slot)
        self._apply_slot_color_view(slot, slot_index)

    def _apply_slot_color_view(self, slot: ImageSlot, slot_index: int):
        if slot.source_array is None:
            return
        view_rgb = apply_color_view(slot.source_array, self.color_view_params)
        slot.array = view_rgb
        slot.qimage = array_to_qimage(view_rgb)
        self._custom_tool_modified.discard(slot_index)
        if self.show_histogram:
            rgb = view_rgb[:, :, :3] if view_rgb.shape[2] >= 3 else view_rgb
            self._rebuild_slot_histogram(slot_index, rgb)

    def set_color_view_params(self, params: ColorViewParams):
        if params == self.color_view_params:
            return
        self.color_view_params = params
        self._refresh_all_color_views()

    def _refresh_all_color_views(self):
        for i, slot in enumerate(self.slots):
            if slot.source_array is not None:
                self._apply_slot_color_view(slot, i)
        if self.eyedropper_enabled and self._sample_x is not None:
            self.pixel_samples_changed.emit(self.collect_pixel_samples())
        self.update()

    def _set_active_slot_index(self, idx: int):
        idx = max(0, min(idx, max(0, len(self.slots) - 1)))
        if idx != self._active_slot_index:
            self._active_slot_index = idx
            self.active_slot_changed.emit(idx)

    def apply_custom_tool_view(self, slot_index: int, rgb: np.ndarray):
        """Write custom tool output to the given slot display."""
        if slot_index < 0 or slot_index >= len(self.slots):
            return
        slot = self.slots[slot_index]
        view_rgb = np.ascontiguousarray(rgb[:, :, :3] if rgb.ndim == 3 else rgb)
        slot.array = view_rgb
        slot.qimage = array_to_qimage(view_rgb)
        self._custom_tool_modified.add(slot_index)
        if self.show_histogram:
            self._rebuild_slot_histogram(slot_index, view_rgb)
        if self.eyedropper_enabled and self._sample_x is not None:
            self.pixel_samples_changed.emit(self.collect_pixel_samples())
        self.update()

    def revert_custom_tool_views(self, slot_index: Optional[int] = None):
        """Revert custom tool display changes; restore color view."""
        if slot_index is not None:
            indices = [slot_index] if slot_index in self._custom_tool_modified else []
        else:
            indices = sorted(self._custom_tool_modified)
        if not indices:
            return False
        for i in indices:
            if i < len(self.slots) and self.slots[i].source_array is not None:
                self._apply_slot_color_view(self.slots[i], i)
                self._custom_tool_modified.discard(i)
        if self.eyedropper_enabled and self._sample_x is not None:
            self.pixel_samples_changed.emit(self.collect_pixel_samples())
        self.update()
        return True

    def _load_all_slots(self):
        self._slot_histograms = []
        for i, slot in enumerate(self.slots):
            self._load_slot(slot, slot.info, i)
        self.slots_content_changed.emit()
        self.update()

    def reload_images_by_path(self, paths: set, info_by_path: Dict[str, ImageInfo]):
        """Refresh affected slots after file changes (e.g. rotation)."""
        paths = set(paths)
        if not paths:
            return

        if self._tab_preview_slot is not None:
            self.exit_tab_preview()

        changed = False
        for i, slot in enumerate(self.slots):
            if slot.info.path in paths:
                info = info_by_path.get(slot.info.path, slot.info)
                self.image_loader.invalidate_image(slot.info.path)
                self._load_slot(slot, info, i)
                changed = True

        for gi, group in enumerate(self.groups):
            self.groups[gi] = [
                info_by_path.get(img.path, img) if img.path in paths else img
                for img in group
            ]

        for pi, pool in enumerate(self.slot_pools):
            self.slot_pools[pi] = [
                info_by_path.get(img.path, img) if img.path in paths else img
                for img in pool
            ]

        if changed:
            self._slot_layouts = []
            self.crop_rect_image = None
            self.reset_view()
            self.slots_content_changed.emit()
            self.update()

    def remove_slot_at(
        self,
        index: int,
        groups: List[List[ImageInfo]],
        slot_pools: List[List[ImageInfo]],
        group_index: int,
    ) -> bool:
        """Remove a column in place; keep zoom, pan, and toolbar state."""
        if index < 0 or index >= len(self.slots) or len(self.slots) <= 1:
            return False

        if self._tab_preview_slot is not None:
            self.exit_tab_preview()

        del self.slots[index]
        if index < len(self.slot_pools):
            del self.slot_pools[index]
        if index < len(self.slot_indices):
            del self.slot_indices[index]
        if index < len(self._slot_histograms):
            del self._slot_histograms[index]

        self.slot_pools = slot_pools
        self.groups = groups
        self.group_index = max(0, min(group_index, len(groups) - 1))

        group = self.groups[self.group_index]
        self.slot_indices = []
        for i, slot in enumerate(self.slots):
            pool = self.slot_pools[i] if i < len(self.slot_pools) else [slot.info]
            si = next((j for j, p in enumerate(pool) if p.path == slot.info.path), 0)
            self.slot_indices.append(si)
            if i < len(group) and slot.info.path != group[i].path:
                self._load_slot(slot, group[i], i)

        if self._hover_slot_index >= len(self.slots):
            self._hover_slot_index = max(0, len(self.slots) - 1)
        if self._active_slot_index >= len(self.slots):
            self._active_slot_index = max(0, len(self.slots) - 1)

        self._slot_layouts = []
        self._clamp_pan()
        self.slots_content_changed.emit()
        self.update()
        return True

    @staticmethod
    def _channel_hist(channel: np.ndarray) -> np.ndarray:
        return np.bincount(channel.ravel(), minlength=256)

    def _rebuild_slot_histogram(self, index: int, arr: np.ndarray):
        while len(self._slot_histograms) <= index:
            self._slot_histograms.append(None)
        rgb = arr[:, :, :3] if arr.shape[2] >= 3 else arr
        luma = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(np.uint8)
        self._slot_histograms[index] = {
            'Red': self._channel_hist(rgb[:, :, 0]),
            'Green': self._channel_hist(rgb[:, :, 1]),
            'Blue': self._channel_hist(rgb[:, :, 2]),
            'Luma': self._channel_hist(luma),
        }

    def set_eyedropper(self, enabled: bool):
        self.eyedropper_enabled = enabled
        self.setMouseTracking(True)
        self.setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        if not enabled:
            self._sample_x = None
            self._sample_y = None
        self.update()

    def set_pixel_inspector(self, enabled: bool):
        self.pixel_inspector_enabled = enabled
        self.update()

    def set_pixel_inspector_min_scale(self, scale: float):
        self.pixel_inspector_min_scale = max(1.0, scale)
        self.update()

    def _should_show_pixel_inspector(self, scale: float) -> bool:
        return self.pixel_inspector_enabled and scale >= self.pixel_inspector_min_scale

    def set_show_histogram(self, show: bool):
        was = self.show_histogram
        self.show_histogram = show
        if show and not was:
            for i, slot in enumerate(self.slots):
                if slot.array is not None:
                    rgb = slot.array[:, :, :3] if slot.array.shape[2] >= 3 else slot.array
                    self._rebuild_slot_histogram(i, rgb)
        self.update()

    def set_show_slot_overlay(self, show: bool):
        self.show_slot_overlay = show
        self.update()

    def set_metrics_overlay(
        self,
        enabled: bool,
        baseline_idx: int,
        slot_metrics: Dict[int, Dict[str, Optional[float]]],
        enabled_keys: List[str],
        baseline_label: str = 'Baseline',
    ):
        self.show_metrics_overlay = enabled
        self.metrics_baseline_idx = baseline_idx
        self.slot_metrics = slot_metrics or {}
        self.metrics_enabled_keys = list(enabled_keys or [])
        self.metrics_baseline_label = baseline_label
        self.update()

    def _widget_to_image_coords(self, layout: Dict, pos: QPoint) -> Optional[Tuple[int, int]]:
        draw = layout.get('draw')
        if not draw:
            return None
        dx, dy, dw, dh, scale, iw, ih = draw
        if scale <= 0:
            return None
        x = int((pos.x() - dx) / scale)
        y = int((pos.y() - dy) / scale)
        if 0 <= x < iw and 0 <= y < ih:
            return x, y
        return None

    def _image_to_widget(self, layout: Dict, ix: int, iy: int) -> Optional[QPoint]:
        draw = layout.get('draw')
        if not draw:
            return None
        dx, dy, _, _, scale, iw, ih = draw
        if not (0 <= ix < iw and 0 <= iy < ih):
            return None
        return QPoint(int(dx + ix * scale), int(dy + iy * scale))

    @staticmethod
    def _extract_patch(arr: np.ndarray, x: int, y: int, radius: int = 4) -> np.ndarray:
        ih, iw = arr.shape[:2]
        size = radius * 2 + 1
        patch = np.zeros((size, size, 3), dtype=np.uint8)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                sx, sy = x + dx, y + dy
                if 0 <= sx < iw and 0 <= sy < ih:
                    patch[radius + dy, radius + dx] = arr[sy, sx, :3]
        return patch

    def collect_pixel_samples(self) -> List[Dict]:
        if self._sample_x is None or self._sample_y is None:
            return []
        x, y = self._sample_x, self._sample_y
        samples = []
        for slot in self.slots:
            name = slot.info.name if slot.info else ""
            folder_name = ""
            if slot.info and slot.info.path:
                folder_name = self._folder_name_map.get(slot.info.path, "")
                if not folder_name:
                    from pathlib import Path
                    folder_name = Path(slot.info.path).parent.name
            base = {'name': name, 'folder': folder_name, 'x': x, 'y': y}
            if slot.array is None:
                samples.append({**base, 'valid': False, 'rgb': (0, 0, 0), 'patch': None})
                continue
            ih, iw = slot.array.shape[:2]
            if not (0 <= x < iw and 0 <= y < ih):
                samples.append({**base, 'valid': False, 'rgb': (0, 0, 0), 'patch': None})
                continue
            r, g, b = int(slot.array[y, x, 0]), int(slot.array[y, x, 1]), int(slot.array[y, x, 2])
            patch = self._extract_patch(slot.array, x, y)
            samples.append({**base, 'valid': True, 'rgb': (r, g, b), 'patch': patch})
        return samples

    def _update_eyedropper_sample(self, pos: QPoint):
        if not self.eyedropper_enabled or not self._slot_layouts:
            return None
        idx = self._slot_at_pos(pos)
        layout = self._slot_layouts[idx]
        coords = self._widget_to_image_coords(layout, pos)
        if coords:
            self._sample_x, self._sample_y = coords
            return self.collect_pixel_samples()
        return None

    def _draw_histogram_overlay(
        self, painter: QPainter, cell: Tuple[float, float, float, float], idx: int,
    ):
        if not self.show_histogram or idx >= len(self._slot_histograms):
            return
        hist = self._slot_histograms[idx]
        if not hist:
            return

        cx, cy, cw, ch = cell
        ow = min(cw - 16, 200)
        oh = 80
        ox = cx + cw - ow - 8
        oy = cy + 8
        pad = 6
        plot_x = ox + pad
        plot_y = oy + pad + 10
        plot_w = ow - pad * 2
        plot_h = oh - pad * 2 - 14

        dark = is_dark_theme()
        if dark:
            grid_pen = QColor(255, 255, 255, 50)
            title_pen = QColor(255, 255, 255, 220)
            title_shadow = QColor(0, 0, 0, 140)
        else:
            grid_pen = QColor(0, 0, 0, 40)
            title_pen = QColor(0, 0, 0, 210)
            title_shadow = QColor(255, 255, 255, 200)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        tx, ty = int(ox + pad), int(oy + pad + 9)
        painter.setPen(title_shadow)
        painter.drawText(tx + 1, ty + 1, tr('histogram'))
        painter.setPen(title_pen)
        painter.drawText(tx, ty, tr('histogram'))

        for i in range(1, 4):
            gy = int(plot_y + plot_h * i / 4)
            painter.setPen(QPen(grid_pen, 1))
            painter.drawLine(int(plot_x), gy, int(plot_x + plot_w), gy)

        channels = (
            ('Red', QColor(244, 67, 54, 70), QColor(244, 67, 54, 200)),
            ('Green', QColor(76, 175, 80, 70), QColor(76, 175, 80, 200)),
            ('Blue', QColor(33, 150, 243, 70), QColor(33, 150, 243, 200)),
        )
        for key, fill_c, line_c in channels:
            counts = hist.get(key)
            if counts is None or counts.max() <= 0:
                continue
            max_c = float(counts.max())
            path = QPainterPath()
            path.moveTo(plot_x, plot_y + plot_h)
            for i in range(256):
                px = plot_x + i * plot_w / 255.0
                py = plot_y + plot_h - counts[i] / max_c * plot_h
                path.lineTo(px, py)
            path.lineTo(plot_x + plot_w, plot_y + plot_h)
            path.closeSubpath()
            painter.fillPath(path, fill_c)
            painter.setPen(QPen(line_c, 1.2))
            last_x, last_y = plot_x, plot_y + plot_h
            for i in range(256):
                px = plot_x + i * plot_w / 255.0
                py = plot_y + plot_h - counts[i] / max_c * plot_h
                if i > 0:
                    painter.drawLine(int(last_x), int(last_y), int(px), int(py))
                last_x, last_y = px, py

        luma = hist.get('Luma')
        if luma is not None and luma.max() > 0:
            max_c = float(luma.max())
            pen = QPen(QColor(230, 230, 230, 180), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            last_x, last_y = plot_x, plot_y + plot_h
            for i in range(256):
                px = plot_x + i * plot_w / 255.0
                py = plot_y + plot_h - luma[i] / max_c * plot_h
                if i > 0:
                    painter.drawLine(int(last_x), int(last_y), int(px), int(py))
                last_x, last_y = px, py

        legend_item_w = 22
        legend_x = ox + ow - pad - len(channels) * legend_item_w
        legend_y = oy + pad + 9
        for i, (_, fill_c, line_c) in enumerate(channels):
            lx = legend_x + i * legend_item_w
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(line_c))
            painter.drawEllipse(int(lx), int(legend_y - 5), 6, 6)
            painter.setPen(QColor(160, 160, 160))
            painter.drawText(int(lx + 9), int(legend_y), "RGB"[i])

        painter.restore()

    def _draw_eyedropper_crosshair(self, painter: QPainter, layout: Dict):
        if not self.eyedropper_enabled or self._sample_x is None:
            return
        pt = self._image_to_widget(layout, self._sample_x, self._sample_y)
        if pt is None:
            return
        cx, cy, cw, ch = layout['cell']
        cell = cell_rectf(layout['cell'])
        painter.save()
        painter.setClipRect(cell)
        pen = QPen(QColor(0, 0, 0, 160))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(pt.x(), int(cy), pt.x(), int(cy + ch))
        painter.drawLine(int(cx), pt.y(), int(cx + cw), pt.y())
        pen = QPen(QColor(255, 235, 59, 230))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(pt.x(), int(cy), pt.x(), int(cy + ch))
        painter.drawLine(int(cx), pt.y(), int(cx + cw), pt.y())
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawPoint(pt)
        painter.restore()

    def enter_tab_preview(self, slot_idx: int):
        """Long-press Tab: temporarily show next slot (last column wraps to first)."""
        if self._tab_preview_slot is not None:
            return
        if len(self.slots) <= 1:
            self.status_changed.emit(tr('compare_tab_single_slot'))
            return
        next_idx = (slot_idx + 1) % len(self.slots)
        self._tab_preview_slot = slot_idx
        self._tab_preview_backup = self.slots[slot_idx].info
        next_info = self.slots[next_idx].info
        self._load_slot(self.slots[slot_idx], next_info, slot_idx)
        if next_idx == 0 and slot_idx == len(self.slots) - 1:
            hint = tr('compare_tab_first')
        else:
            hint = tr('compare_tab_slot_n', n=next_idx + 1)
        self.status_changed.emit(
            tr('compare_tab_preview', from_n=slot_idx + 1, hint=hint, name=next_info.name),
        )
        self.update()

    def exit_tab_preview(self):
        if self._tab_preview_slot is None or self._tab_preview_backup is None:
            return
        idx = self._tab_preview_slot
        self._load_slot(self.slots[idx], self._tab_preview_backup, idx)
        self._tab_preview_slot = None
        self._tab_preview_backup = None
        self.status_changed.emit(self._row_status_line())
        self.slots_content_changed.emit()
        self.update()

    def _row_status_line(self) -> str:
        group = self.groups[self.group_index] if self.groups else []
        names = ", ".join(img.name[:12] for img in group[:3])
        if len(group) > 3:
            names += '...'
        return tr(
            'compare_status_row',
            idx=self.group_index + 1,
            total=len(self.groups),
            names=names,
        )

    def next_group(self):
        if len(self.groups) <= 1:
            self.status_changed.emit(tr('compare_one_group'))
            return
        self.exit_tab_preview()
        self.group_index = min(len(self.groups) - 1, self.group_index + 1)
        self._load_group(self.group_index)

    def prev_group(self):
        if len(self.groups) <= 1:
            self.status_changed.emit(tr('compare_one_group'))
            return
        self.exit_tab_preview()
        self.group_index = max(0, self.group_index - 1)
        self._load_group(self.group_index)

    def _load_group(self, index: int):
        self.group_index = index
        group = self.groups[index]
        for i, slot in enumerate(self.slots):
            if i < len(group):
                self._load_slot(slot, group[i], i)
                pool = self.slot_pools[i] if i < len(self.slot_pools) else [group[i]]
                self.slot_indices[i] = next(
                    (j for j, p in enumerate(pool) if p.path == group[i].path), 0
                )
        self.crop_rect_image = None
        self.status_changed.emit(self._row_status_line())
        self.slots_content_changed.emit()
        self.update()

    def _auto_grid_shape(self) -> Tuple[int, int]:
        n = len(self.slots)
        if n == 0:
            return 1, 1
        cols = n if n <= 4 else int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols)) if cols else 1
        return cols, rows

    def _fit_grid_shape(self, cols: int, rows: int) -> Tuple[int, int]:
        n = max(1, len(self.slots))
        cols = max(1, cols)
        rows = max(1, rows)
        if cols * rows < n:
            cols = int(np.ceil(n / rows))
        if cols * rows < n:
            rows = int(np.ceil(n / cols))
        return cols, rows

    def set_grid_layout(self, cols: int, rows: int) -> Tuple[int, int]:
        cols, rows = self._fit_grid_shape(cols, rows)
        self._layout_cols = cols
        self._layout_rows = rows
        self._slot_layouts = []
        self._clamp_pan()
        self.update()
        return cols, rows

    def reset_grid_layout(self) -> Tuple[int, int]:
        self._layout_cols = None
        self._layout_rows = None
        cols, rows = self._auto_grid_shape()
        self._slot_layouts = []
        self._clamp_pan()
        self.update()
        return cols, rows

    def get_grid_layout(self) -> Tuple[int, int]:
        if self._layout_cols and self._layout_rows:
            cols, rows = self._fit_grid_shape(self._layout_cols, self._layout_rows)
            return cols, rows
        return self._auto_grid_shape()

    def _grid_shape(self) -> Tuple[int, int]:
        return self.get_grid_layout()

    def _cell_rect(self, index: int) -> Tuple[float, float, float, float]:
        cols, rows = self._grid_shape()
        W = max(1, self.width())
        H = max(1, self.height())
        col_w = W / cols
        row_h = H / rows
        col = index % cols
        row = index // cols
        return col * col_w, row * row_h, col_w, row_h

    def _pan_limits_for_slot(self, layout: Dict) -> Tuple[float, float, float, float]:
        """Return allowed pan_x / pan_y range for this slot (min_x, max_x, min_y, max_y)."""
        cx, cy, cw, ch = layout['cell']
        slot = layout['slot']
        if slot.qimage is None or slot.qimage.isNull():
            return (0.0, 0.0, 0.0, 0.0)

        iw, ih = slot.qimage.width(), slot.qimage.height()
        base_scale = min(cw / iw, ch / ih)
        disp_w = iw * base_scale * self.global_zoom
        disp_h = ih * base_scale * self.global_zoom

        if disp_w <= cw:
            margin_x = (cw - disp_w) / 2
            min_px, max_px = -margin_x, margin_x
        else:
            min_px = (cw - disp_w) / 2
            max_px = (disp_w - cw) / 2

        if disp_h <= ch:
            margin_y = (ch - disp_h) / 2
            min_py, max_py = -margin_y, margin_y
        else:
            min_py = (ch - disp_h) / 2
            max_py = (disp_h - ch) / 2

        return min_px, max_px, min_py, max_py

    def _clamp_pan(self, primary_slot: Optional[int] = None):
        if not self._slot_layouts:
            self._slot_layouts = self._compute_layouts()

        layouts = self._slot_layouts
        if primary_slot is not None and 0 <= primary_slot < len(layouts):
            layout = layouts[primary_slot]
            if layout.get('draw'):
                min_px, max_px, min_py, max_py = self._pan_limits_for_slot(layout)
                self.global_pan_x = max(min_px, min(max_px, self.global_pan_x))
                self.global_pan_y = max(min_py, min(max_py, self.global_pan_y))
                return

        min_px, max_px = float('-inf'), float('inf')
        min_py, max_py = float('-inf'), float('inf')

        for layout in layouts:
            if not layout.get('draw'):
                continue
            sx0, sx1, sy0, sy1 = self._pan_limits_for_slot(layout)
            min_px = max(min_px, sx0)
            max_px = min(max_px, sx1)
            min_py = max(min_py, sy0)
            max_py = min(max_py, sy1)

        if min_px > max_px:
            min_px = max_px = 0.0
        if min_py > max_py:
            min_py = max_py = 0.0

        self.global_pan_x = max(min_px, min(max_px, self.global_pan_x))
        self.global_pan_y = max(min_py, min(max_py, self.global_pan_y))

    def _compute_layouts(self) -> List[Dict]:
        layouts = []
        n = len(self.slots)
        cols, rows = self._grid_shape()

        for i in range(n):
            cell_x, cell_y, cw, ch = self._cell_rect(i)
            slot = self.slots[i]

            if slot.qimage is None or slot.qimage.isNull():
                layouts.append({
                    'slot': slot, 'cell': (cell_x, cell_y, cw, ch),
                    'draw': None, 'index': i,
                })
                continue

            iw, ih = slot.qimage.width(), slot.qimage.height()
            base_scale = min(cw / iw, ch / ih)
            scale = base_scale * self.global_zoom
            disp_w = iw * scale
            disp_h = ih * scale
            draw_x = cell_x + (cw - disp_w) / 2 + self.global_pan_x
            draw_y = cell_y + (ch - disp_h) / 2 + self.global_pan_y

            layouts.append({
                'slot': slot,
                'cell': (cell_x, cell_y, cw, ch),
                'draw': (draw_x, draw_y, disp_w, disp_h, scale, iw, ih),
                'index': i,
            })
        return layouts

    def _visible_image_range(
        self, layout: Dict, dx: float, dy: float, scale: float, iw: int, ih: int,
    ) -> Tuple[int, int, int, int]:
        cx, cy, cw, ch = layout['cell']
        x0 = max(0, int(math.floor((cx - dx) / scale)))
        y0 = max(0, int(math.floor((cy - dy) / scale)))
        x1 = min(iw, int(math.ceil((cx + cw - dx) / scale)))
        y1 = min(ih, int(math.ceil((cy + ch - dy) / scale)))
        return x0, y0, x1, y1

    def _text_color_for_rgb(self, r: int, g: int, b: int) -> QColor:
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return QColor(255, 255, 255, 230) if lum < 140 else QColor(0, 0, 0, 220)

    def _draw_pixel_grid(
        self, painter: QPainter, layout: Dict,
        dx: float, dy: float, scale: float, iw: int, ih: int,
    ):
        x0, y0, x1, y1 = self._visible_image_range(layout, dx, dy, scale, iw, ih)
        if x1 <= x0 or y1 <= y0:
            return
        cx, cy, cw, ch = layout['cell']
        painter.setPen(QPen(QColor(255, 255, 255, 55), 1))
        left = max(dx + x0 * scale, cx)
        right = min(dx + x1 * scale, cx + cw)
        top = max(dy + y0 * scale, cy)
        bottom = min(dy + y1 * scale, cy + ch)
        for px in range(x0, x1 + 1):
            wx = dx + px * scale
            if cx <= wx <= cx + cw:
                painter.drawLine(int(wx), int(top), int(wx), int(bottom))
        for py in range(y0, y1 + 1):
            wy = dy + py * scale
            if cy <= wy <= cy + ch:
                painter.drawLine(int(left), int(wy), int(right), int(wy))

    def _draw_pixel_rgb_labels(
        self, painter: QPainter, layout: Dict, slot: ImageSlot,
        dx: float, dy: float, scale: float, iw: int, ih: int,
    ):
        arr = slot.array
        if arr is None:
            return
        x0, y0, x1, y1 = self._visible_image_range(layout, dx, dy, scale, iw, ih)
        count = (x1 - x0) * (y1 - y0)
        if count <= 0 or count > MAX_PIXEL_RGB_LABELS:
            return

        detail = scale >= PIXEL_RGB_DETAIL_SCALE
        font = QFont()
        font.setPointSize(max(6, min(9, int(scale / 6))))
        painter.setFont(font)

        for py in range(y0, y1):
            for px in range(x0, x1):
                r = int(arr[py, px, 0])
                g = int(arr[py, px, 1])
                b = int(arr[py, px, 2])
                sx = dx + px * scale
                sy = dy + py * scale
                text_color = self._text_color_for_rgb(r, g, b)

                if detail:
                    line_h = max(8, int(scale / 3.2))
                    y_base = int(sy + max(2, (scale - line_h * 3) / 2) + line_h - 2)
                    dark = text_color.lightness() > 128
                    painter.setPen(QColor(244, 67, 54, 240) if dark else QColor(255, 120, 120))
                    painter.drawText(int(sx + 2), y_base, f"R:{r}")
                    painter.setPen(QColor(76, 175, 80, 240) if dark else QColor(140, 255, 160))
                    painter.drawText(int(sx + 2), y_base + line_h, f"G:{g}")
                    painter.setPen(QColor(33, 150, 243, 240) if dark else QColor(140, 190, 255))
                    painter.drawText(int(sx + 2), y_base + line_h * 2, f"B:{b}")
                else:
                    line_h = max(6, int(scale / 3.0))
                    y_base = int(sy + max(1, (scale - line_h * 3) / 2) + line_h - 1)
                    dark = text_color.lightness() > 128
                    painter.setPen(QColor(244, 67, 54, 240) if dark else QColor(255, 120, 120))
                    painter.drawText(int(sx + 1), y_base, f"R:{r}")
                    painter.setPen(QColor(76, 175, 80, 240) if dark else QColor(140, 255, 160))
                    painter.drawText(int(sx + 1), y_base + line_h, f"G:{g}")
                    painter.setPen(QColor(33, 150, 243, 240) if dark else QColor(140, 190, 255))
                    painter.drawText(int(sx + 1), y_base + line_h * 2, f"B:{b}")

    def paintEvent(self, event):
        painter = QPainter(self)
        c = self._colors
        painter.fillRect(self.rect(), self._c('canvas_bg'))

        self._slot_layouts = self._compute_layouts()
        pixel_inspector = False

        for layout in self._slot_layouts:
            draw = layout.get('draw')
            if draw is not None and self._should_show_pixel_inspector(draw[4]):
                pixel_inspector = True
                break

        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            not pixel_inspector,
        )

        for layout in self._slot_layouts:
            cell = cell_rectf(layout['cell'])
            cx, cy, cw, ch = layout['cell']
            slot = layout['slot']
            draw = layout['draw']
            idx = layout['index']

            painter.fillRect(cell, self._c('canvas_bg'))

            if idx == self._hover_slot_index:
                painter.fillRect(cell, self._cell_hover)

            if idx > 0:
                painter.setPen(QPen(self._c('panel_border'), 1))
                painter.drawLine(int(cx), int(cy), int(cx), int(cy + ch))

            if draw is None:
                painter.setPen(self._c('text_dim'))
                painter.drawText(cell, Qt.AlignmentFlag.AlignCenter, tr('loading'))
                continue

            dx, dy, dw, dh, scale, iw, ih = draw

            painter.save()
            painter.setClipRect(cell)
            painter.drawImage(QRectF(dx, dy, dw, dh), slot.qimage, QRectF(0, 0, iw, ih))
            if self._should_show_pixel_inspector(scale):
                self._draw_pixel_grid(painter, layout, dx, dy, scale, iw, ih)
                self._draw_pixel_rgb_labels(painter, layout, slot, dx, dy, scale, iw, ih)
            self._draw_eyedropper_crosshair(painter, layout)
            self._draw_histogram_overlay(painter, layout['cell'], idx)
            painter.restore()

            crop = self.crop_rect_image
            if self.crop_draft_widget and idx == self._active_slot_index:
                crop = self._widget_rect_to_image(layout, self.crop_draft_widget)

            if crop and crop.width() > 0 and crop.height() > 0:
                sx = dx + crop.x() * scale
                sy = dy + crop.y() * scale
                sw = crop.width() * scale
                sh = crop.height() * scale
                painter.save()
                painter.setClipRect(cell)
                pen = QPen(QColor('#ff0000'))
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                crop_box = QRectF(sx, sy, sw, sh)
                if self.crop_shape == 'circle':
                    painter.drawEllipse(crop_box)
                else:
                    painter.drawRect(crop_box)
                painter.restore()

            pool_len = len(self.slot_pools[idx]) if idx < len(self.slot_pools) else 1
            pool_pos = self.slot_indices[idx] + 1 if idx < len(self.slot_indices) else 1

            if self.show_slot_overlay:
                painter.save()
                painter.setClipRect(cell)
                painter.setPen(self._c('success'))
                font = painter.font()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                max_w = max(40, int(cw - 16))
                folder_name = self._folder_name_map.get(slot.info.path, "")
                if not folder_name:
                    from pathlib import Path
                    folder_name = Path(slot.info.path).parent.name
                folder_line = painter.fontMetrics().elidedText(
                    f"{tr('folder_label')}: {folder_name}",
                    Qt.TextElideMode.ElideMiddle,
                    max_w,
                )
                name_line = painter.fontMetrics().elidedText(
                    f"{tr('name_label')}: {slot.info.name}",
                    Qt.TextElideMode.ElideMiddle,
                    max_w,
                )
                meta_lines = [
                    folder_line,
                    name_line,
                    f"{tr('resolution_label')}: {iw} × {ih}",
                    f"{tr('size_label')}: {self._fmt_size(slot.info.file_size)}",
                    f"{tr('scale_label')}: {int(self.global_zoom * 100)}%  |  {pool_pos}/{pool_len}",
                ]
                if self._should_show_pixel_inspector(scale):
                    meta_lines.append(tr('overlay_pixel_grid', scale=int(self.pixel_inspector_min_scale)))
                if idx == self._hover_slot_index:
                    if self._tab_preview_slot == idx:
                        hint = tr('overlay_previewing')
                    elif len(self.slots) > 1:
                        hint = tr('overlay_tab_hint')
                    else:
                        hint = ""
                    if hint:
                        meta_lines.append(hint)
                for li, line in enumerate(meta_lines):
                    painter.drawText(int(cx + 8), int(cy + 18 + li * 16), line)
                painter.restore()

            if self.show_metrics_overlay and len(self.slots) > 1:
                painter.save()
                painter.setClipRect(cell)
                font = painter.font()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                metric_lines: List[str] = []
                if idx == self.metrics_baseline_idx:
                    metric_lines.append(self.metrics_baseline_label)
                elif idx in self.slot_metrics:
                    vals = self.slot_metrics[idx]
                    for key in self.metrics_enabled_keys:
                        if key in vals:
                            metric_lines.append(format_metric_value(key, vals[key]))
                if metric_lines:
                    painter.setPen(self._c('accent'))
                    fm = painter.fontMetrics()
                    line_h = fm.height() + 6
                    y_base = int(cy + ch - 10)
                    for mi, line in enumerate(reversed(metric_lines)):
                        painter.drawText(int(cx + 8), y_base - mi * line_h, line)
                painter.restore()

    def _fmt_size(self, size: int) -> str:
        from utils.file_utils import format_file_size
        return format_file_size(size)

    def _widget_rect_to_image(self, layout: Dict, widget_rect: Optional[QRect]) -> Optional[QRect]:
        if widget_rect is None or layout.get('draw') is None:
            return None
        dx, dy, dw, dh, scale, iw, ih = layout['draw']
        if scale <= 0:
            return None
        x1 = int(max(0, min(iw, (widget_rect.left() - dx) / scale)))
        y1 = int(max(0, min(ih, (widget_rect.top() - dy) / scale)))
        x2 = int(max(0, min(iw, (widget_rect.right() - dx) / scale)))
        y2 = int(max(0, min(ih, (widget_rect.bottom() - dy) / scale)))
        if x2 <= x1 or y2 <= y1:
            return None
        return QRect(x1, y1, x2 - x1, y2 - y1)

    def _slot_at_pos(self, pos: QPoint) -> int:
        if not self._slot_layouts:
            self._slot_layouts = self._compute_layouts()
        px, py = pos.x(), pos.y()
        for layout in self._slot_layouts:
            cx, cy, cw, ch = layout['cell']
            if cx <= px < cx + cw and cy <= py < cy + ch:
                return layout['index']
        return self._hover_slot_index

    def _slot_at_cursor(self) -> int:
        """Resolve slot under mouse (for Tab preview)."""
        pos = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(pos):
            return self._slot_at_pos(pos)
        return self._hover_slot_index

    def _max_zoom_limit(self) -> float:
        limit = MAX_ZOOM
        layouts = self._slot_layouts or self._compute_layouts()
        for layout in layouts:
            cx, cy, cw, ch = layout['cell']
            draw = layout.get('draw')
            if draw:
                iw, ih = draw[5], draw[6]
            else:
                slot = layout['slot']
                if slot.qimage is None or slot.qimage.isNull():
                    continue
                iw, ih = slot.qimage.width(), slot.qimage.height()
            base_scale = min(cw / iw, ch / ih)
            if base_scale > 0:
                limit = max(limit, MAX_SCALE / base_scale)
        return limit

    def _zoom_at(self, anchor: QPoint, new_zoom: float):
        self._slot_layouts = self._compute_layouts()

        idx = self._slot_at_pos(anchor)
        self._set_active_slot_index(idx)
        layout = self._slot_layouts[idx] if idx < len(self._slot_layouts) else None
        if not layout or not layout.get('draw'):
            return

        cx, cy, cw, ch = layout['cell']
        dx, dy, dw, dh, scale, iw, ih = layout['draw']
        mx, my = anchor.x(), anchor.y()
        if scale <= 0:
            return

        pan_x, pan_y = self.global_pan_x, self.global_pan_y
        img_x = (mx - cx - (cw - dw) / 2 - pan_x) / scale
        img_y = (my - cy - (ch - dh) / 2 - pan_y) / scale

        old_zoom = self.global_zoom
        max_zoom = self._max_zoom_limit()
        self.global_zoom = max(MIN_ZOOM, min(max_zoom, new_zoom))
        if abs(self.global_zoom - old_zoom) < 1e-6:
            return

        base_scale = min(cw / iw, ch / ih)
        new_scale = base_scale * self.global_zoom
        new_disp_w = iw * new_scale
        new_disp_h = ih * new_scale

        self.global_pan_x = mx - cx - (cw - new_disp_w) / 2 - img_x * new_scale
        self.global_pan_y = my - cy - (ch - new_disp_h) / 2 - img_y * new_scale
        self._clamp_pan(idx)
        self.zoom_changed.emit(self.global_zoom)
        self.update()

    def _apply_pinch_zoom_at(self, pos: QPoint, pixels: float):
        if pixels == 0:
            return
        factor = zoom_factor_from_pixels(pixels)
        self._zoom_at(pos, self.global_zoom * factor)

    def event(self, event):
        pixels = try_handle_pinch_event(event)
        if pixels is not None:
            if pixels != 0:
                if hasattr(event, "position"):
                    pos = event.position().toPoint()
                else:
                    pos = self.mapFromGlobal(QCursor.pos())
                self._set_active_slot_index(self._slot_at_pos(pos))
                self._hover_slot_index = self._active_slot_index
                self._apply_pinch_zoom_at(pos, pixels)
            return True
        return super().event(event)

    def wheelEvent(self, event: QWheelEvent):
        pos = event.position().toPoint()
        self._set_active_slot_index(self._slot_at_pos(pos))
        self._hover_slot_index = self._active_slot_index

        delta = wheel_event_pixel_delta(event)
        if delta == 0:
            return

        self._apply_pinch_zoom_at(pos, delta)
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(_compare_menu_style(self._colors))
        idx = self._slot_at_pos(event.pos())
        menu.addAction(tr('ctx_reset_zoom'), self.reset_view)
        menu.addAction(tr('ctx_zoom_in'), lambda: self._zoom_at(event.pos(), self.global_zoom * ZOOM_WHEEL_FACTOR))
        menu.addAction(tr('ctx_zoom_out'), lambda: self._zoom_at(event.pos(), self.global_zoom / ZOOM_WHEEL_FACTOR))
        menu.addSeparator()
        menu.addAction(tr('ctx_next_group'), self.next_group)
        menu.addAction(tr('ctx_prev_group'), self.prev_group)
        menu.addSeparator()
        menu.addAction(tr('ctx_export_crop'), lambda: self.window()._export_crop())
        menu.addAction(tr('ctx_pixel_diff'), lambda: self.window()._open_pixel_diff())
        menu.addAction(tr('ctx_toggle_hist'), lambda: self.window()._toggle_histogram())
        dlg = self.window()
        if hasattr(dlg, '_populate_custom_tool_menu'):
            dlg._populate_custom_tool_menu(menu, idx)
        if idx < len(self.slots) and self.slots[idx].info:
            path = self.slots[idx].info.path
            menu.addSeparator()
            menu.addAction(tr('ctx_copy_path'), lambda: self._copy_path(path))
            import sys
            reveal_key = 'ctx_reveal' if sys.platform == 'darwin' else 'ctx_reveal_win'
            menu.addAction(tr(reveal_key), lambda: self._reveal(path))
        menu.exec(event.globalPos())

    def _copy_path(self, path: str):
        from utils.platform_utils import copy_text_to_clipboard
        copy_text_to_clipboard(path)

    def _reveal(self, path: str):
        from utils.platform_utils import reveal_in_file_manager
        reveal_in_file_manager(path)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()

        if key == Qt.Key.Key_Tab and not event.isAutoRepeat():
            if self._tab_preview_slot is None:
                self.enter_tab_preview(self._slot_at_cursor())
            event.accept()
            return

        if key == Qt.Key.Key_R:
            self.reset_view()
        elif key == Qt.Key.Key_Up:
            self.global_pan_y += 15
            self._clamp_pan()
            self.update()
        elif key == Qt.Key.Key_Down:
            self.global_pan_y -= 15
            self._clamp_pan()
            self.update()
        elif key == Qt.Key.Key_Escape:
            dlg = self.window()
            if hasattr(dlg, '_on_escape_pressed'):
                dlg._on_escape_pressed()
            else:
                exit_window_fullscreen(dlg)
            event.accept()
            return
        elif key == Qt.Key.Key_Backspace:
            dlg = self.window()
            if hasattr(dlg, 'remove_folder_column_at_cursor'):
                dlg.remove_folder_column_at_cursor()
            event.accept()
            return
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Tab and not event.isAutoRepeat():
            self.exit_tab_preview()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def set_copy_format(self, fmt: str):
        self._copy_format = fmt if fmt in ('rgb', 'hex') else 'rgb'

    def set_copy_enabled(self, enabled: bool):
        self._copy_enabled = enabled

    def copy_format(self) -> str:
        return self._copy_format

    def _copy_eyedropper_rgb(self, pos: QPoint) -> bool:
        """Copy color at click position to clipboard; return success."""
        samples = self._update_eyedropper_sample(pos)
        if not samples:
            return False
        self.pixel_samples_changed.emit(samples)
        idx = self._slot_at_pos(pos)
        if idx < 0 or idx >= len(samples) or not samples[idx].get('valid'):
            return False
        if not self._copy_enabled:
            return False
        r, g, b = samples[idx]['rgb']
        hex_val = f"#{r:02X}{g:02X}{b:02X}"
        from utils.platform_utils import copy_text_to_clipboard
        if self._copy_format == 'hex':
            copy_text_to_clipboard(hex_val)
            self.status_changed.emit(tr('copied_hex', val=hex_val))
        else:
            copy_text_to_clipboard(f"{r},{g},{b}")
            self.status_changed.emit(tr('copied_rgb', r=r, g=g, b=b))
        self.rgb_copied.emit(r, g, b)
        self.update()
        return True

    def mousePressEvent(self, event: QMouseEvent):
        self.setFocus()
        self._set_active_slot_index(self._slot_at_pos(event.pos()))
        self._hover_slot_index = self._active_slot_index
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.drawing_crop = True
                self.crop_start_widget = event.pos()
                self.crop_draft_widget = None
            elif self.eyedropper_enabled:
                self._eyedropper_click_pending = True
                self._eyedropper_press_pos = event.pos()
            else:
                self.panning = True
                self.pan_start = event.pos()
                self.pan_start_offset = (self.global_pan_x, self.global_pan_y)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._slot_layouts:
            hover = self._slot_at_pos(event.pos())
            if hover != self._hover_slot_index:
                self._hover_slot_index = hover
                self.update()

        if self.eyedropper_enabled and not self.drawing_crop and not self.panning:
            samples = self._update_eyedropper_sample(event.pos())
            if samples is not None:
                self.pixel_samples_changed.emit(samples)
                self.update()

        if self._eyedropper_click_pending and self._eyedropper_press_pos is not None:
            if (event.pos() - self._eyedropper_press_pos).manhattanLength() > 5:
                self._eyedropper_click_pending = False
                self.panning = True
                self.pan_start = self._eyedropper_press_pos
                self.pan_start_offset = (self.global_pan_x, self.global_pan_y)

        if self.drawing_crop and self.crop_start_widget:
            self.crop_draft_widget = crop_widget_rect_from_points(
                self.crop_start_widget, event.pos(), self.crop_shape,
            )
            self.update()
        elif self.panning and self.pan_start:
            delta = event.pos() - self.pan_start
            self.global_pan_x = self.pan_start_offset[0] + delta.x()
            self.global_pan_y = self.pan_start_offset[1] + delta.y()
            self._clamp_pan(self._active_slot_index)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._eyedropper_click_pending and self._eyedropper_press_pos is not None:
                self._copy_eyedropper_rgb(self._eyedropper_press_pos)
                self._eyedropper_click_pending = False
                self._eyedropper_press_pos = None
            if self.drawing_crop and self.crop_draft_widget and self._slot_layouts:
                idx = self._active_slot_index
                if idx < len(self._slot_layouts):
                    img_rect = self._widget_rect_to_image(self._slot_layouts[idx], self.crop_draft_widget)
                    if img_rect and img_rect.width() > 4 and img_rect.height() > 4:
                        self.crop_rect_image = img_rect
                        shape_keys = {'rect': 'crop_rect', 'square': 'crop_square', 'circle': 'crop_circle'}
                        shape_label = tr(shape_keys.get(self.crop_shape, 'crop_rect'))
                        self.status_changed.emit(
                            tr(
                                'crop_region_status',
                                shape=shape_label,
                                x=img_rect.x(),
                                y=img_rect.y(),
                                w=img_rect.width(),
                                h=img_rect.height(),
                            ),
                        )
                self.crop_draft_widget = None
            self.drawing_crop = False
            self.panning = False

    def reset_view(self):
        self.global_zoom = 1.0
        self.global_pan_x = 0.0
        self.global_pan_y = 0.0
        self.zoom_changed.emit(self.global_zoom)
        self.update()

    def set_crop_shape(self, shape: str):
        if shape not in ('rect', 'square', 'circle'):
            shape = 'rect'
        if self.crop_shape != shape:
            self.crop_shape = shape
            self.crop_rect_image = None
            self.crop_draft_widget = None
            self.update()

    def get_crop_rect(self) -> Optional[Rect]:
        region = self.get_crop_region()
        return region.rect if region else None

    def get_crop_region(self) -> Optional[CropRegion]:
        if self.crop_rect_image is None:
            return None
        r = self.crop_rect_image
        return CropRegion(
            Rect(r.x(), r.y(), r.width(), r.height()),
            self.crop_shape,
        )

    def get_export_images(self) -> List[ImageInfo]:
        return [s.info for s in self.slots]


class CompareDialog(QDialog):
    folder_column_remove_requested = pyqtSignal(int)

    def __init__(
        self,
        images: List[ImageInfo],
        folder_manager: FolderManager,
        image_loader: ImageLoader,
        slot_pools: Optional[List[List[ImageInfo]]] = None,
        groups: Optional[List[List[ImageInfo]]] = None,
    ):
        super().__init__()
        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.images = images
        self.folder_manager = folder_manager
        self.image_loader = image_loader
        self.slot_pools = slot_pools
        self.groups = groups or [images]

        self.setWindowTitle(tr('compare_title_names', n=len(images), names='…'))
        self.resize(COMPARE_WINDOW_WIDTH, COMPARE_WINDOW_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._group_navigator = None
        self._column_remove_in_progress = False
        self._build_ui()
        self._setup_escape_shortcut()

    def _setup_escape_shortcut(self):
        """ESC exits fullscreen only; QShortcut blocks QDialog default ESC→reject()."""
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self._on_escape_pressed)

    def _on_escape_pressed(self):
        exit_window_fullscreen(self)

    def set_group_navigator(self, callback):
        """Set callback for Space/B compare group navigation: callback(delta)."""
        self._group_navigator = callback

    def remove_folder_column_at_cursor(self):
        """Backspace: remove folder for column under mouse."""
        self.folder_column_remove_requested.emit(self.canvas._slot_at_cursor())

    def remove_column_in_place(
        self,
        slot_index: int,
        images: List[ImageInfo],
        groups: List[List[ImageInfo]],
        slot_pools: List[List[ImageInfo]],
        group_index: int,
        title: str,
    ) -> bool:
        """Remove compare column in place without closing or resetting tools."""
        if slot_index < 0 or slot_index >= len(self.canvas.slots):
            return False

        self._column_remove_in_progress = True
        try:
            if not self.canvas.remove_slot_at(
                slot_index, groups, slot_pools, group_index,
            ):
                return False

            self.images = images
            self.groups = groups
            self.slot_pools = slot_pools
            self.setWindowTitle(title)

            if self.diff_map_cb.isChecked():
                self.diff_map_panel.remove_slot_at(slot_index)
                self._update_diff_map()

            if self.eyedropper_cb.isChecked():
                self.pixel_panel.set_slot_count(len(self.canvas.slots))
                self.pixel_panel.update_samples(self.canvas.collect_pixel_samples())

            self._sync_grid_spinboxes()
            return True
        finally:
            self._column_remove_in_progress = False

    def reload_modified_images(self, paths: set):
        """Refresh images and metadata after rotation or similar edits."""
        paths = set(paths)
        if not paths:
            return

        info_by_path: Dict[str, ImageInfo] = {}
        for folder in self.folder_manager.folders:
            for img in folder.images:
                if img.path in paths:
                    info_by_path[img.path] = img

        self.images = [
            info_by_path.get(img.path, img) if img.path in paths else img
            for img in self.images
        ]
        self.canvas.reload_images_by_path(paths, info_by_path)

    def _build_ui(self):
        self.setStyleSheet(get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._compare_seps: List[QFrame] = []

        self._toolbar_bar = QWidget()
        self._toolbar_bar.setObjectName("compareToolbar")
        self._toolbar_bar.setFixedHeight(38)
        toolbar = QHBoxLayout(self._toolbar_bar)
        toolbar.setContentsMargins(12, 0, 12, 0)
        toolbar.setSpacing(8)

        zoom_group, zoom_lay = _compare_group()
        zoom_group.setObjectName("compareZoomGroup")
        zoom_group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        zoom_lay.setContentsMargins(6, 3, 6, 3)
        zoom_lay.setSpacing(8)
        zoom_lbl = CaptionLabel("缩放")
        zoom_lbl.setObjectName("compareMutedLabel")
        self._zoom_lbl = zoom_lbl
        zoom_lay.addWidget(zoom_lbl)
        self.zoom_slider = Slider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(0, ZOOM_SLIDER_STEPS)
        self.zoom_slider.setValue(zoom_to_slider_pos(1.0, MAX_ZOOM))
        self.zoom_slider.setFixedWidth(108)
        self.zoom_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        enable_slider_keyboard_tune(self.zoom_slider)
        self.zoom_slider.setToolTip("视图缩放（滚轮可超过滑条上限）")
        zoom_lay.addWidget(self.zoom_slider)
        zoom_lay.addSpacing(4)
        reset_btn = PushButton("还原")
        _style_dialog_button(reset_btn, width=44)
        reset_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        reset_btn.setToolTip("还原缩放与平移 (R)")
        self._reset_view_btn = reset_btn
        zoom_lay.addWidget(reset_btn)
        _fit_zoom_group(self)
        self._zoom_group = zoom_group
        toolbar.addWidget(zoom_group, 0, Qt.AlignmentFlag.AlignLeft)

        sep1 = _compare_vsep()
        self._compare_seps.append(sep1)
        toolbar.addWidget(sep1)

        layout_group, layout_lay = _compare_group()
        layout_lay.setSpacing(4)
        cols_lbl = CaptionLabel("列")
        cols_lbl.setObjectName("compareMutedLabel")
        self._cols_lbl = cols_lbl
        layout_lay.addWidget(cols_lbl)
        self.grid_cols_spin = QSpinBox()
        self.grid_cols_spin.setRange(1, 12)
        self.grid_cols_spin.setValue(1)
        _style_dialog_spinbox(self.grid_cols_spin)
        self.grid_cols_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grid_cols_spin.setToolTip("对比网格列数")
        self.grid_cols_spin.valueChanged.connect(self._on_grid_layout_changed)
        layout_lay.addWidget(self.grid_cols_spin)
        times_lbl = CaptionLabel("×")
        times_lbl.setObjectName("compareMutedLabel")
        layout_lay.addWidget(times_lbl)
        rows_lbl = CaptionLabel("行")
        rows_lbl.setObjectName("compareMutedLabel")
        self._rows_lbl = rows_lbl
        layout_lay.addWidget(rows_lbl)
        self.grid_rows_spin = QSpinBox()
        self.grid_rows_spin.setRange(1, 12)
        self.grid_rows_spin.setValue(1)
        _style_dialog_spinbox(self.grid_rows_spin)
        self.grid_rows_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grid_rows_spin.setToolTip("对比网格行数")
        self.grid_rows_spin.valueChanged.connect(self._on_grid_layout_changed)
        layout_lay.addWidget(self.grid_rows_spin)
        auto_grid_btn = PushButton("自动")
        _style_dialog_button(auto_grid_btn, width=40)
        auto_grid_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        auto_grid_btn.setToolTip("按图片数量自动排列行列")
        auto_grid_btn.clicked.connect(self._on_grid_layout_auto)
        self._auto_grid_btn = auto_grid_btn
        layout_lay.addWidget(auto_grid_btn)
        toolbar.addWidget(layout_group)

        sep2 = _compare_vsep()
        self._compare_seps.append(sep2)
        toolbar.addWidget(sep2)

        info_group, info_lay = _compare_group()
        info_lay.setSpacing(14)
        self.slot_info_cb = DialogCheckBox("信息")
        style_dialog_checkbox(self.slot_info_cb, spacing=4)
        self.slot_info_cb.setChecked(True)
        self.slot_info_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slot_info_cb.setToolTip("显示各分区文件夹、文件名、分辨率等")
        self.slot_info_cb.toggled.connect(self._on_slot_info_toggled)
        info_lay.addWidget(self.slot_info_cb)
        self.histogram_cb = DialogCheckBox("直方图")
        style_dialog_checkbox(self.histogram_cb, spacing=4)
        self.histogram_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.histogram_cb.setToolTip("切换直方图叠加 (H)")
        self.histogram_cb.toggled.connect(self._on_histogram_toggled)
        info_lay.addWidget(self.histogram_cb)
        toolbar.addWidget(info_group)

        toolbar.addStretch()

        crop_group, crop_lay = _compare_group()
        crop_lay.setSpacing(4)
        crop_lbl = CaptionLabel("裁剪")
        crop_lbl.setObjectName("compareMutedLabel")
        self._crop_lbl = crop_lbl
        crop_lay.addWidget(crop_lbl)
        self.crop_shape_combo = ComboBox()
        style_dialog_combo(self.crop_shape_combo)
        self.crop_shape_combo.setToolTip("Shift+拖拽 框选裁剪形状")
        for key, _ in CROP_SHAPE_OPTIONS:
            self.crop_shape_combo.addItem(tr(key))
        fit_dialog_combo_width(
            self.crop_shape_combo,
            [tr(key) for key, _ in CROP_SHAPE_OPTIONS],
        )
        self.crop_shape_combo.currentIndexChanged.connect(self._on_crop_shape_changed)
        crop_lay.addWidget(self.crop_shape_combo)
        export_crop_btn = PushButton("导出")
        _style_dialog_button(export_crop_btn, width=44)
        export_crop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        export_crop_btn.setToolTip("导出裁剪结果")
        export_crop_btn.clicked.connect(self._export_crop)
        self._export_crop_btn = export_crop_btn
        crop_lay.addWidget(export_crop_btn)
        toolbar.addWidget(crop_group)

        layout.addWidget(self._toolbar_bar)

        self.status_label = QLabel("")
        self.status_label.setObjectName("compareStatusStrip")
        self.status_label.setAutoFillBackground(True)
        self.status_label.setFixedHeight(24)
        self.status_label.setWordWrap(False)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._status_full_text = ""
        layout.addWidget(self.status_label)

        self.canvas = CompareCanvas(
            self.images, self.image_loader, self.slot_pools, self.groups,
            folder_name_map=self._folder_name_map(),
        )
        self.canvas.set_crop_shape(_crop_shape_from_index(self.crop_shape_combo.currentIndex()))
        layout.addWidget(self.canvas, stretch=1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 0, 12, 0)
        bottom.setSpacing(12)

        tool_group_margins = (5, 1, 5, 1)
        tool_group_height = DIALOG_TOOLBAR_HEIGHT + 2
        tool_align = Qt.AlignmentFlag.AlignVCenter

        analysis_group, analysis_lay = _compare_group()
        analysis_group.setObjectName("compareAnalysisGroup")
        analysis_group.setFixedHeight(tool_group_height)
        analysis_lay.setContentsMargins(*tool_group_margins)
        analysis_lay.setSpacing(18)
        analysis_lay.setAlignment(tool_align)
        self.eyedropper_cb = DialogCheckBox("吸管")
        style_dialog_checkbox(self.eyedropper_cb, spacing=5)
        self.eyedropper_cb.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self.eyedropper_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.eyedropper_cb.setToolTip("移动鼠标对比像素；左键点击复制颜色（格式见下方）")
        self.eyedropper_cb.toggled.connect(self._on_eyedropper_toggled)
        analysis_lay.addWidget(self.eyedropper_cb, 0, tool_align)

        self.diff_map_cb = DialogCheckBox("差异图")
        style_dialog_checkbox(self.diff_map_cb, spacing=5)
        self.diff_map_cb.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self.diff_map_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.diff_map_cb.setToolTip("选择两个分区显示差异热力图")
        self.diff_map_cb.toggled.connect(self._on_diff_map_toggled)
        analysis_lay.addWidget(self.diff_map_cb, 0, tool_align)

        self.color_view_cb = DialogCheckBox("色彩")
        style_dialog_checkbox(self.color_view_cb, spacing=5)
        self.color_view_cb.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self.color_view_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.color_view_cb.setToolTip("通道顺序、亮度、对比度、Gamma 等视图调整（不写回文件）")
        self.color_view_cb.toggled.connect(self._on_color_view_toggled)
        analysis_lay.addWidget(self.color_view_cb, 0, tool_align)

        self.custom_tool_cb = DialogCheckBox("扩展")
        style_dialog_checkbox(self.custom_tool_cb, spacing=5)
        self.custom_tool_cb.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self.custom_tool_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.custom_tool_cb.setToolTip("运行 Python 扩展工具（可新建、命名、保存）")
        self.custom_tool_cb.toggled.connect(self._on_custom_tool_toggled)
        analysis_lay.addWidget(self.custom_tool_cb, 0, tool_align)

        self.metrics_cb = DialogCheckBox("指标")
        style_dialog_checkbox(self.metrics_cb, spacing=5)
        self.metrics_cb.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self.metrics_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.metrics_cb.toggled.connect(self._on_metrics_toggled)
        analysis_lay.addWidget(self.metrics_cb, 0, tool_align)

        self._rgb_group, rgb_group_lay = _compare_group()
        self._rgb_group.setObjectName("compareRgbGroup")
        self._rgb_group.setFixedHeight(tool_group_height)
        self._rgb_group.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        rgb_group_lay.setContentsMargins(*tool_group_margins)
        rgb_group_lay.setSpacing(6)
        rgb_group_lay.setAlignment(tool_align)

        self.pixel_inspector_cb = DialogCheckBox("像素 RGB")
        style_dialog_checkbox(self.pixel_inspector_cb, spacing=4)
        self.pixel_inspector_cb.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self.pixel_inspector_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pixel_inspector_cb.setToolTip("放大后显示像素网格与 RGB 标注")
        self.pixel_inspector_cb.toggled.connect(self._on_pixel_inspector_toggled)
        rgb_group_lay.addWidget(self.pixel_inspector_cb, 0, tool_align)

        default_idx = (
            PIXEL_INSPECTOR_SCALE_PRESETS.index(int(PIXEL_INSPECTOR_MIN_SCALE))
            if int(PIXEL_INSPECTOR_MIN_SCALE) in PIXEL_INSPECTOR_SCALE_PRESETS
            else 2
        )
        self.pixel_scale_slider = Slider(Qt.Orientation.Horizontal)
        self.pixel_scale_slider.setRange(0, len(PIXEL_INSPECTOR_SCALE_PRESETS) - 1)
        self.pixel_scale_slider.setValue(default_idx)
        self.pixel_scale_slider.setFixedWidth(112)
        style_compact_dialog_slider(
            self.pixel_scale_slider, handle_size=12, height=DIALOG_TOOLBAR_HEIGHT,
        )
        self.pixel_scale_slider.setToolTip("像素 RGB 出现倍数")
        self.pixel_scale_slider.setVisible(False)
        self.pixel_scale_slider.valueChanged.connect(self._on_pixel_scale_changed)
        rgb_group_lay.addWidget(self.pixel_scale_slider, 0, tool_align)

        from qfluentwidgets.common.font import setFont
        self.pixel_scale_value = QLabel(f"{PIXEL_INSPECTOR_SCALE_PRESETS[default_idx]}×")
        self.pixel_scale_value.setObjectName("compareValueLabel")
        setFont(self.pixel_scale_value, DIALOG_TOOLBAR_FONT)
        self.pixel_scale_value.setFixedSize(32, DIALOG_TOOLBAR_HEIGHT)
        self.pixel_scale_value.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        )
        self.pixel_scale_value.setVisible(False)
        rgb_group_lay.addWidget(self.pixel_scale_value, 0, tool_align)
        self._fit_rgb_group_width()

        bottom.addWidget(analysis_group, 0, Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self._rgb_group, 0, Qt.AlignmentFlag.AlignVCenter)
        bottom.addStretch()
        self._bottom_bar = QWidget()
        self._bottom_bar.setObjectName("compareBottomBar")
        self._bottom_bar.setFixedHeight(28)
        self._bottom_bar.setLayout(bottom)
        layout.addWidget(self._bottom_bar)

        self.canvas.set_pixel_inspector_min_scale(PIXEL_INSPECTOR_SCALE_PRESETS[default_idx])

        self._aux_container = QWidget()
        self._aux_container.setObjectName("compareAuxContainer")
        self._aux_outer = QVBoxLayout(self._aux_container)
        self._aux_outer.setContentsMargins(0, 0, 0, 0)
        self._aux_outer.setSpacing(0)

        self.color_view_panel = ColorViewPanel()
        self.color_view_panel.setObjectName("compareColorPanel")
        self.color_view_panel.setVisible(False)
        self._aux_outer.addWidget(self.color_view_panel)

        self.custom_tool_panel = CustomToolPanel()
        self.custom_tool_panel.setObjectName("compareCustomPanel")
        self.custom_tool_panel.setVisible(False)
        self._aux_outer.addWidget(self.custom_tool_panel)

        self.metrics_panel = MetricsPanel()
        self.metrics_panel.setObjectName("compareMetricsPanel")
        self.metrics_panel.setVisible(False)
        self._aux_outer.addWidget(self.metrics_panel)

        self._aux_row = QWidget()
        self._aux_layout = QHBoxLayout(self._aux_row)
        self._aux_layout.setContentsMargins(8, 6, 8, 6)
        self._aux_layout.setSpacing(6)

        self.pixel_panel = PixelDetailPanel()
        self.pixel_panel.setObjectName("compareAuxPanel")
        self.pixel_panel.setVisible(False)
        self.pixel_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )

        self._aux_sep = QFrame()
        self._aux_sep.setObjectName("compareToolbarSep")
        self._aux_sep.setFrameShape(QFrame.Shape.VLine)
        self._aux_sep.setFixedWidth(1)
        self._aux_sep.setVisible(False)
        self._compare_seps.append(self._aux_sep)

        self.diff_map_panel = DiffMapPanel()
        self.diff_map_panel.setObjectName("compareAuxPanel")
        self.diff_map_panel.setVisible(False)
        self.diff_map_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )

        self._aux_layout.addWidget(self.pixel_panel)
        self._aux_layout.addWidget(self._aux_sep)
        self._aux_layout.addWidget(self.diff_map_panel)
        self._aux_outer.addWidget(self._aux_row)
        layout.addWidget(self._aux_container)

        self._sync_aux_panel_layout()

        self._diff_map_timer = QTimer(self)
        self._diff_map_timer.setSingleShot(True)
        self._diff_map_timer.setInterval(64)
        self._diff_map_timer.timeout.connect(self._update_diff_map)

        self._custom_tools_editor: Optional[CustomToolsEditorDialog] = None

        self.zoom_slider.valueChanged.connect(self._on_zoom_slider)
        reset_btn.clicked.connect(self.canvas.reset_view)
        self.canvas.status_changed.connect(self._set_status_text)
        self.canvas.rgb_copied.connect(self._on_rgb_copied)
        self.canvas.zoom_changed.connect(self._sync_zoom_slider)
        self.canvas.pixel_samples_changed.connect(self.pixel_panel.update_samples)
        self.pixel_panel.copy_settings_changed.connect(self._on_copy_settings_changed)
        self._on_copy_settings_changed()
        self.canvas.slots_content_changed.connect(self._on_slots_content_changed)
        self.diff_map_panel.settings_changed.connect(self._schedule_diff_map_update)
        self.diff_map_panel.export_requested.connect(self._export_diff_map)
        self.color_view_panel.settings_changed.connect(self._on_color_view_settings)
        self.custom_tool_panel.run_requested.connect(lambda: self._run_custom_tool())
        self.custom_tool_panel.revert_requested.connect(self._revert_custom_tool)
        self.custom_tool_panel.manage_requested.connect(self._open_custom_tools_editor)
        self.custom_tool_panel.layout_changed.connect(self._sync_aux_panel_layout)
        self.canvas.active_slot_changed.connect(self.custom_tool_panel.set_target_index)
        self.metrics_panel.settings_changed.connect(self._schedule_metrics_update)
        self.metrics_panel.export_requested.connect(self._export_metrics_table)

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setSingleShot(True)
        self._metrics_timer.setInterval(60)
        self._metrics_timer.timeout.connect(self._start_metrics_worker)
        self._metrics_worker: Optional[MetricsComputeWorker] = None
        self._metrics_generation = 0

        self._sync_custom_tool_slots()
        self._sync_metrics_slots()
        self._sync_grid_spinboxes()
        self._sync_zoom_slider(self.canvas.global_zoom)
        self.apply_theme()
        self.retranslate_ui()

    def _fit_rgb_group_width(self):
        """Size RGB group to content width so slider is not stretched."""
        if not hasattr(self, '_rgb_group'):
            return
        self._rgb_group.adjustSize()
        w = self._rgb_group.sizeHint().width() + 10
        self._rgb_group.setFixedWidth(w)

    def _on_copy_settings_changed(self, *_args):
        if hasattr(self, 'pixel_panel') and hasattr(self, 'canvas'):
            self.canvas.set_copy_enabled(self.pixel_panel.copy_enabled())
            self.canvas.set_copy_format(self.pixel_panel.copy_format())

    def _apply_compare_control_styles(self, colors: Dict[str, str]):
        fg = colors['foreground']
        bg = colors['background']
        border = colors['panel_border']
        spin_ss = (
            f"QSpinBox {{ color: {fg}; background-color: {bg}; "
            f"border: 1px solid {border}; border-radius: 4px; "
            f"font-size: {DIALOG_TOOLBAR_FONT}px; padding-left: 2px; padding-right: 0px; "
            f"selection-background-color: transparent; selection-color: {fg}; }}"
            f"QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; }}"
            f"QSpinBox::up-button {{ subcontrol-position: top right; height: 11px; }}"
            f"QSpinBox::down-button {{ subcontrol-position: bottom right; height: 11px; }}"
            f"QSpinBox QLineEdit {{ background: transparent; border: none; padding: 0 2px; "
            f"selection-background-color: transparent; selection-color: {fg}; }}"
        )
        combo_ss = dialog_combo_stylesheet(colors)
        for w in (self.grid_cols_spin, self.grid_rows_spin):
            w.setStyleSheet(spin_ss)
        self.crop_shape_combo.setStyleSheet(combo_ss)
        fit_dialog_combo_width(
            self.crop_shape_combo,
            [tr(key) for key, _ in CROP_SHAPE_OPTIONS],
        )
        for cb, sp in (
            (self.slot_info_cb, 4),
            (self.histogram_cb, 4),
            (self.eyedropper_cb, 5),
            (self.diff_map_cb, 5),
            (self.color_view_cb, 5),
            (self.custom_tool_cb, 5),
            (self.metrics_cb, 5),
            (self.pixel_inspector_cb, 4),
        ):
            apply_dialog_checkbox_theme(cb, colors, spacing=sp)
            fit_checkbox_width(cb, spacing=sp)
        if hasattr(self, 'pixel_inspector_cb'):
            fit_checkbox_width(self.pixel_inspector_cb, extra=16)
        self._fit_bottom_tool_checkboxes()

    def apply_theme(self, colors: Optional[Dict[str, str]] = None):
        if colors is None:
            colors = get_colors()
        self._colors = colors
        self.setStyleSheet(get_stylesheet())
        bar_ss = (
            f"QWidget#compareToolbar {{ background: {colors['panel_bg']}; "
            f"border-bottom: 1px solid {colors['panel_border']}; }}"
            f"QWidget#compareBottomBar {{ background: {colors['background']}; "
            f"border-top: 1px solid {colors['panel_border']}; "
            f"border-bottom: 1px solid {colors['panel_border']}; }}"
            f"QFrame#compareToolbarSep {{ background: {colors['panel_border']}; "
            f"border: none; max-width: 1px; margin: 0 2px; }}"
            f"QWidget#compareZoomGroup {{ background: {colors['background']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 6px; }}"
            f"QWidget#compareAnalysisGroup, QWidget#compareRgbGroup {{ "
            f"background: {colors['panel_bg']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 6px; }}"
            f"QWidget#compareAuxPanel {{ background: {colors['panel_bg']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 6px; }}"
            f"QWidget#compareColorPanel {{ background: {colors['panel_bg']}; "
            f"border-bottom: 1px solid {colors['panel_border']}; }}"
            f"QWidget#compareMetricsPanel {{ background: {colors['panel_bg']}; "
            f"border-bottom: 1px solid {colors['panel_border']}; }}"
            f"QWidget#compareAuxContainer {{ background: {colors['background']}; }}"
        )
        if hasattr(self, '_toolbar_bar'):
            self._toolbar_bar.setStyleSheet(bar_ss)
        if hasattr(self, '_bottom_bar'):
            self._bottom_bar.setStyleSheet(bar_ss)
        if hasattr(self, 'status_label'):
            from PyQt6.QtGui import QPalette, QColor
            pal = self.status_label.palette()
            pal.setColor(QPalette.ColorRole.Window, QColor(colors['background']))
            pal.setColor(QPalette.ColorRole.WindowText, QColor(colors['text_dim']))
            self.status_label.setPalette(pal)
            self.status_label.setAutoFillBackground(True)
            self.status_label.setStyleSheet(
                f"QLabel#compareStatusStrip {{ background-color: {colors['background']}; "
                f"color: {colors['text_dim']}; border-bottom: 1px solid {colors['panel_border']}; "
                f"padding-left: 12px; font-size: 11px; }}"
            )
        muted = (
            f"color: {colors['text_muted']}; background: transparent; "
            f"font-size: {DIALOG_TOOLBAR_FONT}px;"
        )
        for lbl in self.findChildren(CaptionLabel):
            name = lbl.objectName()
            if name == "compareValueLabel":
                lbl.setStyleSheet(
                    f"color: {colors['foreground']}; background: transparent; "
                    f"font-size: {DIALOG_TOOLBAR_FONT}px;"
                )
            else:
                lbl.setStyleSheet(muted)
        if hasattr(self, 'pixel_scale_value'):
            self.pixel_scale_value.setStyleSheet(
                f"color: {colors['foreground']}; background: transparent; "
                f"font-size: {DIALOG_TOOLBAR_FONT}px; padding: 0px; margin: 0px; border: none;"
            )
        if hasattr(self, 'grid_cols_spin'):
            self._apply_compare_control_styles(colors)
        if hasattr(self, 'canvas'):
            self.canvas.apply_theme(colors)
        if hasattr(self, '_zoom_group'):
            _fit_zoom_group(self)
        if hasattr(self, '_aux_container'):
            self._aux_container.setStyleSheet(bar_ss)
        if hasattr(self, 'pixel_panel'):
            self.pixel_panel.apply_theme(colors)
        if hasattr(self, 'diff_map_panel'):
            self.diff_map_panel.apply_theme(colors)
        if hasattr(self, 'color_view_panel'):
            self.color_view_panel.apply_theme(colors)
        if hasattr(self, 'custom_tool_panel'):
            self.custom_tool_panel.apply_theme(colors)
        if hasattr(self, 'metrics_panel'):
            self.metrics_panel.apply_theme(colors)
        if hasattr(self, '_rgb_group'):
            self._fit_rgb_group_width()
        if hasattr(self, '_status_full_text'):
            self._set_status_text(self._status_full_text)
        self.update()

    def _current_crop_shape(self) -> str:
        if not hasattr(self, 'crop_shape_combo'):
            return 'rect'
        return _crop_shape_from_index(self.crop_shape_combo.currentIndex())

    def _sync_grid_spinboxes(self):
        n = max(1, len(self.canvas.slots))
        cols, rows = self.canvas.get_grid_layout()
        self.grid_cols_spin.blockSignals(True)
        self.grid_rows_spin.blockSignals(True)
        self.grid_cols_spin.setRange(1, max(1, n))
        self.grid_rows_spin.setRange(1, max(1, n))
        self.grid_cols_spin.setValue(cols)
        self.grid_rows_spin.setValue(rows)
        self.grid_cols_spin.blockSignals(False)
        self.grid_rows_spin.blockSignals(False)

    def _on_grid_layout_changed(self, _value: int = 0):
        cols, rows = self.canvas.set_grid_layout(
            self.grid_cols_spin.value(), self.grid_rows_spin.value(),
        )
        if (cols, rows) != (self.grid_cols_spin.value(), self.grid_rows_spin.value()):
            self._sync_grid_spinboxes()

    def _on_grid_layout_auto(self):
        cols, rows = self.canvas.reset_grid_layout()
        self.grid_cols_spin.blockSignals(True)
        self.grid_rows_spin.blockSignals(True)
        self.grid_cols_spin.setValue(cols)
        self.grid_rows_spin.setValue(rows)
        self.grid_cols_spin.blockSignals(False)
        self.grid_rows_spin.blockSignals(False)

    def _on_rgb_copied(self, r: int, g: int, b: int):
        hex_val = f"#{r:02X}{g:02X}{b:02X}"
        if self.canvas.copy_format() == 'hex':
            title, content = tr('color_copied'), hex_val
        else:
            title, content = tr('color_copied'), f"RGB ({r}, {g}, {b})"
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _on_slot_info_toggled(self, checked: bool):
        self.canvas.set_show_slot_overlay(checked)

    def _set_status_text(self, text: str):
        self._status_full_text = text
        zoom = self.canvas.global_zoom if hasattr(self, 'canvas') else 1.0
        display = tr('status_zoom', zoom=zoom)
        if text:
            display += f"  ·  {text}"
        w = max(100, self.status_label.width())
        elided = self.status_label.fontMetrics().elidedText(
            display, Qt.TextElideMode.ElideMiddle, w - 16,
        )
        self.status_label.setText(elided)
        self.status_label.setToolTip(display)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_status_full_text'):
            self._set_status_text(self._status_full_text)

    def _aux_panel_height(self) -> int:
        return max(300, PixelDetailPanel.preferred_height() + 12)

    def _sync_aux_panel_layout(self):
        """Eyedropper, diff map, color, custom, metrics: sensible height when toggled."""
        eyedropper = self.eyedropper_cb.isChecked()
        diff_map = self.diff_map_cb.isChecked()
        color_view = self.color_view_cb.isChecked()
        custom_tool = self.custom_tool_cb.isChecked()
        metrics_on = self.metrics_cb.isChecked()
        both = eyedropper and diff_map
        aux_h = self._aux_panel_height()

        visible = eyedropper or diff_map or color_view or custom_tool or metrics_on
        self._aux_container.setVisible(visible)
        self.color_view_panel.setVisible(color_view)
        self.custom_tool_panel.setVisible(custom_tool)
        self.metrics_panel.setVisible(metrics_on)
        self._aux_row.setVisible(eyedropper or diff_map)
        self.pixel_panel.setVisible(eyedropper)
        self._aux_sep.setVisible(both)
        self.diff_map_panel.setVisible(diff_map)
        self.diff_map_panel.set_compact_layout(both)

        color_h = self.color_view_panel.sizeHint().height() if color_view else 0
        if custom_tool:
            self.custom_tool_panel.sync_tool_display_mode(emit_layout=False)
            if self.custom_tool_panel.wants_result_panel():
                self.custom_tool_panel.set_panel_height(aux_h)
        custom_h = self.custom_tool_panel.panel_height() if custom_tool else 0
        metrics_h = self.metrics_panel.panel_height() if metrics_on else 0
        row_h = aux_h + 12 if (eyedropper or diff_map) else 0

        gap_cc = 4 if color_view and custom_tool else 0
        gap_cm = 4 if color_view and metrics_on else 0
        gap_cr = 4 if color_view and (eyedropper or diff_map) else 0
        gap_custom_row = 4 if custom_tool and (eyedropper or diff_map) else 0
        gap_metrics_row = 4 if metrics_on and (eyedropper or diff_map) else 0

        if visible:
            self._aux_container.setFixedHeight(
                color_h + custom_h + metrics_h + row_h
                + gap_cc + gap_cm + gap_cr + gap_custom_row + gap_metrics_row,
            )
        else:
            self._aux_container.setFixedHeight(0)

        if both:
            self.pixel_panel.set_panel_height(aux_h)
            self.diff_map_panel.set_panel_height(aux_h)
            self.pixel_panel.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
            )
            self.diff_map_panel.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
            )
            self.pixel_panel.setMinimumWidth(0)
            self.diff_map_panel.setMinimumWidth(0)
            self._aux_layout.setStretch(0, 1)
            self._aux_layout.setStretch(1, 0)
            self._aux_layout.setStretch(2, 1)
        elif eyedropper:
            self.pixel_panel.set_panel_height(aux_h)
            self.pixel_panel.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
            )
            self.pixel_panel.setMinimumWidth(0)
            self._aux_layout.setStretch(0, 1)
            self._aux_layout.setStretch(1, 0)
            self._aux_layout.setStretch(2, 0)
        elif diff_map:
            self.diff_map_panel.set_panel_height(aux_h)
            self.diff_map_panel.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
            )
            self.diff_map_panel.setMinimumWidth(0)
            self._aux_layout.setStretch(0, 0)
            self._aux_layout.setStretch(1, 0)
            self._aux_layout.setStretch(2, 1)
        else:
            self._aux_layout.setStretch(0, 0)
            self._aux_layout.setStretch(1, 0)
            self._aux_layout.setStretch(2, 0)

        if eyedropper:
            self.pixel_panel.update_content_width()

    def _sync_metrics_slots(self):
        if not hasattr(self, 'metrics_panel'):
            return
        labels = []
        for i, slot in enumerate(self.canvas.slots):
            folder = self._folder_name_map().get(slot.info.path, '')
            if not folder:
                folder = Path(slot.info.path).parent.name
            labels.append(f'{i + 1}: {folder}')
        self.metrics_panel.set_slot_labels(labels)

    def _folder_labels_for_metrics(self) -> List[str]:
        labels = []
        for slot in self.canvas.slots:
            folder = self._folder_name_map().get(slot.info.path, '')
            if not folder:
                folder = Path(slot.info.path).parent.name
            labels.append(folder)
        return labels

    def _schedule_metrics_update(self):
        if not hasattr(self, 'metrics_cb') or not self.metrics_cb.isChecked():
            return
        self._metrics_timer.start()

    def _start_metrics_worker(self):
        if not hasattr(self, 'metrics_cb') or not self.metrics_cb.isChecked():
            return
        metrics = self.metrics_panel.enabled_metrics()
        baseline = self.metrics_panel.baseline_index()
        if len(self.canvas.slots) < 2 or not metrics:
            self.canvas.set_metrics_overlay(
                True, baseline, {}, metrics, tr('metrics_baseline_tag'),
            )
            self.metrics_panel.set_status('')
            return
        sources = [s.source_array for s in self.canvas.slots]
        if baseline >= len(sources) or sources[baseline] is None:
            self.metrics_panel.set_status(tr('metrics_computing'))
            return
        if self._metrics_worker and self._metrics_worker.isRunning():
            self._metrics_worker.requestInterruption()
            self._metrics_worker.wait(50)
        self._metrics_generation += 1
        gen = self._metrics_generation
        self.metrics_panel.set_status(tr('metrics_computing'))
        worker = MetricsComputeWorker(sources, baseline, metrics, preview=True)
        worker.finished.connect(
            lambda sm, b, m, g=gen: self._on_metrics_computed(g, sm, b, m),
        )
        self._metrics_worker = worker
        worker.start()

    def _on_metrics_computed(
        self,
        generation: int,
        slot_metrics: Dict[int, Dict[str, Optional[float]]],
        baseline: int,
        metrics: List[str],
    ):
        if generation != self._metrics_generation:
            return
        if not self.metrics_cb.isChecked():
            return
        self.canvas.set_metrics_overlay(
            True, baseline, slot_metrics, metrics, tr('metrics_baseline_tag'),
        )
        self.metrics_panel.set_metrics_display(slot_metrics, metrics)

    def _on_metrics_toggled(self, checked: bool):
        self._sync_aux_panel_layout()
        if checked:
            self._sync_metrics_slots()
            self._schedule_metrics_update()
        else:
            self._metrics_timer.stop()
            if self._metrics_worker and self._metrics_worker.isRunning():
                self._metrics_worker.requestInterruption()
            self.canvas.set_metrics_overlay(False, 0, {}, [])
            self.metrics_panel.set_status('')

    def _export_metrics_table(self):
        metrics = self.metrics_panel.enabled_metrics()
        if not metrics:
            QMessageBox.warning(self, tr('tip'), tr('metrics_export_fail'))
            return
        if len(self.canvas.slots) < 2:
            QMessageBox.warning(self, tr('tip'), tr('metrics_need_two'))
            return
        self.raise_()
        self.activateWindow()
        out_dir = QFileDialog.getExistingDirectory(self, tr('select_export_dir'))
        self.raise_()
        self.activateWindow()
        if not out_dir:
            return
        path = str(Path(out_dir) / tr('metrics_export_file'))
        if getattr(self, '_metrics_export_worker', None) and self._metrics_export_worker.isRunning():
            return
        baseline = self.metrics_panel.baseline_index()
        self.metrics_panel.set_export_enabled(False)
        self.metrics_panel.set_status(tr('metrics_exporting'))
        worker = MetricsExportWorker(
            path,
            self.groups,
            baseline,
            metrics,
            self.image_loader,
            self._folder_labels_for_metrics(),
        )
        worker.finished.connect(self._on_metrics_export_finished)
        self._metrics_export_worker = worker
        worker.start()

    def _on_metrics_export_finished(self, count: int, err: object):
        self.metrics_panel.set_export_enabled(True)
        self.metrics_panel.set_status('')
        if err:
            InfoBar.error(
                title=tr('error'),
                content=tr('metrics_export_fail'),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
        else:
            path = getattr(self._metrics_export_worker, '_path', '')
            InfoBar.success(
                title=tr('export_done_title'),
                content=tr('metrics_export_ok', n=count, path=path),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        self.raise_()
        self.activateWindow()
        if self.metrics_cb.isChecked():
            self._schedule_metrics_update()

    def retranslate_ui(self):
        if hasattr(self, 'metrics_panel'):
            self.metrics_panel.retranslate_ui()
        if hasattr(self, 'diff_map_panel'):
            self.diff_map_panel.retranslate_ui()
        for cb, key in (
            (getattr(self, 'metrics_cb', None), 'metrics'),
            (getattr(self, 'slot_info_cb', None), 'info'),
            (getattr(self, 'histogram_cb', None), 'histogram'),
            (getattr(self, 'eyedropper_cb', None), 'eyedropper'),
            (getattr(self, 'diff_map_cb', None), 'diff_map'),
            (getattr(self, 'color_view_cb', None), 'color'),
            (getattr(self, 'custom_tool_cb', None), 'extensions'),
            (getattr(self, 'pixel_inspector_cb', None), 'pixel_rgb'),
        ):
            if cb is not None:
                cb.setText(tr(key))
        if hasattr(self, '_zoom_lbl'):
            self._zoom_lbl.setText(tr('zoom'))
        if hasattr(self, '_cols_lbl'):
            self._cols_lbl.setText(tr('cols'))
        if hasattr(self, '_rows_lbl'):
            self._rows_lbl.setText(tr('rows'))
        if hasattr(self, '_crop_lbl'):
            self._crop_lbl.setText(tr('crop'))
        if hasattr(self, '_reset_view_btn'):
            self._reset_view_btn.setText(tr('reset_view'))
            self._reset_view_btn.setToolTip(tr('reset_view_tip'))
            _style_dialog_button(self._reset_view_btn)
            _fit_zoom_group(self)
        if hasattr(self, '_auto_grid_btn'):
            self._auto_grid_btn.setText(tr('auto_grid'))
            self._auto_grid_btn.setToolTip(tr('auto_grid_tip'))
            _style_dialog_button(self._auto_grid_btn, width=40)
        if hasattr(self, '_export_crop_btn'):
            self._export_crop_btn.setText(tr('export'))
            self._export_crop_btn.setToolTip(tr('export_crop_tip'))
            _style_dialog_button(self._export_crop_btn)
        if hasattr(self, 'slot_info_cb'):
            self.slot_info_cb.setText(tr('info'))
            fit_checkbox_width(self.slot_info_cb, spacing=4, extra=12)
        if hasattr(self, 'histogram_cb'):
            self.histogram_cb.setText(tr('histogram'))
            fit_checkbox_width(self.histogram_cb, spacing=4, extra=12)
        if hasattr(self, 'slot_info_cb'):
            self.slot_info_cb.setToolTip(tr('info_tip'))
        if hasattr(self, 'histogram_cb'):
            self.histogram_cb.setToolTip(tr('histogram_tip'))
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.setToolTip(tr('zoom_slider_tip'))
        if hasattr(self, 'grid_cols_spin'):
            self.grid_cols_spin.setToolTip(tr('grid_cols_tip'))
            self.grid_rows_spin.setToolTip(tr('grid_rows_tip'))
        if hasattr(self, 'eyedropper_cb'):
            self.eyedropper_cb.setToolTip(tr('eyedropper_tip'))
        if hasattr(self, 'diff_map_cb'):
            self.diff_map_cb.setToolTip(tr('diff_map_tip'))
        if hasattr(self, 'color_view_cb'):
            self.color_view_cb.setToolTip(tr('color_view_tip'))
        if hasattr(self, 'custom_tool_cb'):
            self.custom_tool_cb.setToolTip(tr('extensions_tip'))
        if hasattr(self, 'pixel_inspector_cb'):
            self.pixel_inspector_cb.setToolTip(tr('pixel_rgb_tip'))
        if hasattr(self, 'pixel_scale_slider'):
            self.pixel_scale_slider.setToolTip(tr('pixel_scale_tip'))
        if hasattr(self, 'crop_shape_combo'):
            idx = self.crop_shape_combo.currentIndex()
            self.crop_shape_combo.setToolTip(tr('crop_region_required'))
            self.crop_shape_combo.blockSignals(True)
            self.crop_shape_combo.clear()
            for key, _ in CROP_SHAPE_OPTIONS:
                self.crop_shape_combo.addItem(tr(key))
            if 0 <= idx < len(CROP_SHAPE_OPTIONS):
                self.crop_shape_combo.setCurrentIndex(idx)
            self.crop_shape_combo.blockSignals(False)
            fit_dialog_combo_width(
                self.crop_shape_combo,
                [tr(key) for key, _ in CROP_SHAPE_OPTIONS],
            )
        if hasattr(self, 'metrics_cb') and self.metrics_cb.isChecked():
            self._schedule_metrics_update()
        self._fit_bottom_tool_checkboxes()
        if hasattr(self, 'color_view_panel'):
            self.color_view_panel.retranslate_ui()
        if hasattr(self, 'custom_tool_panel'):
            self.custom_tool_panel.retranslate_ui()
        if hasattr(self, 'pixel_panel'):
            self.pixel_panel.retranslate_ui()
        if hasattr(self, '_status_full_text'):
            self._set_status_text(self._status_full_text)

    def _fit_bottom_tool_checkboxes(self):
        for cb in (
            getattr(self, 'eyedropper_cb', None),
            getattr(self, 'diff_map_cb', None),
            getattr(self, 'color_view_cb', None),
            getattr(self, 'custom_tool_cb', None),
            getattr(self, 'metrics_cb', None),
            getattr(self, 'pixel_inspector_cb', None),
        ):
            if cb is not None:
                sp = 4 if cb is getattr(self, 'pixel_inspector_cb', None) else 5
                fit_checkbox_width(cb, spacing=sp, extra=12)

    def _sync_custom_tool_slots(self):
        if not hasattr(self, 'custom_tool_panel'):
            return
        labels = []
        for i, slot in enumerate(self.canvas.slots):
            name = slot.info.name if slot.info else tr('slot_label', n=i + 1)
            labels.append(f'{i + 1}: {name}')
        self.custom_tool_panel.set_slot_count(len(self.canvas.slots), labels)

    def _on_slots_content_changed(self):
        self._sync_grid_spinboxes()
        if self._column_remove_in_progress:
            return
        if self.diff_map_panel.isVisible():
            self.diff_map_panel.set_slot_count(len(self.canvas.slots))
            self._schedule_diff_map_update()
        self._sync_custom_tool_slots()
        self._sync_metrics_slots()
        if hasattr(self, 'metrics_cb') and self.metrics_cb.isChecked():
            self._schedule_metrics_update()

    def _schedule_diff_map_update(self):
        self._diff_map_timer.start()

    def _update_diff_map(self):
        if not self.diff_map_panel.isVisible():
            return
        if len(self.canvas.slots) < 2:
            self.diff_map_panel.apply_result(None)
            return
        ref_i = self.diff_map_panel.ref_index()
        cmp_i = self.diff_map_panel.cmp_index()
        if ref_i == cmp_i:
            self.diff_map_panel.show_message(tr('diff_select_two'))
            return
        arr1 = self.canvas.slots[ref_i].array
        arr2 = self.canvas.slots[cmp_i].array
        if arr1 is None or arr2 is None:
            self.diff_map_panel.apply_result(None)
            return
        result = compute_diff_map(
            arr1, arr2,
            method=self.diff_map_panel.method(),
            sensitivity=self.diff_map_panel.sensitivity(),
        )
        self.diff_map_panel.apply_result(result)

    def showEvent(self, event):
        super().showEvent(event)
        schedule_macos_native_fullscreen_button(self)
        self.raise_()
        self.activateWindow()
        self.canvas.setFocus()

    def reject(self):
        super().reject()

    def closeEvent(self, event):
        super().closeEvent(event)

    def _sync_zoom_slider(self, zoom: float):
        max_z = self.canvas._max_zoom_limit()
        pos = zoom_to_slider_pos(zoom, max_z)
        self.zoom_slider.setRange(0, ZOOM_SLIDER_STEPS)
        sync_fluent_slider(self.zoom_slider, pos)
        pct = int(zoom * 100)
        hi_pct = int(zoom_slider_hi(max_z) * 100)
        if zoom > zoom_slider_hi(max_z) + 0.001:
            self.zoom_slider.setToolTip(
                tr('zoom_status_over', pct=pct, hi=hi_pct),
            )
        else:
            self.zoom_slider.setToolTip(
                tr(
                    'zoom_status_log',
                    pct=pct,
                    lo=int(MIN_ZOOM * 100),
                    hi=hi_pct,
                ),
            )
        if hasattr(self, '_status_full_text'):
            self._set_status_text(self._status_full_text)

    def _on_zoom_slider(self, value: int):
        max_z = self.canvas._max_zoom_limit()
        zoom = slider_pos_to_zoom(value, max_z)
        self.canvas._zoom_at(self.canvas.rect().center(), min(zoom, max_z))

    def _folder_name_map(self) -> Dict[str, str]:
        mapping = {}
        for folder in self.folder_manager.folders:
            for img in folder.images:
                mapping[img.path] = folder.name
        return mapping

    @staticmethod
    def _safe_filename_part(text: str) -> str:
        cleaned = re.sub(r'[/\\:*?"<>|]', '_', text.strip())
        return cleaned or "unnamed"

    def _default_diff_map_filename(self) -> str:
        ref_i = self.diff_map_panel.ref_index()
        cmp_i = self.diff_map_panel.cmp_index()
        ref_info = self.canvas.slots[ref_i].info
        cmp_info = self.canvas.slots[cmp_i].info
        folder_map = self._folder_name_map()
        ref_folder = self._safe_filename_part(folder_map.get(ref_info.path, "folder"))
        cmp_folder = self._safe_filename_part(folder_map.get(cmp_info.path, "folder"))
        ref_stem = self._safe_filename_part(Path(ref_info.path).stem)
        cmp_stem = self._safe_filename_part(Path(cmp_info.path).stem)
        if ref_folder == cmp_folder:
            return f"{ref_folder}_{ref_stem}_vs_{cmp_stem}_diff.png"
        if ref_stem == cmp_stem:
            return f"{ref_folder}_vs_{cmp_folder}_{ref_stem}_diff.png"
        return f"{ref_folder}_{ref_stem}_vs_{cmp_folder}_{cmp_stem}_diff.png"

    def _export_diff_map(self):
        if not self.diff_map_panel.has_heatmap():
            QMessageBox.information(self, tr('tip'), tr('diff_no_heatmap'))
            return
        out_dir = QFileDialog.getExistingDirectory(self, tr('select_export_dir'))
        if not out_dir:
            return
        heatmap = self.diff_map_panel.get_heatmap_bgr()
        if heatmap is None:
            QMessageBox.warning(self, tr('error'), tr('diff_data_unavailable'))
            return
        path = Path(out_dir) / self._default_diff_map_filename()
        if not cv2.imwrite(str(path), heatmap):
            QMessageBox.warning(self, tr('error'), tr('diff_write_failed', path=path))
            return
        QMessageBox.information(self, tr('export_done_title'), tr('diff_export_ok', path=out_dir))
        self.raise_()
        self.activateWindow()

    def _on_crop_shape_changed(self):
        if not hasattr(self, 'canvas'):
            return
        self.canvas.set_crop_shape(self._current_crop_shape())

    def _export_crop(self):
        region = self.canvas.get_crop_region()
        if not region:
            QMessageBox.information(self, tr('tip'), tr('crop_region_required'))
            return
        out_dir = QFileDialog.getExistingDirectory(self, tr('select_export_dir'))
        if not out_dir:
            return
        images = self.canvas.get_export_images()
        is_multi = self.folder_manager.mode == 'multi' and self.folder_manager.get_folder_count() > 1
        count = ComparisonTools.export_crops(
            images, region, out_dir, is_multi, self._folder_name_map()
        )
        QMessageBox.information(self, tr('export_done_title'), tr('export_crop_ok', n=count, path=out_dir))
        self.raise_()
        self.activateWindow()

    def _on_histogram_toggled(self, checked: bool):
        self.canvas.set_show_histogram(checked)

    def _toggle_histogram(self):
        self.histogram_cb.setChecked(not self.histogram_cb.isChecked())

    def _on_eyedropper_toggled(self, checked: bool):
        self.canvas.set_eyedropper(checked)
        self.pixel_panel.set_eyedropper_active(checked)
        self._sync_aux_panel_layout()
        if checked:
            self.pixel_panel.set_slot_count(len(self.canvas.slots))
            if self.canvas.slots and self.canvas.slots[0].array is not None:
                ih, iw = self.canvas.slots[0].array.shape[:2]
                self.canvas._sample_x = iw // 2
                self.canvas._sample_y = ih // 2
                self.pixel_panel.update_samples(self.canvas.collect_pixel_samples())
            else:
                self.pixel_panel.update_content_width()
            self.canvas.update()

    def _on_diff_map_toggled(self, checked: bool):
        self._sync_aux_panel_layout()
        if checked:
            self.diff_map_panel.set_slot_count(len(self.canvas.slots))
            self._update_diff_map()

    def _on_color_view_toggled(self, checked: bool):
        self._sync_aux_panel_layout()
        if checked and self.color_view_panel.params() != self.canvas.color_view_params:
            self._on_color_view_settings(self.color_view_panel.params())

    def _on_color_view_settings(self, params: ColorViewParams):
        if params == self.canvas.color_view_params:
            return
        self.canvas.set_color_view_params(params)
        if self.diff_map_panel.isVisible():
            self._schedule_diff_map_update()

    def _on_custom_tool_toggled(self, checked: bool):
        self._sync_aux_panel_layout()
        if checked:
            self._sync_custom_tool_slots()
            self.custom_tool_panel.reload_tools()

    def _open_custom_tools_editor(self):
        if self._custom_tools_editor is None:
            dlg = CustomToolsEditorDialog(self)
            dlg.tools_changed.connect(self._on_custom_tools_changed)
            self._custom_tools_editor = dlg
        self._custom_tools_editor.show()
        self._custom_tools_editor.raise_()
        self._custom_tools_editor.activateWindow()

    def _on_custom_tools_changed(self, state):
        self.custom_tool_panel.reload_tools(state)
        self._sync_aux_panel_layout()

    def _populate_custom_tool_menu(self, menu: QMenu, slot_index: int):
        state = load_custom_tools()
        if not state.tools:
            return
        menu.addSeparator()
        sub = menu.addMenu(tr('extensions_menu'))
        sub.setStyleSheet(_compare_menu_style(get_colors()))
        for tool in state.tools:
            sub.addAction(
                tool.name,
                lambda tid=tool.id, si=slot_index: self._run_custom_tool(
                    tool_id=tid, slot_index=si, from_menu=True,
                ),
            )
        if self.canvas._custom_tool_modified:
            sub.addSeparator()
            sub.addAction(
                tr('extensions_revert'),
                lambda si=slot_index: self._revert_custom_tool(si),
            )

    def _revert_custom_tool(self, slot_index: Optional[int] = None):
        if self.canvas.revert_custom_tool_views(slot_index):
            self._set_status_text(tr('extensions_reverted'))
        else:
            self._set_status_text(tr('extensions_no_revert'))

    def _run_custom_tool(
        self,
        tool_id: Optional[str] = None,
        slot_index: Optional[int] = None,
        from_menu: bool = False,
    ):
        if not from_menu and not self.custom_tool_cb.isChecked():
            return
        if tool_id:
            self.custom_tool_panel.select_tool_by_id(tool_id)
        if slot_index is not None:
            self.custom_tool_panel.set_target_index(slot_index)
        elif not self.custom_tool_panel.wants_slot_picker():
            self.custom_tool_panel.set_target_index(self.canvas._active_slot_index)

        tool = self.custom_tool_panel.current_tool()
        if tool is None:
            msg = tr('extensions_no_tool')
            if self.custom_tool_panel.wants_result_panel():
                self.custom_tool_panel.show_error(msg)
            else:
                self._set_status_text(msg)
            return
        show_panel = tool.show_result_panel
        target = self.custom_tool_panel.target_index()
        try:
            result = run_custom_tool(
                tool.id,
                tool.code,
                self.canvas,
                target_index=target,
                ref_index=self.custom_tool_panel.ref_index(),
                cmp_index=self.custom_tool_panel.cmp_index(),
            )
            message = self.custom_tool_panel.result_message(result)
            if message:
                self._set_status_text(message)
            if not show_panel:
                apply_slot = result.get('apply_slot')
                if apply_slot is not None and result.get('image') is not None:
                    self.canvas.apply_custom_tool_view(apply_slot, result['image'])
                elif result.get('image') is not None and apply_slot is None:
                    self.canvas.apply_custom_tool_view(target, result['image'])
            if show_panel and not self.custom_tool_cb.isChecked():
                self.custom_tool_cb.setChecked(True)
            self.custom_tool_panel.apply_result(result, show_panel=show_panel)
        except Exception as exc:
            logger.exception('自定义工具运行失败')
            err = tr('extensions_run_fail', exc=exc)
            if show_panel:
                self.custom_tool_panel.show_error(err)
            else:
                self._set_status_text(err)

    def _on_pixel_inspector_toggled(self, checked: bool):
        self.canvas.set_pixel_inspector(checked)
        self.pixel_scale_slider.setVisible(checked)
        self.pixel_scale_value.setVisible(checked)
        self.pixel_scale_slider.setEnabled(checked)
        self._fit_rgb_group_width()
        if checked:
            self._on_pixel_scale_changed(self.pixel_scale_slider.value())

    def _on_pixel_scale_changed(self, index: int):
        index = max(0, min(index, len(PIXEL_INSPECTOR_SCALE_PRESETS) - 1))
        scale = PIXEL_INSPECTOR_SCALE_PRESETS[index]
        self.pixel_scale_value.setText(f"{scale}×")
        self.canvas.set_pixel_inspector_min_scale(scale)

    def _open_pixel_diff(self):
        from ui.pixel_diff_dialog import PixelDiffDialog
        dlg = PixelDiffDialog(self.canvas.get_export_images(), self.image_loader, self)
        dlg.show()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self._on_escape_pressed()
            event.accept()
            return
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_B):
            if self._group_navigator:
                delta = 1 if key == Qt.Key.Key_Space else -1
                self._group_navigator(delta)
            event.accept()
            return
        if key == Qt.Key.Key_P:
            self._open_pixel_diff()
        elif key == Qt.Key.Key_H:
            self._toggle_histogram()
        elif key == Qt.Key.Key_Backspace:
            self.remove_folder_column_at_cursor()
            event.accept()
            return
        else:
            self.canvas.keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        self.canvas.keyReleaseEvent(event)
