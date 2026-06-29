"""
Left folder sidebar - Fluent style.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QMenu, QApplication, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QTimer
from PyQt6.QtGui import (
    QContextMenuEvent, QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent, QColor, QFont,
    QFontMetrics,
)
from typing import List, Optional, Dict
import logging

from qfluentwidgets import TransparentToolButton, CaptionLabel, FluentIcon as FIF, Theme, isDarkTheme
from qfluentwidgets.common.font import getFont
from ui.qt_icons import close_button_style, CLOSE_BTN_ICON, CLOSE_BTN_SIZE

from core.folder_manager import FolderInfo
from utils.file_utils import format_file_size
from ui.folder_drag import folder_path_from_mime, start_folder_drag
from i18n import tr

logger = logging.getLogger(__name__)


class FolderItemWidget(QFrame):
    """Single folder list entry."""

    clicked = pyqtSignal(str)
    remove_requested = pyqtSignal(str)
    context_menu_requested = pyqtSignal(str, object)  # path, global QPoint
    reorder_drop = pyqtSignal(str, str)  # source_path, target_path

    def __init__(
        self,
        folder: FolderInfo,
        active: bool = False,
        *,
        display_count: Optional[int] = None,
        display_size: Optional[int] = None,
        hidden_count: int = 0,
    ):
        super().__init__()
        self.folder_path = folder.path
        self._folder_name_full = folder.name
        self._active = active
        self._colors: Dict[str, str] = {}
        self._drop_highlight = False
        self._drag_started = False
        self._press_pos = QPoint()
        self._in_elide_update = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 5, 4, 5)
        layout.setSpacing(4)

        icon = QLabel("📁")
        icon.setFixedWidth(18)
        icon.setStyleSheet("background: transparent; font-size: 12px;")
        layout.addWidget(icon)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(0)
        self.name_lbl = CaptionLabel("")
        self.name_lbl.setFixedHeight(14)
        self.name_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.name_lbl.setToolTip(folder.path)
        self._display_count = display_count if display_count is not None else len(folder.images)
        self._display_size = (
            display_size
            if display_size is not None
            else sum(img.file_size for img in folder.images)
        )
        self._hidden_count = hidden_count
        self._meta_text_full = self._build_meta_text()
        self.meta_lbl = CaptionLabel(self._meta_text_full)
        self.meta_lbl.setFixedHeight(12)
        self.meta_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        info.addWidget(self.name_lbl)
        info.addWidget(self.meta_lbl)
        layout.addLayout(info, stretch=1)

        self.rm_btn = TransparentToolButton(FIF.CLOSE)
        self.rm_btn.setFixedSize(CLOSE_BTN_SIZE, CLOSE_BTN_SIZE)
        self.rm_btn.setIconSize(QSize(CLOSE_BTN_ICON, CLOSE_BTN_ICON))
        self.rm_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.rm_btn.setToolTip(tr('menu_remove_folder'))
        self.rm_btn.setStyleSheet(close_button_style(self._colors, 'TransparentToolButton'))
        self.rm_btn.clicked.connect(lambda: self.remove_requested.emit(self.folder_path))
        layout.addWidget(self.rm_btn)
        self._set_active(active)
        self.update_name_elide()

    def _build_meta_text(self) -> str:
        meta = f"{tr('col_count', n=self._display_count)} · {format_file_size(self._display_size)}"
        if self._hidden_count:
            meta += tr('folder_meta_hidden', n=self._hidden_count)
        return meta

    def retranslate_ui(self):
        self._meta_text_full = self._build_meta_text()
        self.rm_btn.setToolTip(tr('menu_remove_folder'))
        self.update_name_elide()

    def update_name_elide(self):
        """Middle-elide folder name and meta for current entry width."""
        if not hasattr(self, '_folder_name_full'):
            return
        margins = self.layout().contentsMargins()
        fixed = (
            margins.left() + margins.right()
            + 18 + self.layout().spacing()
            + self.rm_btn.width() + self.layout().spacing()
        )
        available = max(72, self.width() - fixed)
        name_fm = QFontMetrics(self.name_lbl.font())
        elided = name_fm.elidedText(
            self._folder_name_full, Qt.TextElideMode.ElideMiddle, available,
        )
        if self.name_lbl.text() != elided:
            self.name_lbl.setText(elided)
        meta_fm = QFontMetrics(self.meta_lbl.font())
        meta_elided = meta_fm.elidedText(
            self._meta_text_full, Qt.TextElideMode.ElideMiddle, available,
        )
        if self.meta_lbl.text() != meta_elided:
            self.meta_lbl.setText(meta_elided)
        if elided != self._folder_name_full:
            self.name_lbl.setToolTip(f"{self._folder_name_full}\n{self.folder_path}")
        else:
            self.name_lbl.setToolTip(self.folder_path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._in_elide_update:
            return
        QTimer.singleShot(0, self._deferred_name_elide)

    def _deferred_name_elide(self):
        if self._in_elide_update:
            return
        self._in_elide_update = True
        try:
            self.update_name_elide()
        finally:
            self._in_elide_update = False

    def _apply_label_theme(self):
        c = self._colors
        if not c:
            return
        fg = QColor(c['foreground'])
        muted = QColor(c['text_muted'])
        self.name_lbl.setTextColor(fg, fg)
        self.name_lbl.setFont(getFont(11, QFont.Weight.DemiBold))
        self.meta_lbl.setTextColor(muted, muted)
        self.meta_lbl.setFont(getFont(9))

    def apply_theme(self, colors: Dict[str, str], active: bool = False):
        self._colors = colors
        self._active = active
        self._apply_label_theme()
        if hasattr(self, 'rm_btn'):
            icon_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
            self.rm_btn.setIcon(FIF.CLOSE.icon(icon_theme))
            self.rm_btn.setStyleSheet(close_button_style(colors, 'TransparentToolButton'))
        self._set_active(active)

    def _set_active(self, active: bool):
        self._active = active
        c = self._colors
        drop = self._drop_highlight
        if not c:
            if drop:
                self.setStyleSheet(
                    "FolderItemWidget { background: #1a3050; border: 1px dashed #2196f3; border-radius: 4px; }"
                )
            elif active:
                self.setStyleSheet(
                    "FolderItemWidget { background: #1a3050; border: 1px solid #2196f3; border-radius: 4px; }"
                )
            else:
                self.setStyleSheet(
                    "FolderItemWidget { background: #141414; border: 1px solid #252525; border-radius: 4px; }"
                    "FolderItemWidget:hover { background: #1c1c1c; border-color: #333; }"
                )
            return
        if drop:
            self.setStyleSheet(
                f"FolderItemWidget {{ background: {c['accent']}33; "
                f"border: 1px dashed {c['accent']}; border-radius: 4px; }}"
            )
        elif active:
            self.setStyleSheet(
                f"FolderItemWidget {{ background: {c['accent']}33; "
                f"border: 1px solid {c['accent']}; border-radius: 4px; }}"
            )
        else:
            self.setStyleSheet(
                f"FolderItemWidget {{ background: {c['panel_bg']}; "
                f"border: 1px solid {c['panel_border']}; border-radius: 4px; }}"
                f"FolderItemWidget:hover {{ background: {c['hover_bg']}; }}"
            )

    def set_drop_highlight(self, highlighted: bool):
        if self._drop_highlight != highlighted:
            self._drop_highlight = highlighted
            self._set_active(self._active)

    def set_active(self, active: bool):
        self._set_active(active)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
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

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._drag_started:
            self.clicked.emit(self.folder_path)
        super().mouseReleaseEvent(event)

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
        self.context_menu_requested.emit(self.folder_path, event.globalPos())
        event.accept()


class FolderSidebar(QWidget):
    """Folder sidebar."""

    folder_selected = pyqtSignal(str)
    folder_removed = pyqtSignal(str)
    folder_context_menu = pyqtSignal(str, object)
    folder_reorder_requested = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._header = QLabel()
        layout.addWidget(self._header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()

        scroll.setWidget(self.container)
        layout.addWidget(scroll, stretch=1)

        self._items: List[FolderItemWidget] = []
        self._folder_paths: List[str] = []
        self._active_path: Optional[str] = None
        self._theme_colors: Optional[Dict[str, str]] = None
        self.retranslate_ui()

    def retranslate_ui(self):
        self._header.setText(tr('sidebar_loaded_folders'))
        for item in self._items:
            item.retranslate_ui()

    def apply_theme(self, colors: Dict[str, str]):
        self._theme_colors = colors
        self._header.setStyleSheet(
            f"color: {colors['text_muted']}; font-size: 10px; font-weight: bold; padding: 0 2px;"
        )
        for item in self._items:
            item.apply_theme(colors, item.folder_path == self._active_path)

    def set_folders(
        self,
        folders: List[FolderInfo],
        active_path: Optional[str] = None,
        folder_stats: Optional[Dict[str, tuple]] = None,
    ):
        """folder_stats: path -> (visible_count, visible_size, hidden_count)"""
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()
        self._folder_paths = [f.path for f in folders]

        self._active_path = active_path
        for folder in folders:
            active = folder.path == active_path
            stats = folder_stats.get(folder.path) if folder_stats else None
            if stats:
                item = FolderItemWidget(
                    folder, active,
                    display_count=stats[0],
                    display_size=stats[1],
                    hidden_count=stats[2],
                )
            else:
                item = FolderItemWidget(folder, active)
            item.clicked.connect(self._on_item_clicked)
            item.remove_requested.connect(self.folder_removed.emit)
            item.context_menu_requested.connect(self.folder_context_menu.emit)
            item.reorder_drop.connect(self._on_reorder_drop)
            self.list_layout.insertWidget(self.list_layout.count() - 1, item)
            self._items.append(item)

        if self._theme_colors:
            self.apply_theme(self._theme_colors)
        QTimer.singleShot(0, self.update_name_elision)

    def _on_reorder_drop(self, source_path: str, target_path: str):
        try:
            from_idx = self._folder_paths.index(source_path)
            to_idx = self._folder_paths.index(target_path)
        except ValueError:
            return
        if from_idx != to_idx:
            self.folder_reorder_requested.emit(from_idx, to_idx)

    def _on_item_clicked(self, path: str):
        self._active_path = path
        for item in self._items:
            item.set_active(item.folder_path == path)
        self.folder_selected.emit(path)

    def get_active_path(self) -> Optional[str]:
        return self._active_path

    def update_name_elision(self):
        for item in self._items:
            item.update_name_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_name_elision()
