"""Compare window - custom extension tool panel."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPainter, QPen, QColor, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
)
from qfluentwidgets import PushButton, ComboBox

from extensions.custom_tool_store import (
    CustomToolRecord, CustomToolsState, load_custom_tools, save_custom_tools,
)
from ui.fluent_integration import (
    style_compact_button, style_dialog_combo, dialog_combo_stylesheet,
    fit_dialog_combo_width, dialog_toolbar_button_stylesheet,
    fit_dialog_toolbar_button,
    DIALOG_TOOLBAR_HEIGHT, DIALOG_TOOLBAR_FONT,
)
from ui.theme import get_colors
from i18n import tr


class CustomToolPreview(QWidget):
    """Custom tool result preview."""

    MARGIN = 8

    def __init__(self):
        super().__init__()
        self._pixmap: Optional[QPixmap] = None
        self._placeholder = tr('ext_preview_hint')
        self._message = ''
        self._colors = get_colors()
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self.update()

    def set_result(self, *, image: Optional[np.ndarray], message: str = '', error: str = ''):
        self._message = error or message
        self._placeholder = error or message or self._placeholder
        if image is not None:
            h, w = image.shape[:2]
            qimg = QImage(image.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            self._pixmap = QPixmap.fromImage(qimg)
        else:
            self._pixmap = None
        self.update()

    def clear(self, message: str = ''):
        self._pixmap = None
        self._message = message
        self._placeholder = message or tr('ext_no_result')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = self._colors
        dark = c.get('canvas_bg', '').lower() in ('#1a1a1a', '#1a1a1aff')
        bg_key = 'panel_bg' if not dark else 'canvas_bg'
        painter.fillRect(self.rect(), QColor(c[bg_key]))
        content = self.rect().adjusted(self.MARGIN, self.MARGIN, -self.MARGIN, -self.MARGIN)
        painter.setPen(QPen(QColor(c['panel_border']), 1))
        painter.drawRect(content)

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor(c['text_dim']))
            font = QFont()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(content, Qt.AlignmentFlag.AlignCenter, self._placeholder)
            return

        scaled = self._pixmap.scaled(
            content.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        dx = content.x() + (content.width() - scaled.width()) // 2
        dy = content.y() + (content.height() - scaled.height()) // 2
        painter.drawPixmap(dx, dy, scaled)

        if self._message:
            painter.setPen(QColor(c['foreground']))
            font = QFont()
            font.setPointSize(9)
            painter.setFont(font)
            text_rect = content.adjusted(6, 6, -6, -6)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                self._message,
            )


class CustomToolPanel(QWidget):
    """Custom Python tool selection and run panel."""

    run_requested = pyqtSignal()
    manage_requested = pyqtSignal()
    revert_requested = pyqtSignal()
    layout_changed = pyqtSignal()

    _COMPACT_H = DIALOG_TOOLBAR_HEIGHT + 12

    def __init__(self):
        super().__init__()
        self._colors = get_colors()
        self._state = load_custom_tools()
        self._muted: List[QLabel] = []
        self._slot_labels: List[str] = []
        self._preview_height = 300

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(8, 4, 8, 4)
        self._root.setSpacing(4)

        self._ctrl_bar = QWidget()
        self._ctrl_bar.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        ctrl = QHBoxLayout(self._ctrl_bar)
        ctrl.setContentsMargins(0, 0, 0, 0)
        ctrl.setSpacing(5)

        self.tool_combo = ComboBox()
        style_dialog_combo(self.tool_combo)
        self.tool_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.tool_combo.currentIndexChanged.connect(self._on_tool_changed)

        self.target_combo = ComboBox()
        style_dialog_combo(self.target_combo)
        self.target_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.ref_combo = ComboBox()
        style_dialog_combo(self.ref_combo)
        self.ref_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.cmp_combo = ComboBox()
        style_dialog_combo(self.cmp_combo)
        self.cmp_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.run_btn = PushButton()
        style_compact_button(
            self.run_btn, height=DIALOG_TOOLBAR_HEIGHT, font_size=DIALOG_TOOLBAR_FONT,
        )
        self.run_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.run_btn.clicked.connect(self.run_requested.emit)

        self.revert_btn = PushButton()
        style_compact_button(
            self.revert_btn, height=DIALOG_TOOLBAR_HEIGHT, font_size=DIALOG_TOOLBAR_FONT,
        )
        self.revert_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.revert_btn.setToolTip(tr('ext_revert_tip'))
        self.revert_btn.clicked.connect(self.revert_requested.emit)

        self.manage_btn = PushButton()
        style_compact_button(
            self.manage_btn, height=DIALOG_TOOLBAR_HEIGHT, font_size=DIALOG_TOOLBAR_FONT,
        )
        self.manage_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.manage_btn.clicked.connect(self.manage_requested.emit)

        self._tool_wrap, self._tool_lbl = self._ctrl_pair(tr('ext_tool'), self.tool_combo, spacing=2)
        self._target_wrap, self._target_lbl = self._ctrl_pair(tr('ext_apply'), self.target_combo, spacing=2)
        self._ref_wrap, self._ref_lbl = self._ctrl_pair(tr('diff_ref'), self.ref_combo, spacing=2)
        self._cmp_wrap, self._cmp_lbl = self._ctrl_pair(tr('diff_cmp'), self.cmp_combo, spacing=2)
        ctrl.addWidget(self._tool_wrap)
        ctrl.addWidget(self._target_wrap)
        ctrl.addWidget(self._ref_wrap)
        ctrl.addWidget(self._cmp_wrap)
        ctrl.addWidget(self.run_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        ctrl.addWidget(self.revert_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        ctrl.addWidget(self.manage_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        ctrl.addStretch()
        self._root.addWidget(self._ctrl_bar)

        self._result_area = QWidget()
        result_lay = QVBoxLayout(self._result_area)
        result_lay.setContentsMargins(0, 0, 0, 0)
        result_lay.setSpacing(4)
        self.preview = CustomToolPreview()
        result_lay.addWidget(self.preview, stretch=1)
        self.status_label = QLabel('')
        self.status_label.setObjectName('compareMutedLabel')
        self.status_label.setWordWrap(True)
        result_lay.addWidget(self.status_label)
        self._root.addWidget(self._result_area, stretch=1)

        self.reload_tools()
        self.apply_theme(self._colors)
        self.setObjectName('compareCustomPanel')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.retranslate_ui()

    def retranslate_ui(self):
        self._tool_lbl.setText(tr('ext_tool'))
        self._target_lbl.setText(tr('ext_apply'))
        self._ref_lbl.setText(tr('diff_ref'))
        self._cmp_lbl.setText(tr('diff_cmp'))
        self.run_btn.setText(tr('ext_run'))
        self.revert_btn.setText(tr('ext_revert'))
        self.revert_btn.setToolTip(tr('ext_revert_tip'))
        self.manage_btn.setText(tr('ext_manage'))
        for btn in (self.run_btn, self.revert_btn, self.manage_btn):
            fit_dialog_toolbar_button(btn)
        if self._slot_labels:
            self.set_slot_count(len(self._slot_labels), self._slot_labels)

    def _ctrl_pair(self, text: str, widget: QWidget, spacing: int = 4) -> Tuple[QWidget, QLabel]:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)
        lbl = QLabel(text)
        lbl.setObjectName('compareMutedLabel')
        self._muted.append(lbl)
        lay.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        return box, lbl

    def panel_height(self) -> int:
        if self.wants_result_panel():
            return self._COMPACT_H + self._preview_height + 24
        return self._COMPACT_H

    def reload_tools(self, state: Optional[CustomToolsState] = None):
        if state is not None:
            self._state = state
        self.tool_combo.blockSignals(True)
        self.tool_combo.clear()
        for tool in self._state.tools:
            self.tool_combo.addItem(tool.name)
        idx = 0
        if self._state.last_selected_id:
            for i, tool in enumerate(self._state.tools):
                if tool.id == self._state.last_selected_id:
                    idx = i
                    break
        if self._state.tools:
            self.tool_combo.setCurrentIndex(idx)
        self.tool_combo.blockSignals(False)
        self._sync_tool_combo_width()
        self.sync_tool_display_mode()

    def select_tool_by_id(self, tool_id: str) -> bool:
        for i, tool in enumerate(self._state.tools):
            if tool.id == tool_id:
                self.tool_combo.setCurrentIndex(i)
                return True
        return False

    def current_tool(self) -> Optional[CustomToolRecord]:
        idx = self.tool_combo.currentIndex()
        if idx < 0 or idx >= len(self._state.tools):
            return None
        return self._state.tools[idx]

    def wants_result_panel(self) -> bool:
        tool = self.current_tool()
        return tool.show_result_panel if tool else False

    def wants_slot_picker(self) -> bool:
        tool = self.current_tool()
        return tool.needs_slot_picker if tool else False

    def sync_tool_display_mode(self, *, emit_layout: bool = True):
        show_panel = self.wants_result_panel()
        show_ref_cmp = self.wants_slot_picker()
        self._result_area.setVisible(show_panel)
        self._target_wrap.setVisible(not show_ref_cmp)
        self._ref_wrap.setVisible(show_ref_cmp)
        self._cmp_wrap.setVisible(show_ref_cmp)
        self.setFixedHeight(self.panel_height())
        self._sync_target_combo_width()
        self._sync_slot_combo_widths()
        if emit_layout:
            self.layout_changed.emit()

    def set_slot_count(self, count: int, labels: Optional[List[str]] = None):
        count = max(0, count)
        self._slot_labels = labels or [tr('compare_tab_slot_n', n=i + 1) for i in range(count)]
        target_idx = self.target_combo.currentIndex()
        ref_idx = self.ref_combo.currentIndex()
        cmp_idx = self.cmp_combo.currentIndex()
        for combo in (self.target_combo, self.ref_combo, self.cmp_combo):
            combo.blockSignals(True)
            combo.clear()
            for label in self._slot_labels:
                combo.addItem(label)
            combo.blockSignals(False)
        if count >= 1:
            self.target_combo.setCurrentIndex(min(max(0, target_idx), count - 1))
        if count >= 2:
            self.ref_combo.setCurrentIndex(min(max(0, ref_idx), count - 1))
            self.cmp_combo.setCurrentIndex(min(max(1, cmp_idx), count - 1))
        elif count == 1:
            self.ref_combo.setCurrentIndex(0)
            self.cmp_combo.setCurrentIndex(0)
        self._sync_target_combo_width()
        self._sync_slot_combo_widths()

    def set_target_index(self, index: int):
        index = max(0, min(index, max(0, len(self._slot_labels) - 1)))
        self.target_combo.blockSignals(True)
        self.target_combo.setCurrentIndex(index)
        self.target_combo.blockSignals(False)
        if self.wants_slot_picker():
            self.ref_combo.blockSignals(True)
            self.ref_combo.setCurrentIndex(index)
            self.ref_combo.blockSignals(False)

    def target_index(self) -> int:
        if self.wants_slot_picker():
            return self.ref_index()
        idx = self.target_combo.currentIndex()
        return max(0, idx)

    def ref_index(self) -> int:
        idx = self.ref_combo.currentIndex()
        return max(0, idx)

    def cmp_index(self) -> int:
        idx = self.cmp_combo.currentIndex()
        if idx < 0:
            return min(1, max(0, len(self._slot_labels) - 1))
        return idx

    def set_panel_height(self, preview_height: int):
        self._preview_height = max(220, preview_height)
        self.setFixedHeight(self.panel_height())

    def apply_result(self, result: Optional[Dict], *, show_panel: bool = True):
        if not result:
            if show_panel:
                self.preview.clear(tr('ext_no_result'))
                self.status_label.setText('')
            return
        message = result.get('message', '')
        if not show_panel:
            return
        images = result.get('images') or []
        image = result.get('image')
        if image is None and images:
            image = images[0]
        extra = ''
        if len(images) > 1:
            extra = f'（共 {len(images)} 张输出，显示第 1 张）'
        self.preview.set_result(image=image, message=message)
        self.status_label.setText(f'{message}{extra}'.strip())

    def show_error(self, text: str, *, show_panel: bool = True):
        if show_panel:
            self.preview.set_result(image=None, error=text)
            self.status_label.setText(text)

    def result_message(self, result: Optional[Dict]) -> str:
        if not result:
            return ''
        message = str(result.get('message', '') or '')
        images = result.get('images') or []
        if len(images) > 1:
            if message:
                message += f'（{len(images)} 张输出）'
            else:
                message = f'已生成 {len(images)} 张输出'
        return message

    def _on_tool_changed(self, index: int):
        if 0 <= index < len(self._state.tools):
            self._state.last_selected_id = self._state.tools[index].id
            save_custom_tools(self._state)
        self.sync_tool_display_mode()

    def _sync_tool_combo_width(self):
        fit_dialog_combo_width(
            self.tool_combo,
            [t.name for t in self._state.tools] or [tr('ext_no_tools')],
            extra=52, min_width=96,
        )

    def _sync_target_combo_width(self):
        labels = self._slot_labels or [tr('compare_tab_slot_n', n=1)]
        fit_dialog_combo_width(self.target_combo, labels, extra=44, min_width=88)

    def _sync_slot_combo_widths(self):
        labels = self._slot_labels or [tr('compare_tab_slot_n', n=1)]
        fit_dialog_combo_width(self.ref_combo, labels, extra=44, min_width=72)
        fit_dialog_combo_width(self.cmp_combo, labels, extra=44, min_width=72)

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        combo_ss = dialog_combo_stylesheet(colors, padding_left=8, padding_right=28)
        for combo in (self.tool_combo, self.target_combo, self.ref_combo, self.cmp_combo):
            combo.setStyleSheet(combo_ss)
        self._sync_tool_combo_width()
        self._sync_target_combo_width()
        self._sync_slot_combo_widths()
        muted = (
            f"color: {colors.get('text_muted', colors['foreground'])}; "
            f"background: transparent; font-size: {DIALOG_TOOLBAR_FONT}px;"
        )
        for lbl in self._muted:
            lbl.setStyleSheet(muted)
        self.status_label.setStyleSheet(muted)
        btn_ss = dialog_toolbar_button_stylesheet(colors)
        for btn in (self.run_btn, self.revert_btn, self.manage_btn):
            btn.setStyleSheet(btn_ss)
            fit_dialog_toolbar_button(btn)
        self.preview.apply_theme(colors)
