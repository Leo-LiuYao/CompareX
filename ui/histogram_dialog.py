"""
Histogram comparison dialog.
"""
import matplotlib
matplotlib.use('QtAgg')

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import PushButton, CheckBox
from ui.fluent_integration import style_compact_button, style_compact_checkbox
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from typing import List
import logging

from core.image_loader import ImageInfo
from utils.image_utils import compute_histogram

logger = logging.getLogger(__name__)


class HistogramDialog(QDialog):
    """RGB histogram comparison."""

    COLORS = {'Red': '#f44336', 'Green': '#4caf50', 'Blue': '#2196f3'}

    def __init__(self, images: List[ImageInfo], parent=None):
        super().__init__(parent)
        self.images = images
        self.setWindowTitle("直方图对比")
        self.resize(800, 500)
        self._build_ui()
        self._draw()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        ctrl = QHBoxLayout()
        self.show_r = CheckBox("R")
        self.show_r.setChecked(True)
        self.show_g = CheckBox("G")
        self.show_g.setChecked(True)
        self.show_b = CheckBox("B")
        self.show_b.setChecked(True)
        for cb in (self.show_r, self.show_g, self.show_b):
            style_compact_checkbox(cb)
            cb.stateChanged.connect(self._draw)
            ctrl.addWidget(cb)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.figure = Figure(figsize=(8, 4), facecolor='#1e1e1e')
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        btn_layout = QHBoxLayout()
        close_btn = PushButton("关闭")
        style_compact_button(close_btn)
        close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _draw(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor('#2d2d2d')
        ax.tick_params(colors='#b0b0b0')
        ax.set_xlabel('像素值', color='#b0b0b0')
        ax.set_ylabel('频数', color='#b0b0b0')
        for spine in ax.spines.values():
            spine.set_color('#404040')

        channels = []
        if self.show_r.isChecked():
            channels.append('Red')
        if self.show_g.isChecked():
            channels.append('Green')
        if self.show_b.isChecked():
            channels.append('Blue')

        for img in self.images[:8]:
            hist = compute_histogram(img.path)
            for ch_name in channels:
                if ch_name in hist:
                    color = self.COLORS[ch_name]
                    label = f"{img.name[:16]} - {ch_name[0]}"
                    ax.plot(hist[ch_name], color=color, alpha=0.6, linewidth=1, label=label)

        ax.legend(fontsize=7, facecolor='#2d2d2d', edgecolor='#404040', labelcolor='#b0b0b0')
        ax.set_xlim(0, 255)
        self.figure.tight_layout()
        self.canvas.draw()
