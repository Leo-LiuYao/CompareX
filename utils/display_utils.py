"""Multi-monitor detection and window placement."""
from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6.QtGui import QGuiApplication, QScreen
from PyQt6.QtWidgets import QWidget

from config import COMPARE_WINDOW_WIDTH, COMPARE_WINDOW_HEIGHT
from i18n import tr


def screen_items() -> List[Tuple[str, str]]:
    """Return list of (screen_name, display label)."""
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen()
    items: List[Tuple[str, str]] = []
    for i, screen in enumerate(screens):
        name = screen.name()
        geo = screen.availableGeometry()
        tag = tr('display_primary') if screen is primary else tr('display_n', n=i + 1)
        label = f'{tag} · {geo.width()}×{geo.height()}'
        if name and name not in label:
            short = name if len(name) <= 18 else name[:16] + '…'
            label = f'{label} ({short})'
        items.append((name, label))
    return items


def resolve_screen(screen_name: Optional[str] = None) -> Optional[QScreen]:
    screens = QGuiApplication.screens()
    if not screens:
        return None
    if screen_name:
        for screen in screens:
            if screen.name() == screen_name:
                return screen
    return QGuiApplication.primaryScreen() or screens[0]


def place_window_on_screen(
    window: QWidget,
    screen_name: Optional[str] = None,
    *,
    width: int = COMPARE_WINDOW_WIDTH,
    height: int = COMPARE_WINDOW_HEIGHT,
) -> None:
    """Center window on the given display."""
    screen = resolve_screen(screen_name)
    if screen is None:
        return
    ag = screen.availableGeometry()
    w = min(max(400, width), ag.width())
    h = min(max(300, height), ag.height())
    x = ag.x() + max(0, (ag.width() - w) // 2)
    y = ag.y() + max(0, (ag.height() - h) // 2)
    window.resize(w, h)
    window.setGeometry(x, y, w, h)
    handle = window.windowHandle()
    if handle is not None:
        handle.setScreen(screen)
