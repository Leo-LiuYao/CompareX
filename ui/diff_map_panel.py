"""Compare window - difference map panel."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
)
from qfluentwidgets import PushButton, Slider, ComboBox
from ui.fluent_integration import (
    style_compact_button, style_compact_input, sync_fluent_slider,
    dialog_combo_stylesheet, fit_dialog_combo_width, style_dialog_combo,
    style_compact_dialog_slider, dialog_toolbar_button_stylesheet,
    DIALOG_TOOLBAR_HEIGHT, DIALOG_TOOLBAR_FONT,
)
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPixmap, QImage, QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from typing import List, Optional, Dict
import numpy as np
import cv2

from utils.image_utils import DIFF_METHODS
from i18n import tr
from ui.theme import get_colors


def _diff_method_label(key: str) -> str:
    return tr(f'diff_method_{key}')


class DiffHeatmapView(QWidget):
    """Diff heatmap + colorbar on the right."""

    BAR_W = 22
    BAR_GAP = 10
    MARGIN = 8

    def __init__(self):
        super().__init__()
        self._source: Optional[QPixmap] = None
        self._max_val = 1.0
        self._placeholder = tr('diff_select_two')
        self._colors = get_colors()
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self.update()

    def set_heatmap(self, result: Optional[Dict]):
        if not result or result.get("heatmap_rgb") is None:
            self._source = None
            self._max_val = 1.0
            self.update()
            return
        heatmap = result["heatmap_rgb"]
        h, w = heatmap.shape[:2]
        qimg = QImage(heatmap.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        self._source = QPixmap.fromImage(qimg)
        self._max_val = float(result.get("max_diff", 1.0))
        self.update()

    def clear(self, message: str = ''):
        self._source = None
        self._placeholder = message or tr('diff_select_two')
        self.update()

    @staticmethod
    def _jet_color(t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        sample = np.array([[[int(t * 255)]]], dtype=np.uint8)
        bgr = cv2.applyColorMap(sample, cv2.COLORMAP_JET)[0, 0]
        return QColor(int(bgr[2]), int(bgr[1]), int(bgr[0]))

    def _content_rect(self) -> tuple:
        total = self.rect()
        bar_total = self.BAR_W + self.BAR_GAP + 36
        inner = total.adjusted(self.MARGIN, self.MARGIN, -self.MARGIN - bar_total, -self.MARGIN)
        return inner, total.width() - self.MARGIN - bar_total

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = self._colors
        dark = c.get('canvas_bg', '').lower() in ('#1a1a1a', '#1a1a1aff')
        bg_key = 'panel_bg' if not dark else 'canvas_bg'
        painter.fillRect(self.rect(), QColor(c[bg_key]))

        content, bar_x = self._content_rect()
        painter.setPen(QPen(QColor(c['panel_border']), 1))
        painter.drawRect(content)

        if self._source is None or self._source.isNull():
            painter.setPen(QColor(c['text_dim']))
            font = QFont()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(content, Qt.AlignmentFlag.AlignCenter, self._placeholder)
            self._draw_colorbar(painter, bar_x, content.top(), content.height(), active=False)
            return

        scaled = self._source.scaled(
            content.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        dx = content.x() + (content.width() - scaled.width()) // 2
        dy = content.y() + (content.height() - scaled.height()) // 2
        painter.drawPixmap(dx, dy, scaled)

        bar_y = content.y()
        bar_h = content.height()
        self._draw_colorbar(painter, bar_x, bar_y, bar_h, active=True)

    def _draw_colorbar(self, painter: QPainter, x: int, y: int, h: int, active: bool):
        bar = QRectF(x, y, self.BAR_W, h)
        painter.setPen(QPen(QColor(self._colors['panel_border']), 1))
        painter.drawRect(bar)

        if not active or h <= 4:
            return

        inner = bar.adjusted(1, 1, -1, -1)
        for i in range(int(inner.height())):
            t = 1.0 - i / max(1, inner.height() - 1)
            painter.setPen(self._jet_color(t))
            painter.drawLine(
                int(inner.left()), int(inner.top() + i),
                int(inner.right()), int(inner.top() + i),
            )

        painter.setPen(QColor(self._colors['text_muted']))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        label_x = int(bar.right()) + 4
        painter.drawText(label_x, int(bar.top()) + 10, f"{self._max_val:.0f}")
        painter.drawText(label_x, int(bar.top() + bar.height() * 0.5), f"{self._max_val * 0.5:.0f}")
        painter.drawText(label_x, int(bar.bottom()), "0")


class DiffMapPanel(QWidget):
    """Diff heatmap panel with slot and method selectors."""

    settings_changed = pyqtSignal()
    export_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._colors = get_colors()
        self._compact_ctrl = False
        self._heatmap_bgr = None
        self._muted_labels: List[QLabel] = []
        self._last_result: Optional[Dict] = None
        self._slot_count = 0
        self._ref_lbl = None
        self._cmp_lbl = None
        self._method_lbl = None
        self._sens_lbl = None
        self._method_keys = [key for key, _ in DIFF_METHODS]

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)

        self._ctrl_bar = QWidget()
        self._ctrl_bar.setMinimumHeight(DIALOG_TOOLBAR_HEIGHT + 2)
        ctrl = QHBoxLayout(self._ctrl_bar)
        ctrl.setContentsMargins(0, 0, 0, 0)
        ctrl.setSpacing(5)

        self.ref_combo = ComboBox()
        _style_combo(self.ref_combo)
        self.ref_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.ref_combo.currentIndexChanged.connect(self._emit_settings)

        self.cmp_combo = ComboBox()
        _style_combo(self.cmp_combo)
        self.cmp_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.cmp_combo.currentIndexChanged.connect(self._emit_settings)

        self.method_combo = ComboBox()
        _style_combo(self.method_combo)
        self.method_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        for key in self._method_keys:
            self.method_combo.addItem(_diff_method_label(key))
        self.method_combo.currentIndexChanged.connect(self._emit_settings)

        self.sens_slider = Slider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(1, 100)
        self.sens_slider.setValue(50)
        self.sens_slider.setFixedWidth(96)
        style_compact_dialog_slider(
            self.sens_slider, handle_size=14, height=DIALOG_TOOLBAR_HEIGHT,
        )
        self.sens_slider.valueChanged.connect(self._emit_settings)

        ref_pair, self._ref_lbl = self._ctrl_pair('', self.ref_combo, spacing=2, compact=True)
        cmp_pair, self._cmp_lbl = self._ctrl_pair('', self.cmp_combo, spacing=2, compact=True)
        method_pair, self._method_lbl = self._ctrl_pair('', self.method_combo, spacing=2, compact=True)
        sens_pair, self._sens_lbl = self._ctrl_pair('', self.sens_slider, spacing=2, compact=True)
        ctrl.addWidget(ref_pair)
        ctrl.addWidget(cmp_pair)
        ctrl.addWidget(method_pair)
        ctrl.addWidget(sens_pair)
        ctrl.addStretch()

        self.export_btn = PushButton()
        style_compact_button(
            self.export_btn, height=DIALOG_TOOLBAR_HEIGHT, font_size=DIALOG_TOOLBAR_FONT,
        )
        from qfluentwidgets.common.font import getFont
        _btn_fm = QFontMetrics(getFont(DIALOG_TOOLBAR_FONT))
        self.export_btn.setFixedWidth(
            max(_btn_fm.horizontalAdvance(tr('export')) + 18, self.export_btn.sizeHint().width())
        )
        self.export_btn.setEnabled(False)
        self.export_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.export_btn.clicked.connect(self.export_requested.emit)
        ctrl.addWidget(self.export_btn)

        root.addWidget(self._ctrl_bar)

        self.heatmap_view = DiffHeatmapView()
        root.addWidget(self.heatmap_view, stretch=1)

        self.stats_label = QLabel("")
        root.addWidget(self.stats_label)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_theme(self._colors)
        self.retranslate_ui()

    def retranslate_ui(self):
        if self._ref_lbl is not None:
            self._ref_lbl.setText(tr('diff_ref'))
        if self._cmp_lbl is not None:
            self._cmp_lbl.setText(tr('diff_cmp'))
        if self._method_lbl is not None:
            self._method_lbl.setText(tr('diff_method_lbl'))
        if self._sens_lbl is not None:
            self._sens_lbl.setText(tr('diff_sensitivity'))
        self.export_btn.setText(tr('export'))
        from qfluentwidgets.common.font import getFont
        _btn_fm = QFontMetrics(getFont(DIALOG_TOOLBAR_FONT))
        self.export_btn.setFixedWidth(
            max(_btn_fm.horizontalAdvance(tr('export')) + 18, self.export_btn.sizeHint().width())
        )
        idx = self.method_combo.currentIndex()
        self.method_combo.blockSignals(True)
        self.method_combo.clear()
        for key in self._method_keys:
            self.method_combo.addItem(_diff_method_label(key))
        if 0 <= idx < len(self._method_keys):
            self.method_combo.setCurrentIndex(idx)
        self.method_combo.blockSignals(False)
        self._sync_method_combo_width()
        if self._slot_count:
            self.set_slot_count(self._slot_count)
        elif self._last_result is None and self._heatmap_bgr is None:
            self.heatmap_view.clear()
        self._update_stats_text()

    def minimumSizeHint(self):
        from PyQt6.QtCore import QSize
        h = self.height() if self.height() > 0 else 200
        return QSize(0, h)

    def minimumSize(self):
        from PyQt6.QtCore import QSize
        return QSize(0, super().minimumSize().height())

    def _ctrl_pair(
        self, label_text: str, widget: QWidget, *, spacing: int = 3, compact: bool = False,
    ) -> tuple:
        pair = QWidget()
        if compact:
            pair.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(pair)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)
        lbl = self._muted_label(label_text)
        lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        if compact:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        return pair, lbl

    def _zone_combo_text_width(self, text: str = '') -> int:
        from qfluentwidgets.common.font import getFont
        fm = QFontMetrics(getFont(DIALOG_TOOLBAR_FONT))
        sample = text or tr('compare_tab_slot_n', n=12)
        return max(46, fm.horizontalAdvance(sample) + 32)

    def _sync_zone_combo_widths(
        self, *, extra: int = None, min_width: int = None,
    ):
        slot_sample = tr('compare_tab_slot_n', n=12)
        texts = [self.ref_combo.currentText(), self.cmp_combo.currentText(), slot_sample]
        texts = [t for t in texts if t]
        pad_left = 4 if self._compact_ctrl else 6
        pad_right = 24 if self._compact_ctrl else 28
        if extra is None:
            extra = pad_left + pad_right + 4
        if min_width is None:
            min_width = 46 if self._compact_ctrl else 50
        for combo in (self.ref_combo, self.cmp_combo):
            fit_dialog_combo_width(
                combo, texts or [slot_sample], extra=extra, min_width=min_width,
            )

    def _sync_method_combo_width(self):
        labels = [_diff_method_label(key) for key in self._method_keys]
        pad_left = 4 if self._compact_ctrl else 6
        pad_right = 24 if self._compact_ctrl else 28
        fit_dialog_combo_width(
            self.method_combo, labels,
            extra=pad_left + pad_right + 4,
            min_width=46 if self._compact_ctrl else 50,
        )

    def _muted_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        self._muted_labels.append(lbl)
        return lbl

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self.setStyleSheet(
            f"QWidget#compareAuxPanel {{ background: {colors['panel_bg']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 6px; }}"
        )
        muted_style = (
            f"color: {colors['text_muted']}; font-size: {DIALOG_TOOLBAR_FONT}px; "
            f"background: transparent;"
        )
        for lbl in self._muted_labels:
            lbl.setStyleSheet(muted_style)
        self.stats_label.setStyleSheet(
            f"color: {colors['text_muted']}; font-size: {DIALOG_TOOLBAR_FONT}px; "
            f"background: transparent;"
        )
        pad_left = 4 if self._compact_ctrl else 6
        pad_right = 24 if self._compact_ctrl else 28
        zone_combo_ss = dialog_combo_stylesheet(
            colors, padding_left=pad_left, padding_right=pad_right,
        )
        self._sync_zone_combo_widths()
        self._sync_method_combo_width()
        self.ref_combo.setStyleSheet(zone_combo_ss)
        self.cmp_combo.setStyleSheet(zone_combo_ss)
        self.method_combo.setStyleSheet(
            dialog_combo_stylesheet(colors, padding_left=pad_left, padding_right=pad_right),
        )
        self.export_btn.setStyleSheet(dialog_toolbar_button_stylesheet(colors))
        sync_fluent_slider(self.sens_slider, self.sens_slider.value())
        self.heatmap_view.apply_theme(colors)

    def _emit_settings(self):
        self.settings_changed.emit()

    def set_panel_height(self, height: int):
        """Match eyedropper panel height; heatmap fills remaining space."""
        self.setFixedHeight(height)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        margins = 6 + 4 + 6 + 4
        ctrl_h = self._ctrl_bar.minimumHeight()
        stats_h = 18
        avail = max(80, height - margins - ctrl_h - stats_h)
        self.heatmap_view.setMinimumHeight(avail)
        self.heatmap_view.setMaximumHeight(avail)

    def set_compact_layout(self, compact: bool):
        """Tighten controls when eyedropper + diff map side by side."""
        if self._compact_ctrl == compact:
            return
        self._compact_ctrl = compact
        self.apply_theme(self._colors)

    def set_slot_count(self, count: int):
        self._slot_count = count
        labels = [tr('compare_tab_slot_n', n=i + 1) for i in range(count)]
        ref_idx = self.ref_combo.currentIndex()
        cmp_idx = self.cmp_combo.currentIndex()
        self.ref_combo.blockSignals(True)
        self.cmp_combo.blockSignals(True)
        self.ref_combo.clear()
        self.cmp_combo.clear()
        for text in labels:
            self.ref_combo.addItem(text)
            self.cmp_combo.addItem(text)
        if count >= 2:
            self.ref_combo.setCurrentIndex(min(max(0, ref_idx), count - 1))
            self.cmp_combo.setCurrentIndex(min(max(1, cmp_idx), count - 1))
        self.ref_combo.blockSignals(False)
        self.cmp_combo.blockSignals(False)
        self._sync_zone_combo_widths()

    def remove_slot_at(self, removed_index: int):
        """After column removal, shift ref/cmp indices to preserve selection."""
        old_count = self.ref_combo.count()
        if old_count <= 1 or removed_index < 0 or removed_index >= old_count:
            self.set_slot_count(max(0, old_count - 1))
            return

        ref_idx = self.ref_combo.currentIndex()
        cmp_idx = self.cmp_combo.currentIndex()
        new_count = old_count - 1

        def shift(idx: int) -> int:
            if idx == removed_index:
                return max(0, min(removed_index, new_count - 1))
            if idx > removed_index:
                return idx - 1
            return idx

        new_ref = shift(ref_idx)
        new_cmp = shift(cmp_idx)
        if new_count >= 2 and new_ref == new_cmp:
            new_cmp = (new_ref + 1) % new_count

        labels = [tr('compare_tab_slot_n', n=i + 1) for i in range(new_count)]
        self.ref_combo.blockSignals(True)
        self.cmp_combo.blockSignals(True)
        self.ref_combo.clear()
        self.cmp_combo.clear()
        for text in labels:
            self.ref_combo.addItem(text)
            self.cmp_combo.addItem(text)
        if new_count >= 2:
            self.ref_combo.setCurrentIndex(new_ref)
            self.cmp_combo.setCurrentIndex(new_cmp)
        self.ref_combo.blockSignals(False)
        self.cmp_combo.blockSignals(False)
        self._sync_zone_combo_widths()

    def ref_index(self) -> int:
        return max(0, self.ref_combo.currentIndex())

    def cmp_index(self) -> int:
        return max(0, self.cmp_combo.currentIndex())

    def method(self) -> str:
        idx = self.method_combo.currentIndex()
        if 0 <= idx < len(self._method_keys):
            return self._method_keys[idx]
        return 'euclidean'

    def sensitivity(self) -> float:
        return self.sens_slider.value() / 100.0

    def _update_stats_text(self):
        if not self._last_result:
            return
        r = self._last_result
        w_img, h_img = r.get('size', (0, 0))
        self.stats_label.setText(
            tr(
                'diff_stats',
                mean=r['mean_diff'],
                max=r['max_diff'],
                std=r['std_diff'],
                pct=r['diff_pct'],
                w=w_img,
                h=h_img,
            ),
        )

    def apply_result(self, result: Optional[Dict]):
        if not result:
            self._last_result = None
            self.heatmap_view.clear(tr('diff_cannot_compute'))
            self.stats_label.setText("")
            self._heatmap_bgr = None
            self.export_btn.setEnabled(False)
            return

        heatmap = result.get('heatmap_rgb')
        if heatmap is None:
            self._last_result = None
            self.heatmap_view.clear(tr('diff_compute_failed'))
            self.stats_label.setText("")
            self._heatmap_bgr = None
            self.export_btn.setEnabled(False)
            return

        self._last_result = result
        self._heatmap_bgr = result.get('heatmap_bgr')
        self.heatmap_view.set_heatmap(result)
        self.export_btn.setEnabled(True)
        self._update_stats_text()

    def show_message(self, message: str):
        self._last_result = None
        self.heatmap_view.clear(message)
        self.stats_label.setText("")
        self._heatmap_bgr = None
        self.export_btn.setEnabled(False)

    def has_heatmap(self) -> bool:
        return self._heatmap_bgr is not None

    def get_heatmap_bgr(self):
        return self._heatmap_bgr


def _style_combo(combo: ComboBox):
    style_dialog_combo(combo)
