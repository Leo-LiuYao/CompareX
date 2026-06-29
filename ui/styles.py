"""UI stylesheets - Fluent via qfluentwidgets; custom areas supplemented here."""
from ui.theme import get_colors, is_dark_theme


def _build_stylesheet(colors: dict) -> str:
    dark = is_dark_theme()
    scroll_track = '#404040' if dark else '#D6D6D6'
    scroll_handle = '#858585' if dark else '#ADADAD'
    scroll_handle_hover = '#969696' if dark else '#969696'
    return f"""
    QSplitter::handle {{
        background-color: {colors['panel_border']};
        width: 1px;
    }}
    QMainWindow {{
        background-color: {colors['background']};
    }}
    QScrollBar:vertical {{
        background-color: {scroll_track};
        width: 10px;
        margin: 0;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {scroll_handle};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {scroll_handle_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
        background: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background-color: {scroll_track};
        height: 10px;
        margin: 0;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {scroll_handle};
        border-radius: 5px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {scroll_handle_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
        background: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
    """


def get_stylesheet() -> str:
    return _build_stylesheet(get_colors())


def get_dark_stylesheet() -> str:
    return get_stylesheet()
