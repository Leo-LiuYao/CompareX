"""Compare window - image quality metrics panel."""
from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from qfluentwidgets import PushButton, ComboBox

from i18n import tr
from ui.fluent_integration import (
    style_compact_button, dialog_combo_stylesheet,
    apply_dialog_checkbox_theme, DialogCheckBox, fit_checkbox_width,
    fit_compact_button_width, style_baseline_combo, style_dialog_combo,
    style_dialog_checkbox, fit_dialog_toolbar_button,
    DIALOG_TOOLBAR_HEIGHT, DIALOG_TOOLBAR_FONT,
)
from ui.theme import get_colors
from utils.image_metrics import format_metric_value

_BASELINE_CLOSED_WIDTH = 132
_TOOL_CB_SPACING = 5
_TOOL_CB_EXTRA = 12
_STATUS_COL_SPACING = 8
_COMPACT_H = DIALOG_TOOLBAR_HEIGHT + 12
_VALUE_LINE_H = 12


class MetricsPanel(QWidget):
    settings_changed = pyqtSignal()
    export_requested = pyqtSignal()

    @classmethod
    def panel_height(cls) -> int:
        return _COMPACT_H

    def __init__(self):
        super().__init__()
        self._colors = get_colors()
        self._slot_labels: List[str] = []
        self._metric_labels: List[QLabel] = []

        self._ctrl_bar = QWidget()
        self._ctrl_bar.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        root = QHBoxLayout(self._ctrl_bar)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._baseline_lbl = QLabel()
        self._baseline_lbl.setObjectName('compareMutedLabel')
        self._baseline_lbl.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._baseline_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self.baseline_combo = ComboBox()
        style_dialog_combo(self.baseline_combo)
        self.baseline_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.baseline_combo.currentIndexChanged.connect(self._emit_settings)
        root.addWidget(self.baseline_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        metric_checks = QWidget()
        metric_checks.setStyleSheet('background: transparent;')
        metric_checks.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        checks_lay = QHBoxLayout(metric_checks)
        checks_lay.setContentsMargins(0, 0, 0, 0)
        checks_lay.setSpacing(10)

        self.psnr_cb = DialogCheckBox()
        style_dialog_checkbox(self.psnr_cb, spacing=_TOOL_CB_SPACING)
        self.psnr_cb.setChecked(True)
        self.psnr_cb.toggled.connect(self._emit_settings)
        checks_lay.addWidget(self.psnr_cb)

        self.ssim_cb = DialogCheckBox()
        style_dialog_checkbox(self.ssim_cb, spacing=_TOOL_CB_SPACING)
        self.ssim_cb.setChecked(True)
        self.ssim_cb.toggled.connect(self._emit_settings)
        checks_lay.addWidget(self.ssim_cb)
        root.addWidget(metric_checks, 0, Qt.AlignmentFlag.AlignVCenter)

        root.addStretch(1)

        self._status_host = QWidget()
        self._status_host.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self._status_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._status_host.setStyleSheet('background: transparent;')
        self._status_lay = QHBoxLayout(self._status_host)
        self._status_lay.setContentsMargins(0, 0, 0, 0)
        self._status_lay.setSpacing(_STATUS_COL_SPACING)
        self._status_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self._status_host, 0, Qt.AlignmentFlag.AlignVCenter)

        root.addSpacing(8)

        self.export_btn = PushButton()
        style_compact_button(
            self.export_btn, height=DIALOG_TOOLBAR_HEIGHT, font_size=DIALOG_TOOLBAR_FONT,
        )
        self.export_btn.clicked.connect(self.export_requested.emit)
        root.addWidget(self.export_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(0)
        outer.addWidget(self._ctrl_bar)

        self.setFixedHeight(_COMPACT_H)
        self.setMinimumHeight(_COMPACT_H)
        self.setMaximumHeight(_COMPACT_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.retranslate_ui()

    def retranslate_ui(self):
        self._baseline_lbl.setText(tr('metrics_baseline'))
        self.psnr_cb.setText(tr('metrics_psnr'))
        self.ssim_cb.setText(tr('metrics_ssim'))
        self.export_btn.setText(tr('metrics_export'))
        self._fit_metric_checkboxes()
        fit_dialog_toolbar_button(self.export_btn)
        if self._slot_labels:
            self._apply_baseline_combo()
        self._apply_metric_label_theme()

    def _fit_metric_checkboxes(self):
        for cb in (self.psnr_cb, self.ssim_cb):
            fit_checkbox_width(
                cb, spacing=_TOOL_CB_SPACING, extra=_TOOL_CB_EXTRA,
            )

    def _apply_baseline_combo(self):
        style_baseline_combo(
            self.baseline_combo,
            self._slot_labels,
            closed_width=_BASELINE_CLOSED_WIDTH,
            font_size=DIALOG_TOOLBAR_FONT,
        )

    def _clear_metric_labels(self):
        for lbl in self._metric_labels:
            lbl.deleteLater()
        self._metric_labels.clear()
        while self._status_lay.count():
            item = self._status_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _apply_metric_label_theme(self):
        muted = self._colors.get('text_muted', '#888')
        baseline_ss = (
            f"color: {muted}; background: transparent; "
            f"font-size: {DIALOG_TOOLBAR_FONT}px; padding: 0px; "
            f"margin: 0px; border: none;"
        )
        self._baseline_lbl.setStyleSheet(baseline_ss)
        self._baseline_lbl.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        )
        value_ss = (
            f"color: {muted}; background: transparent; "
            f"font-size: {DIALOG_TOOLBAR_FONT}px;"
        )
        for lbl in self._metric_labels:
            lbl.setStyleSheet(value_ss)

    def set_metrics_display(
        self,
        slot_metrics: Dict[int, Dict[str, Optional[float]]],
        metrics: List[str],
    ):
        self._clear_metric_labels()
        if not slot_metrics or not metrics:
            return
        for slot_i, vals in sorted(slot_metrics.items()):
            lines: List[str] = []
            for key in metrics:
                val = vals.get(key)
                if val is not None:
                    lines.append(f'{slot_i + 1}: {format_metric_value(key, val)}')
            if not lines:
                continue
            col = QWidget()
            col.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
            col.setStyleSheet('background: transparent;')
            vlay = QVBoxLayout(col)
            vlay.setContentsMargins(0, 0, 0, 0)
            vlay.setSpacing(0)
            for line in lines:
                lbl = QLabel(line)
                lbl.setObjectName('compareMutedLabel')
                lbl.setFixedHeight(_VALUE_LINE_H)
                self._metric_labels.append(lbl)
                vlay.addWidget(lbl)
            self._status_lay.addWidget(col, 0, Qt.AlignmentFlag.AlignVCenter)
        self._status_host.adjustSize()
        self._apply_metric_label_theme()

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self.baseline_combo.setStyleSheet(dialog_combo_stylesheet(colors))
        for cb in (self.psnr_cb, self.ssim_cb):
            apply_dialog_checkbox_theme(cb, colors, spacing=_TOOL_CB_SPACING)
        self._fit_metric_checkboxes()
        if self._slot_labels:
            self._apply_baseline_combo()
        self._apply_metric_label_theme()

    def set_slot_labels(self, labels: List[str]):
        self._slot_labels = list(labels)
        prev = self.baseline_combo.currentIndex()
        self.baseline_combo.blockSignals(True)
        self.baseline_combo.clear()
        for label in labels:
            self.baseline_combo.addItem(label)
        if labels:
            idx = prev if 0 <= prev < len(labels) else 0
            self.baseline_combo.setCurrentIndex(idx)
        self.baseline_combo.blockSignals(False)
        self._apply_baseline_combo()

    def baseline_index(self) -> int:
        return max(0, self.baseline_combo.currentIndex())

    def enabled_metrics(self) -> List[str]:
        out: List[str] = []
        if self.psnr_cb.isChecked():
            out.append('psnr')
        if self.ssim_cb.isChecked():
            out.append('ssim')
        return out

    def set_status(self, text: str):
        if not text:
            self._clear_metric_labels()

    def set_export_enabled(self, enabled: bool):
        self.export_btn.setEnabled(enabled)

    def _emit_settings(self, *_args):
        self.settings_changed.emit()
