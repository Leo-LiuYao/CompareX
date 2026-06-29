"""Compare window - color / brightness / channel control panel."""
from typing import List, Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from qfluentwidgets import PushButton, Slider, ComboBox

from ui.fluent_integration import (
    style_compact_button, sync_fluent_slider, dialog_combo_stylesheet,
    fit_dialog_combo_width, style_dialog_combo, style_compact_dialog_slider,
    apply_dialog_checkbox_theme, fit_checkbox_width, DialogCheckBox,
    style_dialog_checkbox, fit_dialog_toolbar_button,
    DIALOG_TOOLBAR_HEIGHT, DIALOG_TOOLBAR_FONT,
)
from ui.theme import get_colors
from i18n import tr
from utils.color_view import (
    ColorViewParams, CHANNEL_ORDER_PRESETS, VIEW_MODES,
)

_SLIDER_W = 118
_VALUE_W = 36


class ColorViewPanel(QWidget):
    settings_changed = pyqtSignal(object)  # ColorViewParams

    def __init__(self):
        super().__init__()
        self._colors = get_colors()
        self._muted: list = []
        self._value_labels: list = []
        self._updating = False
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(48)
        self._settings_timer.timeout.connect(self._flush_settings)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(12)

        self.order_combo = ComboBox()
        style_dialog_combo(self.order_combo)
        for _, label, _ in CHANNEL_ORDER_PRESETS:
            self.order_combo.addItem(label)
        self.order_combo.currentIndexChanged.connect(self._emit_settings)

        self.mode_combo = ComboBox()
        style_dialog_combo(self.mode_combo)
        for _, label in VIEW_MODES:
            self.mode_combo.addItem(label)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.channel_mono_cb = DialogCheckBox()
        self.channel_mono_cb.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self.channel_mono_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.channel_mono_cb.setToolTip(tr('color_mono_tip'))
        self.channel_mono_cb.toggled.connect(self._emit_settings)

        self._display_wrap = QWidget()
        disp_lay = QHBoxLayout(self._display_wrap)
        disp_lay.setContentsMargins(0, 0, 0, 0)
        disp_lay.setSpacing(10)
        disp_lay.addWidget(self.mode_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        disp_lay.addWidget(self.channel_mono_cb, 0, Qt.AlignmentFlag.AlignVCenter)

        self.bright_slider = self._make_slider(-100, 100, 0)
        self.contrast_slider = self._make_slider(0, 200, 100)
        self.gamma_slider = self._make_slider(10, 300, 100)
        self._bright_lbl = self._value_label("0")
        self._contrast_lbl = self._value_label("100%")
        self._gamma_lbl = self._value_label("1.00")

        root.addWidget(self._pair(tr('color_channel'), self.order_combo))
        root.addWidget(self._pair(tr('color_display'), self._display_wrap))
        root.addWidget(self._slider_pair(tr('color_brightness'), self.bright_slider, self._bright_lbl))
        root.addWidget(self._slider_pair(tr('color_contrast'), self.contrast_slider, self._contrast_lbl))
        root.addWidget(self._slider_pair('Gamma:', self.gamma_slider, self._gamma_lbl))

        self.reset_btn = PushButton()
        style_compact_button(
            self.reset_btn, height=DIALOG_TOOLBAR_HEIGHT, font_size=DIALOG_TOOLBAR_FONT,
        )
        self.reset_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reset_btn.clicked.connect(self.reset_defaults)
        root.addWidget(self.reset_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addStretch()

        self.setFixedHeight(DIALOG_TOOLBAR_HEIGHT + 12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_theme(self._colors)
        self._sync_combo_widths()
        self._sync_value_labels()
        self._sync_channel_mono_visibility()
        self.retranslate_ui()

    def retranslate_ui(self):
        self.channel_mono_cb.setText(tr('color_mono_channel'))
        self.channel_mono_cb.setToolTip(tr('color_mono_tip'))
        self.reset_btn.setText(tr('color_reset'))
        labels = (
            tr('color_channel'), tr('color_display'),
            tr('color_brightness'), tr('color_contrast'),
        )
        for lbl, text in zip(self._muted, labels):
            lbl.setText(text)
        order_idx = self.order_combo.currentIndex()
        mode_idx = self.mode_combo.currentIndex()
        self.order_combo.blockSignals(True)
        self.mode_combo.blockSignals(True)
        self.order_combo.clear()
        for _, label, _ in CHANNEL_ORDER_PRESETS:
            self.order_combo.addItem(label)
        self.mode_combo.clear()
        for key, _ in VIEW_MODES:
            self.mode_combo.addItem(tr(f'view_mode_{key}'))
        if 0 <= order_idx < len(CHANNEL_ORDER_PRESETS):
            self.order_combo.setCurrentIndex(order_idx)
        if 0 <= mode_idx < len(VIEW_MODES):
            self.mode_combo.setCurrentIndex(mode_idx)
        self.order_combo.blockSignals(False)
        self.mode_combo.blockSignals(False)
        self._sync_combo_widths()
        self._sync_channel_mono_visibility()
        fit_dialog_toolbar_button(self.reset_btn)

    def _value_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("compareValueLabel")
        lbl.setFixedWidth(_VALUE_W)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._value_labels.append(lbl)
        return lbl

    def _make_slider(self, lo: int, hi: int, val: int) -> Slider:
        s = Slider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.setMinimumWidth(_SLIDER_W)
        s.setFixedWidth(_SLIDER_W)
        style_compact_dialog_slider(s, handle_size=12, height=DIALOG_TOOLBAR_HEIGHT)
        s.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        s.valueChanged.connect(self._on_slider_changed)
        s.sliderReleased.connect(self._flush_settings)
        return s

    def _pair(self, text: str, widget: QWidget) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(text)
        lbl.setObjectName("compareMutedLabel")
        self._muted.append(lbl)
        lay.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        return box

    def _slider_pair(self, text: str, slider: Slider, value_lbl: QLabel) -> QWidget:
        """Label + slider + value (value to the right of slider)."""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(text)
        lbl.setObjectName("compareMutedLabel")
        self._muted.append(lbl)
        lay.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(slider, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(value_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        return box

    def _on_mode_changed(self, _idx: int):
        self._sync_channel_mono_visibility()
        self._emit_settings()

    def _sync_channel_mono_visibility(self):
        mode_idx = self.mode_combo.currentIndex()
        view_mode = VIEW_MODES[mode_idx][0] if mode_idx >= 0 else 'color'
        show = view_mode in ('r', 'g', 'b')
        self.channel_mono_cb.setVisible(show)
        if not show and self.channel_mono_cb.isChecked():
            self._updating = True
            try:
                self.channel_mono_cb.setChecked(False)
            finally:
                self._updating = False
        if show:
            fit_checkbox_width(self.channel_mono_cb, spacing=4, extra=10)

    def _on_slider_changed(self, _v: int):
        self._sync_value_labels()
        self._schedule_settings()

    def _sync_value_labels(self):
        self._bright_lbl.setText(str(self.bright_slider.value()))
        self._contrast_lbl.setText(f"{self.contrast_slider.value()}%")
        self._gamma_lbl.setText(f"{self.gamma_slider.value() / 100:.2f}")

    def _sync_combo_widths(self):
        fit_dialog_combo_width(
            self.order_combo,
            [label for _, label, _ in CHANNEL_ORDER_PRESETS],
            extra=52, min_width=64,
        )
        fit_dialog_combo_width(
            self.mode_combo,
            [tr(f'view_mode_{key}') for key, _ in VIEW_MODES],
            extra=52, min_width=72,
        )

    def params(self) -> ColorViewParams:
        order_idx = self.order_combo.currentIndex()
        order_key = CHANNEL_ORDER_PRESETS[order_idx][0] if order_idx >= 0 else 'rgb'
        mode_idx = self.mode_combo.currentIndex()
        view_mode = VIEW_MODES[mode_idx][0] if mode_idx >= 0 else 'color'
        return ColorViewParams(
            order_key=order_key,
            view_mode=view_mode,
            channel_mono=self.channel_mono_cb.isChecked(),
            brightness=self.bright_slider.value(),
            contrast=self.contrast_slider.value(),
            gamma=self.gamma_slider.value() / 100.0,
        )

    def reset_defaults(self):
        self._updating = True
        try:
            self.order_combo.setCurrentIndex(0)
            self.mode_combo.setCurrentIndex(0)
            self.channel_mono_cb.setChecked(False)
            sync_fluent_slider(self.bright_slider, 0)
            sync_fluent_slider(self.contrast_slider, 100)
            sync_fluent_slider(self.gamma_slider, 100)
            self._sync_value_labels()
            self._sync_channel_mono_visibility()
        finally:
            self._updating = False
        self._emit_settings()

    def _schedule_settings(self):
        if self._updating:
            return
        self._settings_timer.start()

    def _flush_settings(self):
        if self._updating:
            return
        self._settings_timer.stop()
        self.settings_changed.emit(self.params())

    def _emit_settings(self):
        self._flush_settings()

    def apply_theme(self, colors: dict):
        self._colors = colors
        fg = colors['foreground']
        muted = colors.get('text_muted', colors['foreground'])
        combo_ss = dialog_combo_stylesheet(
            colors, padding_left=10, padding_right=34,
        )
        self.order_combo.setStyleSheet(combo_ss)
        self.mode_combo.setStyleSheet(combo_ss)
        apply_dialog_checkbox_theme(self.channel_mono_cb, colors, spacing=4)
        fit_checkbox_width(self.channel_mono_cb, spacing=4, extra=10)
        for lbl in self._muted:
            lbl.setStyleSheet(
                f"color: {muted}; font-size: {DIALOG_TOOLBAR_FONT}px; background: transparent;"
            )
        for lbl in self._value_labels:
            lbl.setStyleSheet(
                f"color: {fg}; font-size: {DIALOG_TOOLBAR_FONT}px; background: transparent;"
            )
        self.reset_btn.setStyleSheet(
            f"PushButton {{ color: {fg}; background: {colors['panel_bg']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 4px; "
            f"font-size: {DIALOG_TOOLBAR_FONT}px; padding: 0 8px; }}"
            f"PushButton:hover {{ background: {colors.get('hover_bg', colors['panel_border'])}; }}"
        )
