"""Workspace history selection dialog."""
from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem,
    QHBoxLayout, QLabel, QMessageBox,
)
from PyQt6.QtCore import Qt
from qfluentwidgets import PrimaryPushButton, PushButton

from i18n import tr
from ui.theme import get_colors
from ui.workspace_store import (
    WorkspaceState, format_workspace_label, valid_folder_paths,
    delete_workspace_history_at, load_workspace_history_states,
)


class WorkspaceHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[WorkspaceState] = []
        self._selected: Optional[WorkspaceState] = None
        self.setWindowTitle(tr('workspace_history_title'))
        self.resize(520, 400)

        colors = get_colors()
        layout = QVBoxLayout(self)
        hint = QLabel(tr('workspace_history_hint_sidebar'))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {colors['text_muted']};")
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background: {colors['background']}; color: {colors['foreground']}; "
            f"border: 1px solid {colors['panel_border']}; }}"
            f"QListWidget::item:selected {{ background: {colors['accent']}; }}"
        )
        self.list_widget.itemDoubleClicked.connect(self._accept_current)
        layout.addWidget(self.list_widget, stretch=1)

        buttons = QHBoxLayout()
        self.delete_btn = PushButton(tr('delete'))
        self.delete_btn.clicked.connect(self._delete_current)
        buttons.addWidget(self.delete_btn)
        buttons.addStretch()
        cancel_btn = PushButton(tr('cancel'))
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        self.open_btn = PrimaryPushButton(tr('workspace_open'))
        self.open_btn.clicked.connect(self._accept_current)
        buttons.addWidget(self.open_btn)
        layout.addLayout(buttons)

        self._reload_list()

    def _reload_list(self):
        self._entries = load_workspace_history_states()
        self.list_widget.clear()
        for i, state in enumerate(self._entries):
            label = format_workspace_label(state, i)
            if not valid_folder_paths(state.folders):
                label = f"{label}\n({tr('workspace_unavailable')})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list_widget.addItem(item)
        has_items = bool(self._entries)
        self.open_btn.setEnabled(has_items)
        self.delete_btn.setEnabled(has_items)
        if has_items:
            self.list_widget.setCurrentRow(0)

    def _current_index(self) -> int:
        row = self.list_widget.currentRow()
        return row if 0 <= row < len(self._entries) else -1

    def _delete_current(self):
        idx = self._current_index()
        if idx < 0:
            return
        if QMessageBox.question(
            self, tr('confirm'), tr('workspace_delete_confirm'),
        ) != QMessageBox.StandardButton.Yes:
            return
        delete_workspace_history_at(idx)
        self._reload_list()
        if not self._entries:
            self._selected = None

    def _accept_current(self):
        idx = self._current_index()
        if idx < 0:
            return
        state = self._entries[idx]
        if not valid_folder_paths(state.folders):
            QMessageBox.information(self, tr('tip'), tr('workspace_restore_failed'))
            return
        self._selected = state
        self.accept()

    def selected_state(self) -> Optional[WorkspaceState]:
        return self._selected
