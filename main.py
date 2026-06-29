#!/usr/bin/env python3
"""
CompareX - Fluent-style UI built on PyQt6-Fluent-Widgets.
"""
import sys
from PyQt6.QtWidgets import QApplication
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from logger_config import setup_logging
from ui.fluent_integration import setup_fluent_app
from ui.app_state import load_language
from i18n import set_language
from ui.main_window import MainWindow
from config import APP_NAME, APP_ICON_PATH
from PyQt6.QtGui import QIcon

logger = setup_logging()


def main():
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        if APP_ICON_PATH.is_file():
            icon = QIcon(str(APP_ICON_PATH))
            app.setWindowIcon(icon)
        set_language(load_language())
        setup_fluent_app()

        window = MainWindow()
        window.showMaximized()
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Application failed to start: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
