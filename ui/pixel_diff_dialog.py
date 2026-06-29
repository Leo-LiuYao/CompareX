"""
Pixel-level difference dialog - Beyond Compare style heatmap.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSlider, QGroupBox, QSplitter,
)
from qfluentwidgets import PushButton
from ui.fluent_integration import style_compact_button, style_compact_input, enable_slider_keyboard_tune
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt
from typing import List, Optional
import numpy as np
import cv2
import logging

from core.image_loader import ImageInfo, ImageLoader
from utils.image_utils import DIFF_METHODS, compute_diff_map, load_image_cv2

logger = logging.getLogger(__name__)


class PixelDiffDialog(QDialog):
    """Pixel-level difference comparison dialog."""

    def __init__(self, images: List[ImageInfo], image_loader: ImageLoader, parent=None):
        super().__init__(parent)
        self.images = images
        self.image_loader = image_loader
        self.setWindowTitle("像素差异对比")
        self.resize(1000, 700)
        self._build_ui()
        if len(images) >= 2:
            self._update_diff()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("参考图:"))
        self.ref_combo = QComboBox()
        for img in self.images:
            self.ref_combo.addItem(img.name, img.path)
        self.ref_combo.currentIndexChanged.connect(self._update_diff)
        ctrl.addWidget(self.ref_combo)

        ctrl.addWidget(QLabel("对比图:"))
        self.cmp_combo = QComboBox()
        for img in self.images:
            self.cmp_combo.addItem(img.name, img.path)
        if len(self.images) > 1:
            self.cmp_combo.setCurrentIndex(1)
        self.cmp_combo.currentIndexChanged.connect(self._update_diff)
        ctrl.addWidget(self.cmp_combo)

        ctrl.addWidget(QLabel("方法:"))
        self.method_combo = QComboBox()
        for key, label in DIFF_METHODS:
            self.method_combo.addItem(label, key)
        self.method_combo.currentIndexChanged.connect(self._update_diff)
        ctrl.addWidget(self.method_combo)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        sens_layout = QHBoxLayout()
        sens_layout.addWidget(QLabel("差异灵敏度:"))
        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(1, 100)
        self.sens_slider.setValue(50)
        enable_slider_keyboard_tune(self.sens_slider)
        self.sens_slider.valueChanged.connect(self._update_diff)
        sens_layout.addWidget(self.sens_slider)
        layout.addLayout(sens_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.ref_label = QLabel("参考图")
        self.ref_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ref_label.setMinimumSize(300, 300)
        self.ref_label.setStyleSheet("background: #1a1a1a; border: 1px solid #404040;")

        self.diff_label = QLabel("差异热力图")
        self.diff_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.diff_label.setMinimumSize(300, 300)
        self.diff_label.setStyleSheet("background: #1a1a1a; border: 1px solid #404040;")

        self.cmp_label = QLabel("对比图")
        self.cmp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cmp_label.setMinimumSize(300, 300)
        self.cmp_label.setStyleSheet("background: #1a1a1a; border: 1px solid #404040;")

        splitter.addWidget(self.ref_label)
        splitter.addWidget(self.diff_label)
        splitter.addWidget(self.cmp_label)
        layout.addWidget(splitter, stretch=1)

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #b0b0b0; padding: 8px; background: #2d2d2d; border-radius: 4px;")
        layout.addWidget(self.stats_label)

        btn_layout = QHBoxLayout()
        export_btn = PushButton("导出热力图")
        style_compact_button(export_btn)
        export_btn.clicked.connect(self._export_heatmap)
        close_btn = PushButton("关闭")
        style_compact_button(close_btn)
        close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._heatmap_bgr: Optional[np.ndarray] = None

    def _get_method(self) -> str:
        key = self.method_combo.currentData()
        return key if key else 'euclidean'

    def _update_diff(self):
        if len(self.images) < 2:
            self.stats_label.setText("至少需要 2 张图片进行像素对比")
            return

        ref_path = self.ref_combo.currentData()
        cmp_path = self.cmp_combo.currentData()
        if ref_path == cmp_path:
            self.stats_label.setText("请选择不同的两张图片")
            return

        img1 = load_image_cv2(ref_path)
        img2 = load_image_cv2(cmp_path)
        if img1 is None or img2 is None:
            self.stats_label.setText("图片加载失败")
            return

        import cv2
        rgb1 = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
        rgb2 = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)
        sensitivity = self.sens_slider.value() / 100.0
        result = compute_diff_map(rgb1, rgb2, method=self._get_method(), sensitivity=sensitivity)
        if not result:
            self.stats_label.setText("差异计算失败")
            return

        self._heatmap_bgr = result['heatmap_bgr']
        hh = min(rgb1.shape[0], rgb2.shape[0])
        ww = min(rgb1.shape[1], rgb2.shape[1])

        self._set_image(self.ref_label, rgb1[:hh, :ww])
        self._set_image(self.cmp_label, rgb2[:hh, :ww])
        self._set_image(self.diff_label, result['heatmap_rgb'])

        self.stats_label.setText(
            f"平均差异: {result['mean_diff']:.2f}  |  最大差异: {result['max_diff']:.2f}  |  "
            f"标准差: {result['std_diff']:.2f}  |  显著差异像素: {result['diff_pct']:.1f}%  |  "
            f"分辨率: {ww}×{hh}  |  红色区域 = 差异较大"
        )

    def _set_image(self, label: QLabel, rgb: np.ndarray):
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg.copy())
        label.setPixmap(
            pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def _export_heatmap(self):
        if self._heatmap_bgr is None:
            return
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出热力图", "diff_heatmap.png", "PNG (*.png)")
        if path:
            cv2.imwrite(path, self._heatmap_bgr)
