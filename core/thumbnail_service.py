"""Thumbnail load queue (main-thread decode to avoid PIL/libjpeg crashes)."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer

from utils.cache import image_cache
from utils.image_utils import create_thumbnail


class ThumbnailService(QObject):
    """Global thumbnail queue: merge requests per path, decode one at a time on main thread."""

    _instance: Optional["ThumbnailService"] = None

    @classmethod
    def instance(cls) -> "ThumbnailService":
        if cls._instance is None:
            cls._instance = ThumbnailService()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._callbacks: Dict[str, List[Callable]] = {}
        self._queue: List[Tuple[str, Tuple[int, int]]] = []
        self._queued: set[str] = set()
        self._busy = False

    def request(
        self,
        path: str,
        size: Tuple[int, int],
        callback: Callable[[str, object], None],
    ):
        if not path:
            return

        cached = image_cache.get_thumbnail(path)
        if cached is not None:
            callback(path, cached)
            return

        self._callbacks.setdefault(path, []).append(callback)
        if path in self._queued:
            return
        self._queued.add(path)
        self._queue.append((path, size))
        if not self._busy:
            QTimer.singleShot(0, self._process_next)

    def _process_next(self):
        if self._busy or not self._queue:
            return
        self._busy = True
        path, size = self._queue.pop(0)
        self._queued.discard(path)

        thumb = None
        try:
            thumb = image_cache.get_thumbnail(path)
            if thumb is None:
                thumb = create_thumbnail(path, size)
                if thumb is not None:
                    image_cache.save_thumbnail(path, thumb)
                    thumb = thumb.copy()
        except Exception:
            thumb = None

        callbacks = self._callbacks.pop(path, [])
        for cb in callbacks:
            try:
                cb(path, thumb)
            except Exception:
                pass

        self._busy = False
        if self._queue:
            QTimer.singleShot(0, self._process_next)
