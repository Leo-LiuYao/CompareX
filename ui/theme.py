"""Theme management - sync with PyQt6-Fluent-Widgets; follow macOS / system appearance."""
import json
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from config import CONFIG_DIR
from ui.fluent_integration import (
    DARK_FLUENT, LIGHT_FLUENT, apply_fluent_theme, get_fluent_colors,
)

THEME_FILE = CONFIG_DIR / 'theme.json'

DARK_COLORS = DARK_FLUENT
LIGHT_COLORS = LIGHT_FLUENT

_is_dark = True
_follow_system = True


def _read_theme_file() -> dict:
    try:
        if THEME_FILE.exists():
            return json.loads(THEME_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def _write_theme_file():
    THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
    THEME_FILE.write_text(
        json.dumps({'dark': _is_dark, 'follow_system': _follow_system}, ensure_ascii=False),
        encoding='utf-8',
    )


def system_prefers_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return _is_dark
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return _is_dark


def _load_persisted_settings():
    global _is_dark, _follow_system
    data = _read_theme_file()
    _follow_system = data.get('follow_system', True)
    _is_dark = data.get('dark', True)


_load_persisted_settings()


def init_theme_with_app():
    """Call after QApplication; resolve theme when following system."""
    global _is_dark
    if _follow_system:
        _is_dark = system_prefers_dark()
    apply_fluent_theme(_is_dark)


def follows_system() -> bool:
    return _follow_system


def set_follow_system(enabled: bool):
    global _follow_system, _is_dark
    _follow_system = enabled
    if enabled:
        _is_dark = system_prefers_dark()
        apply_fluent_theme(_is_dark)
    _write_theme_file()


def save_theme(is_dark: bool, *, follow_system: Optional[bool] = None):
    global _is_dark, _follow_system
    _is_dark = is_dark
    if follow_system is not None:
        _follow_system = follow_system
    elif follow_system is None:
        _follow_system = False
    apply_fluent_theme(_is_dark)
    _write_theme_file()


def apply_system_theme_if_following() -> bool:
    """On system appearance change; refresh if following system and return True."""
    global _is_dark
    if not _follow_system:
        return False
    _is_dark = system_prefers_dark()
    apply_fluent_theme(_is_dark)
    return True


def is_dark_theme() -> bool:
    return _is_dark


def get_colors() -> Dict[str, str]:
    apply_fluent_theme(_is_dark)
    return DARK_COLORS if _is_dark else LIGHT_COLORS
