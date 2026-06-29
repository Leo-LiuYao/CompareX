"""
Main window - Fluent Design style.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QSplitter, QStatusBar, QMessageBox, QStackedWidget, QLineEdit,
    QFrame, QMenu, QApplication, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox,
    QDialog,
)
from PyQt6.QtGui import QAction, QKeySequence, QDragEnterEvent, QDropEvent, QActionGroup, QGuiApplication, QIcon
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer, QSize
from pathlib import Path
from typing import List, Optional, Tuple, Set
import logging
import math

from qfluentwidgets import (
    TransparentToolButton,
    SearchLineEdit, Slider, CaptionLabel, BodyLabel,
    FluentIcon as FIF, LineEdit, SpinBox, ComboBox, CheckBox,
)

from config import APP_NAME, WINDOW_WIDTH, WINDOW_HEIGHT, SHORTCUTS, THUMB_SCALE_PRESETS, DEFAULT_THUMB_SCALE, APP_ICON_PATH
from ui.styles import get_stylesheet
from ui.theme import (
    get_colors, save_theme, is_dark_theme, follows_system, set_follow_system,
    init_theme_with_app, system_prefers_dark,
)
from ui.fluent_integration import (
    style_compact_button, style_compact_input, style_search_input,
    sync_fluent_slider, flip_icon_horizontal, make_pill_button, apply_pill_button,
    enable_slider_keyboard_tune,
    COMPACT_ICON,
)
from ui.app_state import (
    load_last_folder_dir, save_last_folder_dir,
    load_compare_display_name, save_compare_display_name,
    load_language, save_language,
)
from ui.image_grid_view import (
    SingleFolderView, MultiFolderGridView, DropZoneWidget,
    thumb_scale_to_slider_index, slider_index_to_thumb_scale,
)
from ui.folder_sidebar import FolderSidebar
from ui.mode_segment_switch import ModeSegmentSwitch
from ui.align_segment_switch import AlignSegmentSwitch
from ui.compare_dialog import CompareDialog
from ui.user_manual_dialog import UserManualDialog
from core.folder_manager import FolderManager, FolderInfo
from core.image_loader import ImageLoader, ImageInfo
from utils.file_utils import format_file_size, validate_folder_path
from utils.platform_utils import reveal_in_file_manager, open_folder_in_file_manager, copy_text_to_clipboard
from utils.image_utils import rotate_image_file
from utils.cache import image_cache
from utils.display_utils import screen_items, place_window_on_screen
from ui.workspace_store import (
    WorkspaceState, save_workspace, load_workspace, clear_workspace,
    valid_folder_paths,
)
from ui.workspace_history_dialog import WorkspaceHistoryDialog
from i18n import tr, set_language, register_listener, language

logger = logging.getLogger(__name__)

MAX_FOLDERS = 12
_FLUENT_INPUT_TYPES = (
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox,
    LineEdit, SearchLineEdit, SpinBox, ComboBox,
)


def _menu_style(colors: dict) -> str:
    return (
        f"QMenu {{ background: {colors['panel_bg']}; color: {colors['foreground']}; "
        f"border: 1px solid {colors['panel_border']}; padding: 4px; }}"
        f"QMenu::item {{ padding: 6px 24px; }}"
        f"QMenu::item:selected {{ background: {colors['accent']}; }}"
    )


class AppEventFilter(QObject):
    """Global shortcuts: Space open/next compare row, B previous row, Tab in compare."""

    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window

    def _focus_in_compare(self, cw: CompareDialog) -> bool:
        if cw.isActiveWindow():
            return True
        fw = QApplication.focusWidget()
        w = fw
        while w:
            if w is cw or w is cw.canvas:
                return True
            w = w.parentWidget()
        return False

    def _handle_compare_tab(self, cw: CompareDialog, event) -> bool:
        from PyQt6.QtGui import QKeyEvent
        if not isinstance(event, QKeyEvent):
            return False
        canvas = cw.canvas
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Tab and not event.isAutoRepeat():
                if canvas._tab_preview_slot is None:
                    canvas.enter_tab_preview(canvas._slot_at_cursor())
                return True
        elif event.type() == QEvent.Type.KeyRelease:
            if event.key() == Qt.Key.Key_Tab and not event.isAutoRepeat():
                canvas.exit_tab_preview()
                return True
        return False

    def _typing_in_field(self) -> bool:
        fw = QApplication.focusWidget()
        return bool(fw and isinstance(fw, _FLUENT_INPUT_TYPES))

    def eventFilter(self, obj, event):
        from PyQt6.QtGui import QKeyEvent

        cw = self.main_window.compare_window

        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if isinstance(event, QKeyEvent) and cw and cw.isVisible() and self._focus_in_compare(cw):
                if self._handle_compare_tab(cw, event):
                    return True

        if event.type() != QEvent.Type.KeyPress:
            return False
        if not isinstance(event, QKeyEvent):
            return False

        key = event.key()
        if self._typing_in_field():
            return False

        if (
            key == Qt.Key.Key_M
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            if cw and cw.isVisible() and self._focus_in_compare(cw):
                return False
            if event.isAutoRepeat():
                return False
            self.main_window.toggle_compare_mode()
            return True

        if key not in (Qt.Key.Key_Space, Qt.Key.Key_B):
            return False

        if cw and cw.isVisible():
            delta = 1 if key == Qt.Key.Key_Space else -1
            self.main_window.navigate_compare_group(delta)
            return True

        if event.isAutoRepeat():
            return False
        if key == Qt.Key.Key_Space:
            self.main_window.navigate_compare_group(0, force_open=True)
            return True
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setAcceptDrops(True)

        self.image_loader = ImageLoader()
        self.folder_manager = FolderManager(self.image_loader)
        self.selected_images: List[ImageInfo] = []
        self.compare_window: Optional[CompareDialog] = None
        self.compare_row_index = 0
        self._compare_excluded_folders: Set[str] = set()
        self._last_folder_dir = load_last_folder_dir()
        self._display_screen_names: List[str] = []
        self._workspace_save_timer = QTimer(self)
        self._workspace_save_timer.setSingleShot(True)
        self._workspace_save_timer.setInterval(800)
        self._workspace_save_timer.timeout.connect(self._persist_workspace)
        self._restoring_workspace = False

        set_language(load_language())
        register_listener(self.retranslate_ui)

        self._build_ui()
        self._setup_shortcuts()
        self._setup_context_menus()
        self._fix_button_focus()
        init_theme_with_app()
        self.apply_theme()
        self.update_display()
        self._app_filter = AppEventFilter(self)
        QApplication.instance().installEventFilter(self._app_filter)
        QApplication.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)
        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(lambda _: self._refresh_display_combo())
            app.screenRemoved.connect(lambda _: self._refresh_display_combo())
        self.retranslate_ui()
        QTimer.singleShot(0, self._try_restore_workspace)
        logger.info(f"{APP_NAME} started")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setHandleWidth(5)
        splitter.setSizes([260, 1140])
        splitter.splitterMoved.connect(self._on_main_splitter_moved)
        self._main_splitter = splitter
        root.addWidget(splitter)

        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        self.left_panel = panel
        panel.setObjectName("leftPanel")
        panel.setMinimumWidth(240)
        panel.setMaximumWidth(560)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        sidebar_actions = QWidget()
        sidebar_actions.setStyleSheet("background: transparent;")
        actions_layout = QHBoxLayout(sidebar_actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)

        self.add_folder_btn = make_pill_button("添加文件夹", FIF.FOLDER_ADD)
        self.add_folder_btn.clicked.connect(self.open_folder_dialog)
        actions_layout.addWidget(self.add_folder_btn, stretch=3)

        self.clear_folders_btn = make_pill_button("清空", FIF.BROOM)
        self.clear_folders_btn.clicked.connect(self.clear_folders)
        actions_layout.addWidget(self.clear_folders_btn, stretch=2)

        layout.addWidget(sidebar_actions)

        self.folder_sidebar = FolderSidebar()
        self.folder_sidebar.folder_selected.connect(self._on_folder_selected)
        self.folder_sidebar.folder_removed.connect(self._remove_folder)
        self.folder_sidebar.folder_reorder_requested.connect(self._reorder_folders)
        self.folder_sidebar.folder_context_menu.connect(self._show_folder_context_menu)
        layout.addWidget(self.folder_sidebar, stretch=1)

        self.search_edit = SearchLineEdit()
        style_search_input(self.search_edit, get_colors())
        self.search_edit.setPlaceholderText("搜索图片...")
        self.search_edit.textChanged.connect(self._on_search)
        layout.addWidget(self.search_edit)

        self.history_btn = make_pill_button("历史", FIF.HISTORY)
        self.history_btn.clicked.connect(self._open_workspace_history)
        layout.addWidget(self.history_btn)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        self.center_panel = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QFrame()
        self.top_bar = top_bar
        top_bar.setFixedHeight(42)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)
        top_layout.setSpacing(0)

        self.center_title = CaptionLabel(tr('browse_images'))
        top_layout.addWidget(self.center_title)
        top_layout.addStretch()

        top_controls = QWidget()
        top_controls.setStyleSheet("background: transparent;")
        controls_layout = QHBoxLayout(top_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)

        self.align_switch = AlignSegmentSwitch(top_controls)
        self.align_switch.set_align('name', animate=False, emit=False)
        self.align_switch.setEnabled(False)
        self.align_switch.align_changed.connect(self.switch_grid_align)
        controls_layout.addWidget(self.align_switch)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedSize(1, 18)
        sep.setStyleSheet("background: transparent; color: #D0D0D0;")
        self._top_bar_sep = sep
        controls_layout.addWidget(sep)

        self.mode_switch = ModeSegmentSwitch(top_controls)
        self.mode_switch.set_mode('single', animate=False, emit=False)
        self.mode_switch.mode_changed.connect(self.switch_mode)
        controls_layout.addWidget(self.mode_switch)

        display_sep = QFrame()
        display_sep.setFrameShape(QFrame.Shape.VLine)
        display_sep.setFixedSize(1, 18)
        display_sep.setStyleSheet("background: transparent; color: #D0D0D0;")
        self._display_sep = display_sep
        controls_layout.addWidget(display_sep)

        self.display_label = CaptionLabel("显示器")
        controls_layout.addWidget(self.display_label)

        self.display_combo = ComboBox(top_controls)
        self.display_combo.setFixedWidth(200)
        self.display_combo.currentIndexChanged.connect(self._on_display_combo_changed)
        controls_layout.addWidget(self.display_combo)
        self._refresh_display_combo()

        self.compare_btn = make_pill_button("对比", FIF.VIEW)
        self.compare_btn.setMinimumWidth(72)
        self.compare_btn.clicked.connect(self.open_compare_window)
        controls_layout.addWidget(self.compare_btn)

        top_layout.addWidget(top_controls)
        layout.addWidget(top_bar)

        self.stack = QStackedWidget()
        self.drop_zone = DropZoneWidget()
        self.drop_zone.folders_dropped.connect(self._add_folders)
        self.single_view = SingleFolderView()
        self.single_view.selection_changed.connect(self._on_selection_changed)
        self.single_view.thumb_scale_changed.connect(self._on_view_thumb_scale_changed)
        self.single_view.image_context_menu.connect(self._show_image_context_menu)
        self.single_view.view_context_menu.connect(self._show_view_context_menu)
        self.single_view.image_double_clicked.connect(self._open_single_image_compare)
        self.multi_view = MultiFolderGridView()
        self.multi_view.selection_changed.connect(self._on_selection_changed)
        self.multi_view.thumb_scale_changed.connect(self._on_view_thumb_scale_changed)
        self.multi_view.folder_remove_requested.connect(self._remove_folder)
        self.multi_view.folder_reorder_requested.connect(self._reorder_folders)
        self.multi_view.image_context_menu.connect(self._show_image_context_menu)
        self.multi_view.folder_context_menu.connect(self._show_folder_context_menu)
        self.multi_view.view_context_menu.connect(self._show_view_context_menu)
        self.multi_view.image_double_clicked.connect(self._open_single_image_compare)

        self.stack.addWidget(self.drop_zone)
        self.stack.addWidget(self.single_view)
        self.stack.addWidget(self.multi_view)
        layout.addWidget(self.stack, stretch=1)
        return panel

    def _build_menu(self):
        mb = self.menuBar()
        self._menu_file = mb.addMenu("")
        open_act = QAction("", self)
        open_act.setShortcut(QKeySequence(SHORTCUTS['open_folder']))
        open_act.triggered.connect(self.open_folder_dialog)
        self._open_folder_act = open_act
        self._menu_file.addAction(open_act)
        self._menu_file.addSeparator()
        self._workspace_menu = self._menu_file.addMenu("")
        self._save_workspace_act = QAction("", self)
        self._save_workspace_act.triggered.connect(self._save_workspace_now)
        self._workspace_menu.addAction(self._save_workspace_act)
        self._restore_workspace_act = QAction("", self)
        self._restore_workspace_act.triggered.connect(self._restore_workspace)
        self._workspace_menu.addAction(self._restore_workspace_act)
        self._workspace_history_act = QAction("", self)
        self._workspace_history_act.triggered.connect(self._open_workspace_history)
        self._workspace_menu.addAction(self._workspace_history_act)
        self._clear_workspace_act = QAction("", self)
        self._clear_workspace_act.triggered.connect(self._clear_workspace_history)
        self._workspace_menu.addAction(self._clear_workspace_act)
        self._menu_file.addSeparator()
        exit_act = QAction("", self)
        exit_act.setShortcut(QKeySequence("Ctrl+Q"))
        exit_act.triggered.connect(self.close)
        self._exit_act = exit_act
        self._menu_file.addAction(exit_act)

        self._menu_edit = mb.addMenu("")
        self._clear_all_act = QAction("", self)
        self._clear_all_act.triggered.connect(self.clear_folders)
        self._menu_edit.addAction(self._clear_all_act)
        self._remove_folder_act = QAction("", self)
        self._remove_folder_act.triggered.connect(self._remove_active_folder)
        self._menu_edit.addAction(self._remove_folder_act)

        self._menu_tools = mb.addMenu("")
        cmp_act = QAction("", self)
        cmp_act.setShortcut(QKeySequence("Space"))
        cmp_act.triggered.connect(self.open_compare_window)
        self._compare_act = cmp_act
        self._menu_tools.addAction(cmp_act)

        info_act = QAction("", self)
        info_act.setShortcut(QKeySequence(SHORTCUTS['image_info']))
        info_act.triggered.connect(lambda: self.show_image_info())
        self._image_info_act = info_act
        self._menu_tools.addAction(info_act)

        self._menu_view = mb.addMenu("")
        toggle_mode_act = QAction("", self)
        toggle_mode_act.setShortcut(QKeySequence(SHORTCUTS['toggle_mode']))
        toggle_mode_act.triggered.connect(self.toggle_compare_mode)
        self._toggle_mode_act = toggle_mode_act
        self._menu_view.addAction(toggle_mode_act)
        self._menu_view.addSeparator()
        self.follow_system_act = QAction("", self)
        self.follow_system_act.setCheckable(True)
        self.follow_system_act.setChecked(follows_system())
        self.follow_system_act.triggered.connect(self._toggle_follow_system)
        self._menu_view.addAction(self.follow_system_act)
        self._menu_view.addSeparator()
        self.theme_group = QActionGroup(self)
        self.dark_theme_act = QAction("", self)
        self.dark_theme_act.setCheckable(True)
        self.dark_theme_act.triggered.connect(lambda: self.apply_theme(True))
        self.theme_group.addAction(self.dark_theme_act)
        self._menu_view.addAction(self.dark_theme_act)
        self.light_theme_act = QAction("", self)
        self.light_theme_act.setCheckable(True)
        self.light_theme_act.triggered.connect(lambda: self.apply_theme(False))
        self.theme_group.addAction(self.light_theme_act)
        self._menu_view.addAction(self.light_theme_act)
        self._menu_view.addSeparator()
        self._lang_group = QActionGroup(self)
        self._lang_zh_act = QAction("", self)
        self._lang_zh_act.setCheckable(True)
        self._lang_zh_act.triggered.connect(lambda: self._set_language('zh'))
        self._lang_group.addAction(self._lang_zh_act)
        self._menu_view.addAction(self._lang_zh_act)
        self._lang_en_act = QAction("", self)
        self._lang_en_act.setCheckable(True)
        self._lang_en_act.triggered.connect(lambda: self._set_language('en'))
        self._lang_group.addAction(self._lang_en_act)
        self._menu_view.addAction(self._lang_en_act)

        self._menu_help = mb.addMenu("")
        self._manual_act = QAction("", self)
        self._manual_act.triggered.connect(self.show_user_manual)
        self._menu_help.addAction(self._manual_act)

    def retranslate_ui(self):
        self.setWindowTitle(tr('app_title'))
        self._menu_file.setTitle(tr('menu_file'))
        self._open_folder_act.setText(tr('open_folder'))
        self._workspace_menu.setTitle(tr('workspace'))
        self._save_workspace_act.setText(tr('save_workspace'))
        self._restore_workspace_act.setText(tr('restore_workspace'))
        self._workspace_history_act.setText(tr('workspace_history'))
        self._clear_workspace_act.setText(tr('clear_workspace'))
        self._exit_act.setText(tr('exit'))
        self._menu_edit.setTitle(tr('menu_edit'))
        self._clear_all_act.setText(tr('clear_all'))
        self._remove_folder_act.setText(tr('remove_folder'))
        self._menu_tools.setTitle(tr('menu_tools'))
        self._compare_act.setText(tr('compare'))
        self._image_info_act.setText(tr('image_info'))
        self._menu_view.setTitle(tr('menu_view'))
        self._toggle_mode_act.setText(tr('toggle_mode'))
        self.follow_system_act.setText(tr('follow_system'))
        self.dark_theme_act.setText(tr('dark_theme'))
        self.light_theme_act.setText(tr('light_theme'))
        self._lang_zh_act.setText(tr('lang_zh'))
        self._lang_en_act.setText(tr('lang_en'))
        self._menu_help.setTitle(tr('menu_help'))
        self._manual_act.setText(tr('user_manual'))
        self._lang_zh_act.setChecked(language() == 'zh')
        self._lang_en_act.setChecked(language() == 'en')
        if hasattr(self, 'add_folder_btn'):
            self.add_folder_btn.setText(tr('add_folder'))
        if hasattr(self, 'clear_folders_btn'):
            self.clear_folders_btn.setText(tr('clear_all'))
        if hasattr(self, 'compare_btn'):
            self.compare_btn.setText(tr('compare'))
        if hasattr(self, 'history_btn'):
            self.history_btn.setText(tr('workspace_history_short'))
        if hasattr(self, 'drop_zone'):
            self.drop_zone.retranslate_ui()
        if hasattr(self, 'multi_view'):
            self.multi_view.retranslate_ui()
        if hasattr(self, 'mode_switch'):
            self.mode_switch.retranslate_ui()
        if hasattr(self, 'align_switch'):
            self.align_switch.retranslate_ui()
        if hasattr(self, 'folder_sidebar'):
            self.folder_sidebar.retranslate_ui()
        if hasattr(self, 'display_combo'):
            self._refresh_display_combo()
        if hasattr(self, 'selection_label'):
            n = len(self.selected_images)
            self.selection_label.setText(tr('status_selected_n', n=n))
        if hasattr(self, 'display_label'):
            self.display_label.setText(tr('display'))
        if hasattr(self, 'search_edit'):
            self.search_edit.setPlaceholderText(tr('search_placeholder'))
        if hasattr(self, 'thumb_zoom_label'):
            self.thumb_zoom_label.setText(tr('thumb_size'))
        if hasattr(self, 'rotate_left_btn'):
            self.rotate_left_btn.setToolTip(tr('rotate_left'))
            self.rotate_right_btn.setToolTip(tr('rotate_right'))
        if self.compare_window is not None:
            if self.compare_window.isVisible():
                cw = self.compare_window
                gi = cw.canvas.group_index
                groups = cw.canvas.groups
                if groups and 0 <= gi < len(groups):
                    self.compare_window.setWindowTitle(
                        self._compare_window_title(groups[gi], gi, len(groups), True),
                    )
            if hasattr(self.compare_window, 'retranslate_ui'):
                self.compare_window.retranslate_ui()
        self._refresh_header_text()
        if hasattr(self, 'status_label'):
            if self.folder_manager.get_folder_count() == 0:
                self.status_label.setText(tr('ready'))
            else:
                self._update_status()

    def _refresh_header_text(self):
        """Update title bar only (language switch)."""
        if not hasattr(self, 'center_title'):
            return
        count = self.folder_manager.get_folder_count()
        if count == 0:
            self.center_title.setText(tr('title_drop_hint'))
        elif self.folder_manager.mode == 'single':
            af = self.folder_manager.get_active_folder()
            if af:
                n = len(self.folder_manager.get_visible_images(af))
                self.center_title.setText(tr('title_single', name=af.name, n=n))
        else:
            grid = self.folder_manager.get_images_grid()
            align = tr('align_index') if self.folder_manager.grid_align == 'index' else tr('align_name')
            self.center_title.setText(
                tr('title_multi', cols=count, rows=len(grid), align=align),
            )

    def _set_language(self, lang: str):
        save_language(lang)
        set_language(lang)

    def _open_workspace_history(self):
        dlg = WorkspaceHistoryDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        state = dlg.selected_state()
        if state is None:
            return
        paths = valid_folder_paths(state.folders)
        if not paths:
            QMessageBox.information(self, tr('tip'), tr('workspace_restore_failed'))
            return
        self._apply_workspace_state(state, paths)
        QMessageBox.information(self, tr('tip'), tr('workspace_restored'))

    def _workspace_state(self) -> WorkspaceState:
        active = self.folder_manager.get_active_folder()
        return WorkspaceState(
            folders=[f.path for f in self.folder_manager.folders],
            mode=self.folder_manager.mode,
            grid_align=self.folder_manager.grid_align,
            compare_row_index=self.compare_row_index,
            active_folder_path=active.path if active else '',
            excluded_paths=sorted(self.folder_manager._excluded_paths),
            compare_excluded_folders=sorted(self._compare_excluded_folders),
        )

    def _schedule_workspace_save(self):
        if self._restoring_workspace:
            return
        self._workspace_save_timer.start()

    def _persist_workspace(self):
        if self._restoring_workspace:
            return
        if not self.folder_manager.folders:
            return
        save_workspace(self._workspace_state())

    def _save_workspace_now(self):
        if not self.folder_manager.folders:
            QMessageBox.information(self, tr('tip'), tr('add_folders_first'))
            return
        save_workspace(self._workspace_state())
        QMessageBox.information(self, tr('tip'), tr('workspace_saved'))

    def _restore_workspace(self):
        state = load_workspace()
        if not state:
            QMessageBox.information(self, tr('tip'), tr('workspace_restore_failed'))
            return
        paths = valid_folder_paths(state.folders)
        if not paths:
            QMessageBox.information(self, tr('tip'), tr('workspace_restore_failed'))
            return
        self._apply_workspace_state(state, paths)
        QMessageBox.information(self, tr('tip'), tr('workspace_restored'))

    def _try_restore_workspace(self):
        state = load_workspace()
        if not state:
            return
        paths = valid_folder_paths(state.folders)
        if not paths:
            return
        self._apply_workspace_state(state, paths)

    def _apply_workspace_state(self, state: WorkspaceState, paths: List[str]):
        self._restoring_workspace = True
        try:
            self.folder_manager.clear_folders()
            self.selected_images.clear()
            self._compare_excluded_folders = set(state.compare_excluded_folders)
            for p in paths:
                self.folder_manager.add_folder(p)
            self.folder_manager.mode = state.mode if state.mode in ('single', 'multi') else 'single'
            if state.grid_align in ('name', 'index'):
                self.folder_manager.grid_align = state.grid_align
            if state.active_folder_path:
                self.folder_manager.set_active_folder_by_path(state.active_folder_path)
            for ep in state.excluded_paths:
                self.folder_manager.exclude_image(ep)
            self.compare_row_index = max(0, state.compare_row_index)
            self._sync_mode_to_folder_count()
            self.update_display()
        finally:
            self._restoring_workspace = False

    def _clear_workspace_history(self):
        if QMessageBox.question(
            self, tr('confirm'), tr('clear_workspace') + '?',
        ) != QMessageBox.StandardButton.Yes:
            return
        clear_workspace()
        QMessageBox.information(self, tr('tip'), tr('workspace_cleared'))

    def closeEvent(self, event):
        self._persist_workspace()
        self.image_loader.shutdown()
        event.accept()

    def _build_toolbar(self):
        tb = self.addToolBar(tr('toolbar_tools'))
        self.toolbar = tb
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize())

        colors = get_colors()
        self.rotate_left_btn = TransparentToolButton()
        self.rotate_left_btn.setIcon(flip_icon_horizontal(FIF.ROTATE.icon(), COMPACT_ICON))
        self.rotate_left_btn.setFixedSize(28, 28)
        self.rotate_left_btn.setIconSize(QSize(COMPACT_ICON, COMPACT_ICON))
        self.rotate_left_btn.setToolTip("左旋 90°")
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_selected_images(90))
        tb.addWidget(self.rotate_left_btn)
        self.rotate_right_btn = TransparentToolButton(FIF.ROTATE)
        self.rotate_right_btn.setFixedSize(28, 28)
        self.rotate_right_btn.setIconSize(QSize(COMPACT_ICON, COMPACT_ICON))
        self.rotate_right_btn.setToolTip("右旋 90°")
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_selected_images(-90))
        tb.addWidget(self.rotate_right_btn)

    def _build_statusbar(self):
        self.setStatusBar(QStatusBar())
        bar_widget = QWidget()
        bar_layout = QHBoxLayout(bar_widget)
        bar_layout.setContentsMargins(4, 0, 4, 0)
        bar_layout.setSpacing(10)

        self.status_label = CaptionLabel(tr('ready'))
        bar_layout.addWidget(self.status_label)
        bar_layout.addStretch(1)

        self.thumb_zoom_widget = QWidget()
        thumb_layout = QHBoxLayout(self.thumb_zoom_widget)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(6)
        self.thumb_zoom_label = CaptionLabel("缩略图大小")
        thumb_layout.addWidget(self.thumb_zoom_label)
        self.thumb_scale_slider = Slider(Qt.Orientation.Horizontal)
        self.thumb_scale_slider.setRange(0, len(THUMB_SCALE_PRESETS) - 1)
        self.thumb_scale_slider.setValue(thumb_scale_to_slider_index(DEFAULT_THUMB_SCALE))
        self.thumb_scale_slider.setSingleStep(1)
        self.thumb_scale_slider.setPageStep(1)
        self.thumb_scale_slider.setFixedWidth(120)
        self.thumb_scale_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        enable_slider_keyboard_tune(self.thumb_scale_slider)
        self.thumb_scale_slider.valueChanged.connect(self._on_thumb_scale_slider)
        thumb_layout.addWidget(self.thumb_scale_slider)
        self.thumb_scale_value = CaptionLabel(f"{int(DEFAULT_THUMB_SCALE * 100)}%")
        self.thumb_scale_value.setFixedWidth(36)
        self.thumb_scale_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        thumb_layout.addWidget(self.thumb_scale_value)
        bar_layout.addWidget(self.thumb_zoom_widget)
        self.thumb_zoom_widget.setVisible(False)

        bar_layout.addStretch(1)
        self.selection_label = CaptionLabel("已选: 0")
        bar_layout.addWidget(self.selection_label)
        self.statusBar().addWidget(bar_widget, 1)

    def _setup_shortcuts(self):
        """Space / B / Ctrl+M handled by AppEventFilter globally."""
        toggle_mode_act = QAction(self)
        toggle_mode_act.setShortcut(QKeySequence(SHORTCUTS['toggle_mode']))
        toggle_mode_act.triggered.connect(self.toggle_compare_mode)
        self.addAction(toggle_mode_act)

    def _fix_button_focus(self):
        """On Mac, prevent buttons from stealing Space key."""
        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _setup_context_menus(self):
        self.drop_zone.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.drop_zone.customContextMenuRequested.connect(
            lambda pos: self._show_empty_context_menu(self.drop_zone.mapToGlobal(pos))
        )

    def _toggle_follow_system(self, checked: bool):
        set_follow_system(checked)
        self.apply_theme()

    def _on_system_color_scheme_changed(self, _scheme=None):
        if follows_system():
            self.apply_theme()

    def _sync_theme_menu(self):
        if not hasattr(self, 'follow_system_act'):
            return
        follow = follows_system()
        self.follow_system_act.setChecked(follow)
        self.dark_theme_act.setEnabled(not follow)
        self.light_theme_act.setEnabled(not follow)
        dark = is_dark_theme()
        self.dark_theme_act.setChecked(dark)
        self.light_theme_act.setChecked(not dark)

    def apply_theme(self, is_dark: Optional[bool] = None):
        if is_dark is not None:
            save_theme(is_dark)
        elif follows_system():
            save_theme(system_prefers_dark(), follow_system=True)
        colors = get_colors()
        dark = is_dark_theme()

        self._sync_theme_menu()

        self.setStyleSheet(get_stylesheet())
        self.left_panel.setStyleSheet(
            f"#leftPanel {{ background: {colors['sidebar_bg']}; "
            f"border-right: 1px solid {colors['panel_border']}; }}"
        )
        self.center_panel.setStyleSheet(f"background: {colors['background']};")
        self.top_bar.setStyleSheet(
            f"background: {colors['panel_bg']}; border-bottom: 1px solid {colors['panel_border']};"
        )
        self.center_title.setStyleSheet(
            f"color: {colors['text_muted']}; background: transparent;"
        )
        if hasattr(self, 'mode_switch'):
            self.mode_switch.apply_theme(colors)
            self.mode_switch.set_mode(self.folder_manager.mode, animate=False, emit=False)
        if hasattr(self, 'align_switch'):
            self.align_switch.apply_theme(colors)
            self.align_switch.set_align(self.folder_manager.grid_align, animate=False, emit=False)
            self._update_align_switch_state()
        if hasattr(self, '_top_bar_sep'):
            self._top_bar_sep.setStyleSheet(
                f"background: transparent; color: {colors['panel_border']};"
            )
        if hasattr(self, '_display_sep'):
            self._display_sep.setStyleSheet(
                f"background: transparent; color: {colors['panel_border']};"
            )
        if hasattr(self, 'display_label'):
            self.display_label.setStyleSheet(
                f"color: {colors['text_muted']}; background: transparent;"
            )
        if hasattr(self, 'display_combo'):
            style_compact_input(self.display_combo, height=28, font_size=12)
        self.toolbar.setStyleSheet(
            f"QToolBar {{ background: {colors['panel_bg']}; "
            f"border-bottom: 1px solid {colors['panel_border']}; spacing: 6px; padding: 2px 6px; }}"
        )
        if hasattr(self, 'rotate_left_btn'):
            self.rotate_left_btn.setIcon(
                flip_icon_horizontal(FIF.ROTATE.icon(), COMPACT_ICON)
            )
            self.rotate_right_btn.setIcon(FIF.ROTATE.icon())
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background: {colors['panel_bg']}; border-top: 1px solid {colors['panel_border']}; }}"
        )
        if hasattr(self, 'thumb_zoom_widget'):
            self.thumb_zoom_label.setStyleSheet(f"color: {colors['text_muted']}; background: transparent;")
            self.thumb_scale_value.setStyleSheet(f"color: {colors['text_muted']}; background: transparent;")
            self.status_label.setStyleSheet(f"color: {colors['text_muted']}; background: transparent;")
            self.selection_label.setStyleSheet(f"color: {colors['text_muted']}; background: transparent;")
        self.drop_zone.apply_theme(colors)
        self.single_view.apply_theme(colors)
        self.multi_view.apply_theme(colors)
        self.folder_sidebar.apply_theme(colors)
        if self.compare_window is not None:
            self.compare_window.apply_theme(colors)
        if hasattr(self, 'search_edit'):
            style_search_input(self.search_edit, colors)
        if hasattr(self, 'add_folder_btn'):
            apply_pill_button(self.add_folder_btn, colors, 'primary')
            apply_pill_button(self.clear_folders_btn, colors, 'secondary')
            apply_pill_button(self.compare_btn, colors, 'accent')
        if hasattr(self, 'history_btn'):
            apply_pill_button(self.history_btn, colors, 'secondary')

    def _make_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style(get_colors()))
        return menu

    def _show_empty_context_menu(self, global_pos):
        menu = self._make_menu()
        menu.addAction(tr('menu_add_folder'), self.open_folder_dialog)
        menu.addAction(tr('menu_compare_space'), self.open_compare_window)
        if self.folder_manager.get_folder_count() > 0:
            menu.addSeparator()
            menu.addAction(tr('menu_clear_folders'), self.clear_folders)
        menu.exec(global_pos)

    def _show_view_context_menu(self, global_pos):
        menu = self._make_menu()
        menu.addAction(tr('menu_compare_space'), self.open_compare_window)
        view = self.single_view if self.stack.currentIndex() == 1 else self.multi_view
        menu.addAction(tr('menu_select_all'), view.select_all)
        menu.addAction(tr('menu_clear_selection'), view.clear_selection)
        menu.addSeparator()
        menu.addAction(tr('menu_add_folder'), self.open_folder_dialog)
        menu.exec(global_pos)

    def _show_image_context_menu(self, image_info: ImageInfo, global_pos):
        if image_info.path not in {i.path for i in self.selected_images}:
            self.selected_images = [image_info]
            self._refresh_view_selection([image_info])

        menu = self._make_menu()
        menu.addAction(tr('menu_compare_space'), self.open_compare_window)
        menu.addAction(tr('menu_single_view'), lambda: self._open_single_image_compare(image_info))
        menu.addAction(tr('menu_image_info'), lambda: self.show_image_info([image_info]))
        menu.addSeparator()
        menu.addAction(tr('ctx_copy_path'), lambda: copy_text_to_clipboard(image_info.path))
        import sys as _sys
        menu.addAction(
            tr('ctx_reveal') if _sys.platform == 'darwin' else tr('ctx_reveal_win'),
            lambda: reveal_in_file_manager(image_info.path),
        )
        menu.addSeparator()
        to_hide = [
            i for i in self.selected_images
            if not self.folder_manager.is_excluded(i.path)
        ]
        if to_hide:
            n = len(to_hide)
            label = tr('menu_exclude_one') if n == 1 else tr('menu_exclude_n', n=n)
            menu.addAction(label, lambda imgs=to_hide: self._exclude_images_from_preview(imgs))
            menu.addSeparator()
        view = self.single_view if self.stack.currentIndex() == 1 else self.multi_view
        menu.addAction(tr('menu_select_all'), view.select_all)
        menu.addAction(tr('menu_clear_selection'), view.clear_selection)
        menu.exec(global_pos)

    def _show_folder_context_menu(self, folder_path: str, global_pos):
        menu = self._make_menu()
        menu.addAction(tr('menu_single_folder'), lambda: self._on_folder_selected(folder_path))
        menu.addAction(tr('menu_compare_space'), self.open_compare_window)
        menu.addSeparator()
        menu.addAction(
            tr('ctx_reveal') if __import__('sys').platform == 'darwin' else tr('ctx_reveal_win'),
            lambda: open_folder_in_file_manager(folder_path),
        )
        menu.addAction(tr('ctx_copy_path'), lambda: copy_text_to_clipboard(folder_path))
        hidden_n = self.folder_manager.get_excluded_count_for_folder(folder_path)
        if hidden_n:
            menu.addSeparator()
            menu.addAction(
                tr('menu_restore_hidden', n=hidden_n),
                lambda: self._restore_folder_hidden(folder_path),
            )
        menu.addSeparator()
        menu.addAction(tr('menu_remove_folder'), lambda: self._remove_folder(folder_path))
        menu.exec(global_pos)

    def _exclude_images_from_preview(self, images: List[ImageInfo]):
        """Hide images from preview/compare (multi-select); files on disk unchanged."""
        if not images:
            return
        hidden_paths: set = set()
        for img in images:
            if self.folder_manager.exclude_image(img.path):
                hidden_paths.add(img.path)
        if not hidden_paths:
            return
        self.selected_images = [
            i for i in self.selected_images if i.path not in hidden_paths
        ]
        self.update_display()
        self._schedule_workspace_save()
        n = len(hidden_paths)
        if n == 1:
            name = next(i.name for i in images if i.path in hidden_paths)
            self.status_label.setText(tr('hidden_one', name=name))
        else:
            self.status_label.setText(tr('hidden_n', n=n))

    def _restore_folder_hidden(self, folder_path: str):
        n = self.folder_manager.restore_folder_hidden(folder_path)
        if n:
            self.update_display()
            self.status_label.setText(tr('restored_n', n=n))

    def _refresh_view_selection(self, images: List[ImageInfo]):
        paths = {i.path for i in images}
        view = self.single_view if self.stack.currentIndex() == 1 else self.multi_view
        if hasattr(view, 'selected'):
            view.selected = paths
            view._refresh_selection()
        self._on_selection_changed(images)

    def rotate_selected_images(self, degrees: int):
        """Rotate selected images in place. degrees: PIL angle (positive = CCW)."""
        imgs = list(self.selected_images)
        if not imgs:
            QMessageBox.information(self, tr('tip'), tr('select_images_rotate'))
            return
        ok_count = 0
        fail_paths: List[str] = []
        rotated_paths: set = set()
        for img in imgs:
            if rotate_image_file(img.path, degrees):
                image_cache.invalidate_thumbnail(img.path)
                self.image_loader.invalidate_image(img.path)
                self.folder_manager.reload_image(img.path)
                rotated_paths.add(img.path)
                ok_count += 1
            else:
                fail_paths.append(img.name)
        saved_paths = {i.path for i in imgs}
        self.update_display()
        if rotated_paths and self.compare_window and self.compare_window.isVisible():
            self.compare_window.reload_modified_images(rotated_paths)
        if saved_paths:
            view = self.single_view if self.stack.currentIndex() == 1 else self.multi_view
            if hasattr(view, 'selected'):
                view.selected = saved_paths
                view._refresh_selection()
            self.selected_images = view.get_selected() if hasattr(view, 'get_selected') else imgs
            self._on_selection_changed(self.selected_images)
        if fail_paths:
            QMessageBox.warning(
                self, tr('partial_fail'),
                tr('rotate_partial_fail', ok=ok_count, fail=len(fail_paths),
                   paths='\n'.join(fail_paths[:5])),
            )
        elif ok_count:
            direction = tr('rotate_left_dir') if degrees > 0 else tr('rotate_right_dir')
            self.status_label.setText(tr('rotate_ok', dir=direction, n=ok_count))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        folders = [u.toLocalFile() for u in event.mimeData().urls() if validate_folder_path(u.toLocalFile())]
        if folders:
            self._add_folders(folders)
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self._remove_active_folder()
            event.accept()
        else:
            super().keyPressEvent(event)

    def open_folder_dialog(self):
        start = self._last_folder_dir
        if not Path(start).exists():
            start = str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, tr('select_folder'), start)
        if folder:
            self._last_folder_dir = folder
            save_last_folder_dir(folder)
            self._add_folders([folder])

    def _add_folders(self, folders: list):
        was_empty = self.folder_manager.get_folder_count() == 0
        added = 0
        for path in folders:
            if self.folder_manager.get_folder_count() >= MAX_FOLDERS:
                QMessageBox.warning(self, tr('tip'), tr('max_folders', n=MAX_FOLDERS))
                break
            if self.folder_manager.add_folder(path):
                added += 1
                self.folder_manager.set_active_folder_by_path(path)
        if added:
            if was_empty:
                self.single_view.reset_thumb_scale()
                self.multi_view.reset_thumb_scale()
            self._sync_mode_to_folder_count()
            self._schedule_workspace_save()
        elif folders:
            QMessageBox.warning(self, tr('error'), tr('load_folder_failed'))

    def _remove_folder(self, folder_path: str):
        if self.folder_manager.remove_folder(folder_path):
            self.selected_images = [i for i in self.selected_images
                                    if not i.path.startswith(folder_path + '/') and Path(i.path).parent != Path(folder_path)]
            if self.folder_manager.get_folder_count() == 0:
                self.folder_manager.active_folder_index = 0
            self._sync_mode_to_folder_count()
            self._schedule_workspace_save()

    def _reorder_folders(self, from_index: int, to_index: int):
        if from_index == to_index:
            return
        saved_paths = {i.path for i in self.selected_images}
        if not self.folder_manager.reorder_folders(from_index, to_index):
            return
        QTimer.singleShot(0, lambda paths=saved_paths: self._apply_folder_reorder(paths))
        self._schedule_workspace_save()

    def _apply_folder_reorder(self, saved_paths: set):
        self.update_display()
        if not saved_paths:
            return
        if self.stack.currentIndex() == 2:
            self.multi_view.selected = saved_paths
            self.multi_view._refresh_selection()
            self.selected_images = self.multi_view.get_selected()
            self._on_selection_changed(self.selected_images)
        elif self.stack.currentIndex() == 1:
            self.single_view.selected = saved_paths
            self.single_view._refresh_selection()
            self.selected_images = self.single_view.get_selected()
            self._on_selection_changed(self.selected_images)

    def _remove_active_folder(self):
        path = self.folder_sidebar.get_active_path()
        if path:
            self._remove_folder(path)
        elif self.folder_manager.get_folder_count() > 0:
            self._remove_folder(self.folder_manager.folders[0].path)

    def clear_folders(self):
        if self.folder_manager.get_folder_count() == 0:
            return
        if QMessageBox.question(self, tr('confirm'), tr('clear_folders_confirm')) == QMessageBox.StandardButton.Yes:
            self.folder_manager.clear_folders()
            self.selected_images.clear()
            self._sync_mode_to_folder_count()
            self._schedule_workspace_save()

    def _on_folder_selected(self, folder_path: str):
        self.folder_manager.set_active_folder_by_path(folder_path)
        if self.folder_manager.mode != 'single':
            self.switch_mode('single')
        else:
            self.update_display()

    def _auto_mode_for_folder_count(self) -> str:
        """Choose browse mode from loaded folder count."""
        return 'multi' if self.folder_manager.get_folder_count() > 1 else 'single'

    def _sync_mode_to_folder_count(self):
        """Auto-switch after folder add/remove: 1→single, 2+→multi."""
        self.switch_mode(self._auto_mode_for_folder_count())

    def toggle_compare_mode(self):
        new_mode = 'multi' if self.folder_manager.mode == 'single' else 'single'
        self.switch_mode(new_mode)

    def switch_mode(self, mode: str):
        self.folder_manager.mode = mode
        if hasattr(self, 'mode_switch') and self.mode_switch.mode() != mode:
            self.mode_switch.set_mode(mode, animate=True, emit=False)
        self.update_display()
        self._schedule_workspace_save()

    def switch_grid_align(self, align: str):
        if not self.folder_manager.set_grid_align(align):
            return
        if hasattr(self, 'align_switch') and self.align_switch.align() != align:
            self.align_switch.set_align(align, animate=True, emit=False)
        self.compare_row_index = 0
        self.update_display()
        self._schedule_workspace_save()

    def _update_align_switch_state(self):
        """Align switch always visible; enabled only in multi mode with ≥2 columns."""
        if not hasattr(self, 'align_switch'):
            return
        enabled = (
            self.folder_manager.mode == 'multi'
            and self.folder_manager.get_folder_count() >= 2
        )
        self.align_switch.setEnabled(enabled)
        if enabled:
            self.align_switch.setToolTip(tr('align_tip_enabled'))
        else:
            self.align_switch.setToolTip(tr('align_tip_disabled'))

    def update_display(self):
        folders = self.folder_manager.folders
        active = self.folder_manager.get_active_folder()
        active_path = active.path if active else None

        folder_stats = {}
        for f in folders:
            visible = self.folder_manager.get_visible_images(f)
            folder_stats[f.path] = (
                len(visible),
                sum(img.file_size for img in visible),
                len(f.images) - len(visible),
            )
        self.folder_sidebar.set_folders(folders, active_path, folder_stats)

        count = len(folders)
        if count == 0:
            self.stack.setCurrentIndex(0)
            self.center_title.setText(tr('title_drop_hint'))
        elif self.folder_manager.mode == 'single':
            self.stack.setCurrentIndex(1)
            af = self.folder_manager.get_active_folder()
            if af:
                visible = self.folder_manager.get_visible_images(af)
                self.single_view.set_images(visible, af.name)
                self.center_title.setText(tr('title_single', name=af.name, n=len(visible)))
            else:
                self.single_view.set_images([])
        else:
            self.stack.setCurrentIndex(2)
            names = [f.name for f in folders]
            paths = [f.path for f in folders]
            counts = [len(self.folder_manager.get_visible_images(f)) for f in folders]
            grid = self.folder_manager.get_images_grid()
            self.multi_view.set_grid(names, paths, counts, grid)
            align_label = tr('align_index') if self.folder_manager.grid_align == 'index' else tr('align_name')
            self.center_title.setText(
                tr('title_multi', cols=count, rows=len(grid), align=align_label),
            )

        self._update_align_switch_state()
        self._update_thumb_zoom_bar()
        self._update_status()

    def _active_grid_view(self):
        idx = self.stack.currentIndex()
        if idx == 1:
            return self.single_view
        if idx == 2:
            return self.multi_view
        return None

    def _update_thumb_zoom_bar(self):
        visible = self.stack.currentIndex() != 0
        self.thumb_zoom_widget.setVisible(visible)
        if visible:
            view = self._active_grid_view()
            if view:
                self._sync_thumb_scale_slider(view.get_thumb_scale())

    def _sync_thumb_scale_slider(self, scale: float):
        sync_fluent_slider(self.thumb_scale_slider, thumb_scale_to_slider_index(scale))
        self.thumb_scale_value.setText(f"{int(scale * 100)}%")

    def _on_thumb_scale_slider(self, index: int):
        scale = slider_index_to_thumb_scale(index)
        self.thumb_scale_value.setText(f"{int(scale * 100)}%")
        self.single_view.set_thumb_scale(scale, emit=False)
        self.multi_view.set_thumb_scale(scale, emit=False)

    def _on_view_thumb_scale_changed(self, scale: float):
        self._sync_thumb_scale_slider(scale)
        sender = self.sender()
        other = self.multi_view if sender is self.single_view else self.single_view
        if abs(other.get_thumb_scale() - scale) > 0.01:
            other.set_thumb_scale(scale, emit=False)

    def _on_selection_changed(self, images: List[ImageInfo]):
        self.selected_images = images
        self.selection_label.setText(tr('status_selected_n', n=len(images)))
        self._update_status()

    def _update_status(self):
        total = sum(
            img.file_size
            for folder in self.folder_manager.folders
            for img in self.folder_manager.get_visible_images(folder)
        )
        sel_sz = sum(i.file_size for i in self.selected_images)
        sel_text = tr('status_sel_suffix', n=len(self.selected_images), size=format_file_size(sel_sz)) if self.selected_images else ""
        self.status_label.setText(tr(
            'status_bar',
            folders=self.folder_manager.get_folder_count(),
            files=self.folder_manager.get_total_images(),
            size=format_file_size(total),
            sel=sel_text,
        ))

    def _on_main_splitter_moved(self, _pos: int, _index: int):
        if hasattr(self, 'folder_sidebar'):
            self.folder_sidebar.update_name_elision()

    def _on_search(self, keyword: str):
        if not keyword.strip():
            self.update_display()
            return
        results = self.folder_manager.search_images(keyword.strip())
        self.stack.setCurrentIndex(1)
        self.single_view.set_images(results, tr('search_results'))
        self._update_thumb_zoom_bar()

    def _folder_for_image(self, path: str) -> Optional[FolderInfo]:
        for folder in self.folder_manager.folders:
            if any(img.path == path for img in folder.images):
                return folder
        return None

    def _order_selected_for_compare(
        self, selected: List[ImageInfo], columns: List[FolderInfo],
    ) -> List[ImageInfo]:
        """Order selection: keep all items, sort by folder then file order."""
        if not selected:
            return []

        folder_order = {f.path: i for i, f in enumerate(self.folder_manager.folders)}

        def sort_key(img: ImageInfo) -> tuple:
            folder = self._folder_for_image(img.path)
            if not folder:
                return (9999, 9999, img.path)
            f_idx = folder_order.get(folder.path, 9999)
            img_idx = self._image_index_in_folder(img, folder)
            return (f_idx, img_idx if img_idx is not None else 9999, img.path)

        unique = {img.path: img for img in selected}
        return sorted(unique.values(), key=sort_key)

    def _find_group_index(self, groups: List[List[ImageInfo]], target: List[ImageInfo]) -> int:
        if not target:
            return 0
        sel = {i.path for i in target}
        for gi, group in enumerate(groups):
            if {i.path for i in group} == sel:
                return gi
        return 0

    def _image_index_in_folder(self, img: ImageInfo, folder: FolderInfo) -> Optional[int]:
        for i, item in enumerate(self.folder_manager.get_visible_images(folder)):
            if item.path == img.path:
                return i
        return None

    def _visible_images(self, folder: FolderInfo) -> List[ImageInfo]:
        return self.folder_manager.get_visible_images(folder)

    def _build_custom_stride_groups(
        self, ordered: List[ImageInfo], columns: List[FolderInfo],
    ) -> List[List[ImageInfo]]:
        """Build full group sequence from selection spacing (includes groups before selection)."""
        if len(ordered) < 2:
            return [ordered] if ordered else []

        slot_folders: List[FolderInfo] = []
        indices: List[int] = []
        for img in ordered:
            folder = self._folder_for_image(img.path)
            if not folder:
                return [ordered]
            idx = self._image_index_in_folder(img, folder)
            if idx is None:
                return [ordered]
            slot_folders.append(folder)
            indices.append(idx)

        # Multiple in one folder: step by spacing
        if len({f.path for f in slot_folders}) == 1:
            folder = slot_folders[0]
            i0 = indices[0]
            relative = [i - i0 for i in indices]
            stride = indices[-1] - i0 + 1
            if stride <= 0:
                return [ordered]

            visible = self._visible_images(folder)
            n = len(visible)
            k_lo = max(math.ceil((-i0 - rel) / stride) for rel in relative)
            k_hi = min(math.floor((n - 1 - i0 - rel) / stride) for rel in relative)
            if k_lo > k_hi:
                return [ordered]

            groups: List[List[ImageInfo]] = []
            for k in range(k_lo, k_hi + 1):
                base = i0 + k * stride
                groups.append([visible[base + rel] for rel in relative])
            return groups if groups else [ordered]

        # Cross-folder: advance each selected slot in sync (folder index + k)
        k_lo = max(-idx for idx in indices)
        k_hi = min(
            len(self._visible_images(folder)) - 1 - idx
            for folder, idx in zip(slot_folders, indices)
        )
        if k_lo > k_hi:
            return [ordered]

        groups = []
        for k in range(k_lo, k_hi + 1):
            group = [
                self._visible_images(folder)[start_idx + k]
                for folder, start_idx in zip(slot_folders, indices)
            ]
            groups.append(group)
        return groups if groups else [ordered]

    def _build_row_groups(self, columns: List[FolderInfo]) -> List[List[ImageInfo]]:
        """Build compare groups from name-aligned rows."""
        if self.folder_manager.get_folder_count() > 1 and columns:
            grid = self.folder_manager.get_images_grid()
            col_indices = [self.folder_manager.folders.index(f) for f in columns]
            groups = []
            for row in grid:
                imgs = [
                    row[i] for i in col_indices
                    if i < len(row) and row[i] is not None
                ]
                if imgs:
                    groups.append(imgs)
            return groups

        folder = columns[0] if columns else self.folder_manager.get_active_folder()
        if not folder:
            return []
        return [[img] for img in self._visible_images(folder)]

    def _find_matching_row(
        self, selected: List[ImageInfo], columns: List[FolderInfo],
    ) -> Optional[int]:
        """Return row index when selection exactly matches an aligned row, else None."""
        if not selected:
            return None
        sel_paths = {i.path for i in selected}
        for ri, group in enumerate(self._build_row_groups(columns)):
            if {i.path for i in group} == sel_paths:
                return ri
        return None

    def _resolve_compare_context(self) -> Tuple[List[List[ImageInfo]], int, bool]:
        """
        Resolve compare groups and current index.
        Returns (groups, index, row_navigation) — row_navigation True when Space/B can change rows.
        """
        columns = self._get_compare_columns()

        if self.selected_images:
            ordered = self._order_selected_for_compare(self.selected_images, columns)
            if not ordered:
                ordered = list(self.selected_images)

            # Single folder with one selection: still browse image-by-image
            if len(columns) == 1 and len(ordered) == 1:
                groups = self._build_row_groups(columns)
                folder = columns[0]
                idx_map = {img.path: i for i, img in enumerate(self._visible_images(folder))}
                idx = idx_map.get(ordered[0].path, 0)
                return groups, idx, True

            row_idx = self._find_matching_row(ordered, columns)
            if row_idx is not None:
                groups = self._build_row_groups(columns)
                return groups, row_idx, True

            groups = self._build_custom_stride_groups(ordered, columns)
            idx = self._find_group_index(groups, ordered)
            return groups, idx, len(groups) > 1

        groups = self._build_row_groups(columns)
        if not groups:
            return [], 0, True
        idx = min(self.compare_row_index, len(groups) - 1)
        return groups, idx, True

    def _get_compare_columns(self) -> List[FolderInfo]:
        """Folder columns in compare (from selection, or all if none selected)."""
        if self.selected_images:
            columns: List[FolderInfo] = []
            seen = set()
            for folder in self.folder_manager.folders:
                folder_paths = {img.path for img in self._visible_images(folder)}
                if any(img.path in folder_paths for img in self.selected_images):
                    if folder.path not in seen:
                        columns.append(folder)
                        seen.add(folder.path)
            if columns:
                return self._filter_compare_columns(columns)
        return self._filter_compare_columns(list(self.folder_manager.folders))

    def _filter_compare_columns(self, columns: List[FolderInfo]) -> List[FolderInfo]:
        if not self._compare_excluded_folders:
            return columns
        return [f for f in columns if f.path not in self._compare_excluded_folders]

    def _folder_path_for_image(self, image_path: str) -> Optional[str]:
        for folder in self.folder_manager.folders:
            if any(img.path == image_path for img in self._visible_images(folder)):
                return folder.path
        return None

    def _image_in_folder(self, img: ImageInfo, folder_path: str) -> bool:
        for folder in self.folder_manager.folders:
            if folder.path == folder_path:
                return any(i.path == img.path for i in self._visible_images(folder))
        return False

    def _remove_folder_from_compare_at_slot(self, slot_index: int):
        """Compare backspace: remove folder for column under mouse."""
        cw = self.compare_window
        if not cw or not cw.isVisible():
            return
        if slot_index < 0 or slot_index >= len(cw.canvas.slots):
            return

        columns = self._get_compare_columns()
        if len(columns) <= 1:
            cw.canvas.status_changed.emit(tr('compare_keep_one_folder'))
            return

        folder_path = self._folder_path_for_image(cw.canvas.slots[slot_index].info.path)
        if not folder_path:
            cw.canvas.status_changed.emit(tr('compare_folder_unknown'))
            return
        if folder_path not in {f.path for f in columns}:
            cw.canvas.status_changed.emit(tr('compare_not_independent_col'))
            return

        folder_name = next(
            (f.name for f in self.folder_manager.folders if f.path == folder_path),
            Path(folder_path).name,
        )
        self._compare_excluded_folders.add(folder_path)
        self.selected_images = [
            img for img in self.selected_images
            if not self._image_in_folder(img, folder_path)
        ]

        groups, idx, row_navigation = self._resolve_compare_context()
        if not groups:
            self._compare_excluded_folders.clear()
            cw.close()
            self.compare_window = None
            QMessageBox.information(self, tr('tip'), tr('removed_all_compare_cols'))
            return

        idx = min(cw.canvas.group_index, len(groups) - 1)
        self.compare_row_index = idx
        images = groups[idx]
        slot_pools = self._build_slot_pools(images)
        title = self._compare_window_title(images, idx, len(groups), row_navigation)

        if cw.remove_column_in_place(
            slot_index, images, groups, slot_pools, idx, title,
        ):
            cw.canvas.status_changed.emit(tr('compare_folder_removed', name=folder_name))
            self._sync_view_to_compare_row(idx, groups, row_navigation)
            return

        self._show_compare_dialog(images, groups, idx, row_navigation)
        if self.compare_window:
            self.compare_window.canvas.status_changed.emit(
                tr('compare_folder_removed', name=folder_name),
            )
        self._sync_view_to_compare_row(idx, groups, row_navigation)

    def _build_slot_pools(self, images: List[ImageInfo]) -> List[List[ImageInfo]]:
        if self.folder_manager.get_folder_count() > 1:
            path_to_folder: dict[str, FolderInfo] = {}
            for folder in self.folder_manager.folders:
                for img in self._visible_images(folder):
                    path_to_folder[img.path] = folder
            pools = []
            for img in images:
                folder = path_to_folder.get(img.path)
                pools.append(self._visible_images(folder) if folder else [img])
            return pools
        flat = self.folder_manager.get_images_flat()
        columns = self._get_compare_columns()
        if not flat and columns:
            flat = self._visible_images(columns[0])
        if not flat:
            return [[img] for img in images]
        return [flat for _ in images]

    def _build_compare_groups(self) -> List[List[ImageInfo]]:
        groups, _, _ = self._resolve_compare_context()
        return groups

    def _infer_compare_row_index(self) -> int:
        _, idx, _ = self._resolve_compare_context()
        return idx

    def _sync_view_to_compare_row(
        self, row_index: int, groups: List[List[ImageInfo]], row_navigation: bool = True,
    ):
        if row_index < 0 or row_index >= len(groups):
            return
        images = groups[row_index]
        paths = {i.path for i in images}
        if self.folder_manager.get_folder_count() > 1 and self.stack.currentIndex() == 2:
            self.multi_view.selected = paths
            self.multi_view._refresh_selection()
            if row_navigation and row_index < len(self.multi_view.cells):
                row_cells = self.multi_view.cells[row_index]
                first = next((c for c in row_cells if c.image_info and c.image_info.path in paths), None)
                if first:
                    self.multi_view.ensureWidgetVisible(first, 0, 80)
            else:
                for row_cells in self.multi_view.cells:
                    first = next(
                        (c for c in row_cells if c.image_info and c.image_info.path in paths), None,
                    )
                    if first:
                        self.multi_view.ensureWidgetVisible(first, 0, 80)
                        break
        elif self.stack.currentIndex() == 1:
            self.single_view.selected = paths
            self.single_view._refresh_selection()
            if row_navigation:
                for cell in self.single_view.cells:
                    if cell.image_info and cell.image_info.path in paths:
                        self.single_view.ensureWidgetVisible(cell, 0, 80)
        if row_navigation:
            self.selected_images = images
            self._on_selection_changed(images)

    def _compare_window_title(
        self, images: List[ImageInfo], idx: int, total: int, row_navigation: bool = True,
    ) -> str:
        if len(images) == 1:
            return tr('compare_title_view', name=images[0].name, idx=idx + 1, total=total)
        if not row_navigation or total <= 1:
            names = ", ".join(img.name[:16] for img in images[:3])
            suffix = "..." if len(images) > 3 else ""
            return tr('compare_title_names', n=len(images), names=names + suffix)
        columns = self._get_compare_columns()
        if len(columns) > 1:
            key = 'compare_title_row'
        elif len(images) > 1:
            key = 'compare_title_group'
        else:
            key = 'compare_title_images'
        return tr(key, n=len(images), idx=idx + 1, total=total)

    def _show_compare_dialog(
        self, images: List[ImageInfo], groups: List[List[ImageInfo]], idx: int,
        row_navigation: bool = True,
    ):
        slot_pools = self._build_slot_pools(images)
        cw = self.compare_window
        if cw and cw.isVisible():
            cw.close()
        self.compare_window = CompareDialog(
            images, self.folder_manager, self.image_loader,
            slot_pools=slot_pools, groups=groups,
        )
        self.compare_window.set_group_navigator(self.navigate_compare_group)
        self.compare_window.folder_column_remove_requested.connect(
            self._remove_folder_from_compare_at_slot,
        )
        self.compare_window.canvas.group_index = idx
        if idx < len(groups) and groups[idx] != images:
            self.compare_window.canvas._load_group(idx)
        self.compare_window.setWindowTitle(
            self._compare_window_title(images, idx, len(groups), row_navigation),
        )
        self.compare_window.show()
        place_window_on_screen(self.compare_window, self._selected_display_name())
        self.compare_window.retranslate_ui()
        self.compare_window.raise_()
        self.compare_window.activateWindow()
        self.compare_window.canvas.setFocus()

    def navigate_compare_group(self, delta: int = 0, force_open: bool = False):
        if self.folder_manager.get_total_images() == 0:
            if force_open:
                QMessageBox.warning(self, tr('tip'), tr('add_folders_first'))
            return

        cw = self.compare_window

        if cw and cw.isVisible() and delta != 0:
            groups = cw.canvas.groups
            if not groups or len(groups) <= 1:
                return
            idx = cw.canvas.group_index + delta
            row_navigation = True
        else:
            if delta != 0 and not force_open:
                return
            groups, idx, row_navigation = self._resolve_compare_context()
            if not groups:
                if force_open:
                    QMessageBox.warning(self, tr('tip'), tr('no_images_compare'))
                return

        idx = max(0, min(len(groups) - 1, idx))
        self.compare_row_index = idx
        self._schedule_workspace_save()
        images = groups[idx]

        if cw and cw.isVisible() and len(cw.canvas.slots) == len(images):
            cw.canvas.groups = groups
            cw.canvas.group_index = idx
            cw.canvas.exit_tab_preview()
            cw.canvas._load_group(idx)
            cw.setWindowTitle(
                self._compare_window_title(images, idx, len(groups), row_navigation),
            )
        elif force_open or delta == 0 or (cw and cw.isVisible()):
            self._show_compare_dialog(images, groups, idx, row_navigation)

        self._sync_view_to_compare_row(idx, groups, row_navigation)

    def _refresh_display_combo(self):
        """Refresh connected displays and preserve last selection when possible."""
        if not hasattr(self, 'display_combo'):
            return
        saved = load_compare_display_name()
        items = screen_items()
        current_name = self._selected_display_name()
        self.display_combo.blockSignals(True)
        self.display_combo.clear()
        self._display_screen_names = []
        select_idx = 0
        primary = QGuiApplication.primaryScreen()
        primary_name = primary.name() if primary else ''
        for i, (name, label) in enumerate(items):
            self.display_combo.addItem(label)
            self._display_screen_names.append(name)
            if saved and name == saved:
                select_idx = i
            elif not saved and name == primary_name:
                select_idx = i
        if current_name and current_name in self._display_screen_names:
            select_idx = self._display_screen_names.index(current_name)
        if not items:
            self.display_combo.addItem(tr('no_display'))
            self._display_screen_names.append('')
        self.display_combo.setCurrentIndex(select_idx)
        self.display_combo.setEnabled(bool(items))
        self.display_combo.blockSignals(False)

    def _on_display_combo_changed(self, index: int):
        if index < 0 or index >= len(self._display_screen_names):
            return
        save_compare_display_name(self._display_screen_names[index])

    def _selected_display_name(self) -> str:
        idx = self.display_combo.currentIndex() if hasattr(self, 'display_combo') else -1
        if 0 <= idx < len(self._display_screen_names):
            return self._display_screen_names[idx]
        return ''

    def open_compare_window(self):
        self._compare_excluded_folders.clear()
        self.navigate_compare_group(0, force_open=True)

    def _open_single_image_compare(self, image_info: ImageInfo):
        """Double-click single image: open compare view with one image."""
        self.selected_images = [image_info]
        self._refresh_view_selection([image_info])
        self.navigate_compare_group(0, force_open=True)

    def show_image_info(self, images: Optional[List[ImageInfo]] = None):
        imgs = images or self.selected_images
        if not imgs:
            if self.folder_manager.mode == 'single':
                flat = self.folder_manager.get_images_flat()
                imgs = flat[:1] if flat else []
            else:
                grid = self.folder_manager.get_images_grid()
                imgs = [row[0] for row in grid if row and row[0]][:1]

        if not imgs:
            QMessageBox.information(self, tr('image_info_title'), tr('select_image_info'))
            return

        lines = []
        for img in imgs[:8]:
            w, h = img.resolution
            lines.append(
                f"<b>{img.name}</b><br>"
                f"{tr('info_resolution')}: {w}×{h}<br>"
                f"{tr('info_size')}: {format_file_size(img.file_size)}<br>"
                f"{tr('info_path')}: {img.path}<br><br>"
            )
        QMessageBox.information(self, tr('image_info_title'), "".join(lines))

    def show_user_manual(self):
        dlg = UserManualDialog(self)
        dlg.exec()
