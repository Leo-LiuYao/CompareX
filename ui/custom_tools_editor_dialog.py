"""Custom extension tools - editor / manager dialog."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QWidget,
)
from qfluentwidgets import PushButton, PrimaryPushButton

from extensions.custom_tool_store import (
    CustomToolRecord, CustomToolsState, DEFAULT_TOOL_CODE, SINGLE_SLOT_TOOL_CODE,
    delete_tool, load_custom_tools, save_custom_tools,
    upsert_tool, validate_tool_code,
)
from extensions.custom_tool_runtime import invalidate_tool_cache
from ui.fluent_integration import (
    style_compact_button, style_compact_input,
    apply_dialog_checkbox_theme, DialogCheckBox,
)
from ui.theme import get_colors


class CustomToolsEditorDialog(QDialog):
    """Create, edit, validate, and save user Python tools."""

    tools_changed = pyqtSignal(object)  # CustomToolsState

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors = get_colors()
        self._state = load_custom_tools()
        self._current_id: Optional[str] = None
        self._dirty = False

        self.setWindowTitle('自定义扩展工具')
        self.resize(920, 640)
        self._build_ui()
        self._reload_list(select_id=self._state.last_selected_id)
        self._apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        hint = QLabel(
            '每个工具是一段 Python 脚本，须定义 run(ctx) 函数。'
            ' ctx.slots[i].source / .display 为 numpy 数组，ctx.np / ctx.cv2 可用。'
            ' 保存后写入 ~/.imagecompare_fluent/config/custom_tools.json，下次自动加载。'
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(QLabel('已保存工具'))
        self.tool_list = QListWidget()
        self.tool_list.currentItemChanged.connect(self._on_list_selection)
        left_lay.addWidget(self.tool_list, stretch=1)

        left_btns = QHBoxLayout()
        self.new_btn = PushButton('新建')
        style_compact_button(self.new_btn)
        self.new_btn.clicked.connect(self._new_tool)
        self.delete_btn = PushButton('删除')
        style_compact_button(self.delete_btn)
        self.delete_btn.clicked.connect(self._delete_tool)
        left_btns.addWidget(self.new_btn)
        left_btns.addWidget(self.delete_btn)
        left_btns.addStretch()
        left_lay.addLayout(left_btns)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('名称'))
        self.name_edit = QLineEdit()
        style_compact_input(self.name_edit)
        self.name_edit.textChanged.connect(self._mark_dirty)
        name_row.addWidget(self.name_edit, stretch=1)
        right_lay.addLayout(name_row)

        desc_row = QHBoxLayout()
        desc_row.addWidget(QLabel('说明'))
        self.desc_edit = QLineEdit()
        style_compact_input(self.desc_edit)
        self.desc_edit.textChanged.connect(self._mark_dirty)
        desc_row.addWidget(self.desc_edit, stretch=1)
        right_lay.addLayout(desc_row)

        opts_row = QHBoxLayout()
        self.show_panel_cb = DialogCheckBox('显示结果面板（多图预览）')
        self.show_panel_cb.setChecked(False)
        self.show_panel_cb.toggled.connect(self._mark_dirty)
        self.slot_picker_cb = DialogCheckBox('需要参考/对比分区（多图工具）')
        self.slot_picker_cb.setChecked(False)
        self.slot_picker_cb.toggled.connect(self._mark_dirty)
        opts_row.addWidget(self.show_panel_cb)
        opts_row.addWidget(self.slot_picker_cb)
        opts_row.addStretch()
        right_lay.addLayout(opts_row)

        right_lay.addWidget(QLabel('Python 代码'))
        self.code_edit = QPlainTextEdit()
        font = QFont('Menlo' if __import__('sys').platform == 'darwin' else 'Consolas', 11)
        self.code_edit.setFont(font)
        self.code_edit.textChanged.connect(self._mark_dirty)
        right_lay.addWidget(self.code_edit, stretch=1)

        self.compile_label = QLabel('')
        self.compile_label.setWordWrap(True)
        right_lay.addWidget(self.compile_label)

        action_row = QHBoxLayout()
        self.compile_btn = PushButton('编译检查')
        style_compact_button(self.compile_btn)
        self.compile_btn.clicked.connect(self._compile_check)
        self.save_btn = PrimaryPushButton('保存')
        style_compact_button(self.save_btn)
        self.save_btn.clicked.connect(self._save_current)
        action_row.addWidget(self.compile_btn)
        action_row.addWidget(self.save_btn)
        action_row.addStretch()
        right_lay.addLayout(action_row)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = PushButton('关闭')
        style_compact_button(close_btn)
        close_btn.clicked.connect(self.close)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def _apply_theme(self):
        colors = self._colors
        apply_dialog_checkbox_theme(self.show_panel_cb, colors, spacing=4)
        apply_dialog_checkbox_theme(self.slot_picker_cb, colors, spacing=4)
        self.setStyleSheet(
            f"QDialog {{ background: {colors['background']}; color: {colors['foreground']}; }}"
            f"QListWidget {{ background: {colors['panel_bg']}; color: {colors['foreground']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 4px; }}"
            f"QPlainTextEdit {{ background: {colors['panel_bg']}; color: {colors['foreground']}; "
            f"border: 1px solid {colors['panel_border']}; border-radius: 4px; padding: 6px; }}"
        )

    def _reload_list(self, select_id: Optional[str] = None):
        self.tool_list.blockSignals(True)
        self.tool_list.clear()
        select_row = 0
        for i, tool in enumerate(self._state.tools):
            item = QListWidgetItem(tool.name)
            item.setData(Qt.ItemDataRole.UserRole, tool.id)
            self.tool_list.addItem(item)
            if select_id and tool.id == select_id:
                select_row = i
        self.tool_list.blockSignals(False)
        if self._state.tools:
            self.tool_list.setCurrentRow(select_row)
        else:
            self._clear_editor()

    def _tool_by_id(self, tool_id: str) -> Optional[CustomToolRecord]:
        return self._state.tool_by_id(tool_id)

    def _on_list_selection(self, current: Optional[QListWidgetItem], _previous):
        if current is None:
            return
        if self._dirty and not self._prompt_save_if_dirty():
            self._reload_list(select_id=self._current_id)
            return
        tool_id = current.data(Qt.ItemDataRole.UserRole)
        tool = self._tool_by_id(tool_id)
        if tool is None:
            return
        self._load_tool(tool)

    def _load_tool(self, tool: CustomToolRecord):
        self._current_id = tool.id
        self._dirty = False
        self.name_edit.blockSignals(True)
        self.desc_edit.blockSignals(True)
        self.show_panel_cb.blockSignals(True)
        self.slot_picker_cb.blockSignals(True)
        self.code_edit.blockSignals(True)
        self.name_edit.setText(tool.name)
        self.desc_edit.setText(tool.description)
        self.show_panel_cb.setChecked(tool.show_result_panel)
        self.slot_picker_cb.setChecked(tool.needs_slot_picker)
        self.code_edit.setPlainText(tool.code)
        self.name_edit.blockSignals(False)
        self.desc_edit.blockSignals(False)
        self.show_panel_cb.blockSignals(False)
        self.slot_picker_cb.blockSignals(False)
        self.code_edit.blockSignals(False)
        self.compile_label.setText('')

    def _clear_editor(self):
        self._current_id = None
        self._dirty = False
        self.name_edit.clear()
        self.desc_edit.clear()
        self.show_panel_cb.setChecked(False)
        self.slot_picker_cb.setChecked(False)
        self.code_edit.clear()
        self.compile_label.setText('')

    def _mark_dirty(self):
        self._dirty = True
        self.compile_label.setText('')

    def _new_tool(self):
        if self._dirty and not self._prompt_save_if_dirty():
            return
        tool = CustomToolRecord.new('新工具', SINGLE_SLOT_TOOL_CODE, '单图工具')
        upsert_tool(self._state, tool)
        save_custom_tools(self._state)
        self._state.last_selected_id = tool.id
        self._reload_list(select_id=tool.id)
        self.tools_changed.emit(self._state)

    def _delete_tool(self):
        if not self._current_id:
            return
        tool = self._tool_by_id(self._current_id)
        if tool is None:
            return
        if QMessageBox.question(
            self, '删除工具', f'确定删除「{tool.name}」？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        invalidate_tool_cache(tool.id)
        delete_tool(self._state, tool.id)
        save_custom_tools(self._state)
        self._current_id = None
        self._dirty = False
        self._reload_list(select_id=self._state.last_selected_id)
        self.tools_changed.emit(self._state)

    def _compile_check(self) -> bool:
        ok, msg = validate_tool_code(self.code_edit.toPlainText())
        color = self._colors['success'] if ok else self._colors.get('error', '#f44336')
        self.compile_label.setStyleSheet(f'color: {color};')
        self.compile_label.setText(msg)
        return ok

    def _save_current(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, '保存失败', '请填写工具名称')
            return
        code = self.code_edit.toPlainText()
        if not self._compile_check():
            QMessageBox.warning(self, '保存失败', '请先通过编译检查')
            return

        if self._current_id:
            tool = self._tool_by_id(self._current_id)
            if tool is None:
                tool = CustomToolRecord.new(name, code)
                self._current_id = tool.id
            else:
                invalidate_tool_cache(tool.id)
                tool.name = name
                tool.description = self.desc_edit.text().strip()
                tool.show_result_panel = self.show_panel_cb.isChecked()
                tool.needs_slot_picker = self.slot_picker_cb.isChecked()
                tool.code = code
        else:
            tool = CustomToolRecord.new(
                name, code, self.desc_edit.text().strip(),
                show_result_panel=self.show_panel_cb.isChecked(),
                needs_slot_picker=self.slot_picker_cb.isChecked(),
            )
            self._current_id = tool.id

        upsert_tool(self._state, tool)
        self._state.last_selected_id = tool.id
        save_custom_tools(self._state)
        self._dirty = False
        self._reload_list(select_id=tool.id)
        self.tools_changed.emit(self._state)
        self.compile_label.setStyleSheet(f"color: {self._colors['success']};")
        self.compile_label.setText('已保存')

    def _prompt_save_if_dirty(self) -> bool:
        if not self._dirty:
            return True
        ans = QMessageBox.question(
            self, '未保存的更改', '当前工具有未保存修改，是否保存？',
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Save:
            self._save_current()
            return not self._dirty
        if ans == QMessageBox.StandardButton.Discard:
            self._dirty = False
            return True
        return False

    def closeEvent(self, event):
        if self._dirty and not self._prompt_save_if_dirty():
            event.ignore()
            return
        super().closeEvent(event)
