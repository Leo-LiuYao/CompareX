"""Simple i18n: tr(key) returns the string for the current language."""
from __future__ import annotations

from typing import Callable, List

from i18n.messages import MESSAGES

_current_lang = 'zh'
_listeners: List[Callable[[], None]] = []


def language() -> str:
    return _current_lang


def set_language(lang: str) -> None:
    global _current_lang
    lang = 'en' if lang == 'en' else 'zh'
    if lang == _current_lang:
        return
    _current_lang = lang
    for cb in list(_listeners):
        try:
            cb()
        except Exception:
            pass


def register_listener(callback: Callable[[], None]) -> None:
    if callback not in _listeners:
        _listeners.append(callback)


def unregister_listener(callback: Callable[[], None]) -> None:
    if callback in _listeners:
        _listeners.remove(callback)


def tr(key: str, **kwargs) -> str:
    table = MESSAGES.get(_current_lang) or MESSAGES['zh']
    text = table.get(key, MESSAGES['zh'].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
