"""Compare window - eyedropper pixel detail panel."""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame, QSizePolicy, QLabel,
    QGraphicsOpacityEffect,
)
from qfluentwidgets import ComboBox
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List, Optional, Dict
import numpy as np

from ui.theme import get_colors
from i18n import tr
from ui.fluent_integration import (
    DIALOG_TOOLBAR_FONT, DIALOG_TOOLBAR_HEIGHT,
    style_dialog_checkbox, dialog_combo_stylesheet,
    fit_dialog_combo_width, style_dialog_combo, apply_dialog_checkbox_theme,
    DialogCheckBox, HorizontalScrollArea,
)


COPY_BAR_HEIGHT = DIALOG_TOOLBAR_HEIGHT + 4
H_SCROLLBAR_RESERVE = 8


class PixelSampleCell(QFrame):
    """Per-slot magnified pixel grid + position / RGB / hex."""

    GRID = 9
    DEFAULT_CELL_PX = 18
    TEXT_LINES = 3
    LINE_H = 13
    MIN_CELL_PX = 16
    MAX_CELL_PX = 30

    def __init__(self):
        super().__init__()
        self._title = ""
        self._x = 0
        self._y = 0
        self._rgb = (0, 0, 0)
        self._patch: Optional[np.ndarray] = None
        self._valid = False
        self._colors = get_colors()
        self._dark = True
        self._cell_px = self.DEFAULT_CELL_PX
        self._apply_cell_geometry()

    @property
    def cell_px(self) -> int:
        return self._cell_px

    def _apply_cell_geometry(self):
        grid_h = self.GRID * self._cell_px
        text_h = 12 + self.TEXT_LINES * self.LINE_H + 4
        self.setFixedSize(self.GRID * self._cell_px + 20, 20 + grid_h + text_h)

    def set_cell_px(self, cell_px: int):
        cell_px = max(self.MIN_CELL_PX, min(self.MAX_CELL_PX, int(cell_px)))
        self._cell_px = cell_px
        self._apply_cell_geometry()
        self.updateGeometry()
        self.update()

    @classmethod
    def cell_height_for(cls, cell_px: int) -> int:
        grid_h = cls.GRID * cell_px
        text_h = 12 + cls.TEXT_LINES * cls.LINE_H + 4
        return 20 + grid_h + text_h

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self._dark = colors.get('canvas_bg', '').lower() in ('#1a1a1a', '#1a1a1aff')
        self.update()

    def set_sample(self, data: Dict):
        folder = data.get("folder") or data.get("name", "")
        self._title = folder[:20]
        self._x = data.get("x", 0)
        self._y = data.get("y", 0)
        self._rgb = data.get("rgb", (0, 0, 0))
        self._patch = data.get("patch")
        self._valid = data.get("valid", False)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        c = self._colors
        grid_bg = QColor(40, 40, 40) if self._dark else QColor(245, 245, 245)
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        fm = QFontMetrics(font)

        gw, gh = self.GRID * self._cell_px, self.GRID * self._cell_px
        gx = (self.width() - gw) // 2
        center_x = self.width() // 2

        painter.setPen(QColor(c['text_muted']))
        title = fm.elidedText(self._title, Qt.TextElideMode.ElideRight, self.width() - 8)
        title_rect = fm.boundingRect(title)
        painter.drawText(
            center_x - title_rect.width() // 2, 14, title,
        )

        gy = 20
        painter.fillRect(gx, gy, gw, gh, grid_bg)
        painter.setPen(QColor(c['panel_border']))
        painter.drawRect(gx, gy, gw, gh)

        if self._valid and self._patch is not None:
            patch = self._patch
            ph, pw = patch.shape[:2]
            for py in range(ph):
                for px in range(pw):
                    r, g, b = int(patch[py, px, 0]), int(patch[py, px, 1]), int(patch[py, px, 2])
                    painter.fillRect(
                        gx + px * self._cell_px, gy + py * self._cell_px,
                        self._cell_px, self._cell_px,
                        QColor(r, g, b),
                    )
            cx = gx + (self.GRID // 2) * self._cell_px
            cy = gy + (self.GRID // 2) * self._cell_px
            pen = QPen(QColor(255, 255, 255) if self._dark else QColor(30, 30, 30))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(cx, cy, self._cell_px, self._cell_px)
        else:
            painter.setPen(QColor(c['text_dim']))
            painter.drawText(gx, gy, gw, gh, Qt.AlignmentFlag.AlignCenter, "—")

        r, g, b = self._rgb
        y = gy + gh + 12

        def _draw_centered_line(text: str, color):
            painter.setPen(QColor(color))
            tw = fm.horizontalAdvance(text)
            painter.drawText(center_x - tw // 2, y, text)

        _draw_centered_line(f"({self._x}, {self._y})", c['text_muted'])
        y += self.LINE_H

        rgb_parts = [(f"R:{r}", "#f44336"), (f"G:{g}", "#4caf50"), (f"B:{b}", "#2196f3")]
        gap = 10
        rgb_total = sum(fm.horizontalAdvance(p[0]) for p in rgb_parts) + gap * (len(rgb_parts) - 1)
        rx = center_x - rgb_total // 2
        for text, color in rgb_parts:
            painter.setPen(QColor(color))
            painter.drawText(rx, y, text)
            rx += fm.horizontalAdvance(text) + gap
        y += self.LINE_H

        hex_str = f"#{r:02X}{g:02X}{b:02X}"
        _draw_centered_line(hex_str, c['text_muted'])


class PixelDetailPanel(QWidget):
    """Bottom pixel comparison strip."""

    copy_settings_changed = pyqtSignal()

    @staticmethod
    def preferred_height(cell_px: int = None) -> int:
        if cell_px is None:
            cell_px = PixelSampleCell.DEFAULT_CELL_PX
        return PixelSampleCell.cell_height_for(cell_px) + 30

    def __init__(self):
        super().__init__()
        self._colors = get_colors()
        self._panel_height = 0
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 4)
        root.setSpacing(2)

        self._cells_host = QWidget()
        self._row = QHBoxLayout(self._cells_host)
        self._row.setContentsMargins(8, 4, 8, 0)
        self._row.setSpacing(10)
        self._row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._cells_scroll = HorizontalScrollArea()
        self._cells_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cells_scroll.setWidgetResizable(False)
        self._cells_scroll.setMinimumWidth(0)
        self._cells_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        self._cells_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._cells_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._cells_scroll.setWidget(self._cells_host)
        root.addWidget(self._cells_scroll, stretch=1)

        self._copy_bar = QWidget()
        self._copy_bar.setFixedHeight(COPY_BAR_HEIGHT)
        copy_lay = QHBoxLayout(self._copy_bar)
        copy_lay.setContentsMargins(8, 0, 8, 0)
        copy_lay.setSpacing(0)
        copy_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._copy_cb = DialogCheckBox()
        style_dialog_checkbox(self._copy_cb, spacing=4)
        self._copy_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._copy_cb.toggled.connect(self._on_copy_settings_changed)
        copy_lay.addWidget(self._copy_cb, 0, Qt.AlignmentFlag.AlignVCenter)
        copy_lay.addSpacing(12)

        self._fmt_group = QWidget()
        fmt_lay = QHBoxLayout(self._fmt_group)
        fmt_lay.setContentsMargins(0, 0, 0, 0)
        fmt_lay.setSpacing(4)
        fmt_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        fmt_lbl = QLabel()
        fmt_lay.addWidget(fmt_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        self._copy_format_combo = ComboBox()
        style_dialog_combo(self._copy_format_combo)
        self._copy_format_combo.addItems(["RGB", "HEX"])
        fit_dialog_combo_width(self._copy_format_combo, ["RGB", "HEX"])
        self._copy_format_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._copy_format_combo.currentIndexChanged.connect(self._on_copy_settings_changed)
        fmt_lay.addWidget(self._copy_format_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        self._fmt_group.adjustSize()
        self._fmt_group.setFixedWidth(self._fmt_group.sizeHint().width())
        self._fmt_group.setFixedHeight(DIALOG_TOOLBAR_HEIGHT)
        self._fmt_opacity = QGraphicsOpacityEffect(self._fmt_group)
        self._fmt_group.setGraphicsEffect(self._fmt_opacity)
        self._fmt_opacity.setOpacity(0.0)
        self._fmt_group.setEnabled(False)
        copy_lay.addWidget(self._fmt_group, 0, Qt.AlignmentFlag.AlignVCenter)
        copy_lay.addStretch()
        self._copy_bar.setVisible(False)
        root.addWidget(self._copy_bar)
        self._fmt_label = fmt_lbl

        self._cells: List[PixelSampleCell] = []
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.apply_theme(self._colors)
        self.retranslate_ui()

    def retranslate_ui(self):
        self._copy_cb.setText(tr('pixel_click_copy'))
        self._fmt_label.setText(tr('pixel_format'))
        from ui.fluent_integration import fit_checkbox_width
        fit_checkbox_width(self._copy_cb, spacing=4, extra=12)

    def minimumSize(self):
        from PyQt6.QtCore import QSize
        cell_px = self._cells[0].cell_px if self._cells else PixelSampleCell.DEFAULT_CELL_PX
        h = self._panel_height or self.preferred_height(cell_px)
        return QSize(0, h)

    def _on_copy_settings_changed(self, *_args):
        show_fmt = self._copy_cb.isChecked()
        self._fmt_opacity.setOpacity(1.0 if show_fmt else 0.0)
        self._fmt_group.setEnabled(show_fmt)
        self.copy_settings_changed.emit()

    def set_eyedropper_active(self, active: bool):
        self._copy_bar.setVisible(active)
        if not active:
            self._copy_cb.setChecked(False)
            self._fmt_opacity.setOpacity(0.0)
            self._fmt_group.setEnabled(False)
        if self._panel_height > 0:
            self.set_panel_height(self._panel_height)

    def copy_enabled(self) -> bool:
        return self._copy_cb.isChecked()

    def copy_format(self) -> str:
        return 'hex' if self._copy_format_combo.currentIndex() == 1 else 'rgb'

    @staticmethod
    def _cell_width(cell_px: int = PixelSampleCell.DEFAULT_CELL_PX) -> int:
        return PixelSampleCell.GRID * cell_px + 20

    def content_width(self) -> int:
        cell_px = self._cells[0].cell_px if self._cells else PixelSampleCell.DEFAULT_CELL_PX
        cell_w = self._cell_width(cell_px)
        spacing = 10
        margins = 16
        n = len(self._cells)
        cells_w = n * cell_w + max(0, n - 1) * spacing if n else 0
        return cells_w + margins

    def set_panel_height(self, height: int):
        """Scale pixel grid to panel height; pin copy bar to bottom."""
        self._panel_height = max(0, height)
        self.setFixedHeight(height)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        copy_h = COPY_BAR_HEIGHT if self._copy_bar.isVisible() else 0
        vert_pad = 6 + 4 + 2
        scroll_h = max(100, height - copy_h - vert_pad)
        self._cells_scroll.setFixedHeight(scroll_h)
        content_h = max(80, scroll_h - H_SCROLLBAR_RESERVE)
        self._cells_host.setFixedHeight(content_h)
        static_h = 20 + 12 + PixelSampleCell.TEXT_LINES * PixelSampleCell.LINE_H + 4
        grid_h = max(PixelSampleCell.MIN_CELL_PX * PixelSampleCell.GRID, content_h - static_h)
        cell_px = min(
            PixelSampleCell.MAX_CELL_PX,
            max(PixelSampleCell.MIN_CELL_PX, grid_h // PixelSampleCell.GRID),
        )
        for cell in self._cells:
            cell.set_cell_px(cell_px)
        self.update_content_width()
        self._cells_scroll.verticalScrollBar().setValue(0)

    def update_content_width(self):
        w = self.content_width()
        host_h = self._cells_host.height() if self._cells_host.height() > 0 else 80
        self._cells_host.setFixedSize(w, host_h)
        self.updateGeometry()

    def _apply_panel_style(self):
        c = self._colors
        self.setStyleSheet(
            f"QWidget#compareAuxPanel {{ background: {c['panel_bg']}; "
            f"border: 1px solid {c['panel_border']}; border-radius: 6px; }}"
        )
        muted = (
            f"color: {c['text_muted']}; font-size: {DIALOG_TOOLBAR_FONT}px; "
            f"background: transparent;"
        )
        self._fmt_label.setStyleSheet(muted)
        self._copy_format_combo.setStyleSheet(dialog_combo_stylesheet(c))
        fit_dialog_combo_width(self._copy_format_combo, ["RGB", "HEX"])
        apply_dialog_checkbox_theme(self._copy_cb, c, spacing=4)
        scroll_ss = (
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:horizontal {{ height: {H_SCROLLBAR_RESERVE}px; }}"
        )
        self._cells_scroll.setStyleSheet(scroll_ss)
        self._cells_scroll.viewport().setStyleSheet("background: transparent;")

    def apply_theme(self, colors: Dict[str, str]):
        self._colors = colors
        self._apply_panel_style()
        for cell in self._cells:
            cell.apply_theme(colors)

    def set_slot_count(self, count: int):
        while len(self._cells) < count:
            cell = PixelSampleCell()
            cell.apply_theme(self._colors)
            self._row.addWidget(cell)
            self._cells.append(cell)
        while len(self._cells) > count:
            cell = self._cells.pop()
            self._row.removeWidget(cell)
            cell.deleteLater()
        self.update_content_width()
        if self._panel_height > 0:
            self.set_panel_height(self._panel_height)

    def update_samples(self, samples: List[Dict]):
        self.set_slot_count(len(samples))
        for cell, data in zip(self._cells, samples):
            cell.set_sample(data)
        if self._panel_height > 0:
            self.set_panel_height(self._panel_height)

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        cell_px = self._cells[0].cell_px if self._cells else PixelSampleCell.DEFAULT_CELL_PX
        h = self._panel_height or self.preferred_height(cell_px)
        return QSize(self.content_width(), h)

    def minimumSizeHint(self):
        from PyQt6.QtCore import QSize
        cell_px = self._cells[0].cell_px if self._cells else PixelSampleCell.DEFAULT_CELL_PX
        h = self._panel_height or self.preferred_height(cell_px)
        return QSize(0, h)
