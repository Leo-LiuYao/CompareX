"""
Custom GUI widgets.
"""
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt
from PIL import Image
import numpy as np
from typing import Optional


class ImageLabel(QLabel):
    """Image display label."""

    def __init__(self):
        super().__init__()
        self.image_path = None
        self.pixmap = None
        self.scaled_pixmap = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #404040;")
        self.setMinimumSize(200, 200)

    def set_image_from_path(self, image_path: str):
        """Set image from file path."""
        try:
            pil_image = Image.open(image_path)
            self.set_pil_image(pil_image)
            self.image_path = image_path
        except Exception as e:
            print(f"Error loading image: {e}")
            self.setText("Failed to load image")

    def set_pil_image(self, pil_image: Image.Image):
        """Set image from PIL Image."""
        try:
            # Convert to QPixmap
            if pil_image.mode == 'RGB':
                data = pil_image.tobytes()
                qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGB888)
            elif pil_image.mode == 'RGBA':
                data = pil_image.tobytes()
                qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
            else:
                pil_image = pil_image.convert('RGB')
                data = pil_image.tobytes()
                qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGB888)

            self.pixmap = QPixmap.fromImage(qimage)
            self.update_display()
        except Exception as e:
            print(f"Error setting PIL image: {e}")

    def set_numpy_image(self, numpy_array: np.ndarray):
        """Set image from NumPy array (BGR)."""
        try:
            # BGR to RGB
            if len(numpy_array.shape) == 3 and numpy_array.shape[2] == 3:
                rgb_array = numpy_array[:, :, ::-1]  # BGR to RGB
                h, w, ch = rgb_array.shape
                bytes_per_line = 3 * w
                qimage = QImage(rgb_array.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                self.pixmap = QPixmap.fromImage(qimage)
                self.update_display()
        except Exception as e:
            print(f"Error setting numpy image: {e}")

    def update_display(self):
        """Refresh display."""
        if self.pixmap:
            self.scaled_pixmap = self.pixmap.scaledToFit(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio
            )
            super().setPixmap(self.scaled_pixmap)

    def resizeEvent(self, event):
        """Handle resize."""
        super().resizeEvent(event)
        self.update_display()


class ImageThumbnail(QLabel):
    """Image thumbnail widget."""

    def __init__(self, image_path: str = None):
        super().__init__()
        self.image_path = image_path
        self.pixmap = None
        self.selected = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #2d2d2d; border: 2px solid #404040;")
        self.setMinimumSize(100, 100)
        self.setMaximumSize(100, 100)

        if image_path:
            self.load_thumbnail(image_path)

    def load_thumbnail(self, image_path: str):
        """Load thumbnail."""
        try:
            from utils.image_utils import create_thumbnail
            pil_image = create_thumbnail(image_path, (100, 100))
            if pil_image:
                self.set_pil_image(pil_image)
                self.image_path = image_path
        except Exception as e:
            print(f"Error loading thumbnail: {e}")

    def set_pil_image(self, pil_image: Image.Image):
        """Set thumbnail from PIL Image."""
        try:
            if pil_image.mode == 'RGB':
                data = pil_image.tobytes()
                qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGB888)
            elif pil_image.mode == 'RGBA':
                data = pil_image.tobytes()
                qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
            else:
                pil_image = pil_image.convert('RGB')
                data = pil_image.tobytes()
                qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGB888)

            self.pixmap = QPixmap.fromImage(qimage)
            self.update_display()
        except Exception as e:
            print(f"Error setting thumbnail: {e}")

    def update_display(self):
        """Refresh display."""
        if self.pixmap:
            scaled = self.pixmap.scaledToFit(100, 100, Qt.AspectRatioMode.KeepAspectRatio)
            super().setPixmap(scaled)

    def set_selected(self, selected: bool):
        """Set selection state."""
        self.selected = selected
        if selected:
            self.setStyleSheet("background-color: #2d2d2d; border: 3px solid #0d47a1;")
        else:
            self.setStyleSheet("background-color: #2d2d2d; border: 2px solid #404040;")

    def mousePressEvent(self, event):
        """Mouse click handler."""
        self.set_selected(not self.selected)
        super().mousePressEvent(event)


class NoImagePlaceholder(QWidget):
    """No-image placeholder."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #2d2d2d; border: 1px dashed #404040;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel("No Image")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #808080; font-size: 14px;")

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        self.setLayout(layout)
        self.setMinimumSize(150, 150)
