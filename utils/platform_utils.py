"""
Cross-platform utilities - Finder/Explorer, clipboard, etc.
"""
import logging
import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import Qt, QUrl, QTimer

logger = logging.getLogger(__name__)


def reveal_in_file_manager(path: str):
    """Reveal a file or folder in Finder / Explorer."""
    p = Path(path)
    target = str(p if p.exists() else p.parent)
    if sys.platform == 'darwin':
        subprocess.run(['open', '-R', target], check=False)
    elif sys.platform == 'win32':
        subprocess.run(['explorer', '/select,', target.replace('/', '\\')], check=False)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent if p.is_file() else p)))


def open_folder_in_file_manager(folder_path: str):
    p = Path(folder_path)
    if not p.is_dir():
        return
    if sys.platform == 'darwin':
        subprocess.run(['open', str(p)], check=False)
    elif sys.platform == 'win32':
        subprocess.run(['explorer', str(p)], check=False)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))


def copy_text_to_clipboard(text: str):
    QApplication.clipboard().setText(text)


def _macos_nswindow(window: QWidget):
    if sys.platform != 'darwin':
        return None
    wid = window.winId()
    if not wid:
        return None
    try:
        from ctypes import c_void_p

        import objc

        view = objc.objc_object(c_void_p=int(wid))
        return view.window()
    except Exception:
        return None


def is_macos_native_fullscreen(window: QWidget) -> bool:
    ns_window = _macos_nswindow(window)
    if ns_window is None:
        return False
    try:
        from AppKit import NSWindowStyleMaskFullScreen

        return bool(ns_window.styleMask() & NSWindowStyleMaskFullScreen)
    except Exception:
        return False


def is_window_fullscreen(window: QWidget) -> bool:
    if window.isFullScreen():
        return True
    if window.windowState() & Qt.WindowState.WindowFullScreen:
        return True
    return is_macos_native_fullscreen(window)


def exit_window_fullscreen(window: QWidget) -> bool:
    """Exit fullscreen. Returns True if fullscreen was active and was exited."""
    if is_macos_native_fullscreen(window):
        ns_window = _macos_nswindow(window)
        if ns_window is not None:
            try:
                ns_window.toggleFullScreen_(None)
                return True
            except Exception as exc:
                logger.debug('macOS exit fullscreen failed: %s', exc)
    if window.isFullScreen() or (window.windowState() & Qt.WindowState.WindowFullScreen):
        window.showNormal()
        return True
    return False


def enable_macos_native_fullscreen_button(window: QWidget) -> None:
    """macOS: green button enters native fullscreen (separate Space), not desktop maximize.

    Qt does not set NSWindowCollectionBehaviorFullScreenPrimary on QDialog by default;
    enable it explicitly via the native NSWindow.
    """
    if sys.platform != 'darwin':
        return
    wid = window.winId()
    if not wid:
        return
    try:
        from AppKit import NSWindowCollectionBehaviorFullScreenPrimary

        ns_window = _macos_nswindow(window)
        if ns_window is None:
            return
        behavior = ns_window.collectionBehavior()
        ns_window.setCollectionBehavior_(
            behavior | NSWindowCollectionBehaviorFullScreenPrimary,
        )
    except Exception as exc:
        logger.debug('macOS fullscreen button setup failed: %s', exc)


def schedule_macos_native_fullscreen_button(window: QWidget) -> None:
    """Apply macOS fullscreen button config after show (ensures winId is available)."""
    if sys.platform != 'darwin':
        return
    QTimer.singleShot(0, lambda: enable_macos_native_fullscreen_button(window))
