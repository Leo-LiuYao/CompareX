"""
Image cache system.
"""
import os
from pathlib import Path
from typing import Optional, Dict
from PIL import Image
import hashlib
import logging
import threading
from config import CACHE_DIR, THUMBNAIL_SIZE, MAX_CACHE_IMAGES

logger = logging.getLogger(__name__)


class ImageCache:
    """Thumbnail and metadata cache manager."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_cache_dir = self.cache_dir / 'thumbnails'
        self.thumbnail_cache_dir.mkdir(exist_ok=True)
        self.metadata_cache: Dict = {}
        self._lock = threading.Lock()

    def get_cache_key(self, image_path: str) -> str:
        """
        Generate cache key.

        Args:
            image_path: Image path

        Returns:
            Cache key (hash of file path)
        """
        path_hash = hashlib.md5(image_path.encode()).hexdigest()
        filename = Path(image_path).stem
        return f"{filename}_{path_hash}"

    def get_thumbnail_path(self, image_path: str) -> Path:
        """
        Thumbnail cache file path.

        Args:
            image_path: Original image path

        Returns:
            Cache path
        """
        cache_key = self.get_cache_key(image_path)
        return self.thumbnail_cache_dir / f"{cache_key}.png"

    def save_thumbnail(self, image_path: str, thumbnail: Image.Image) -> bool:
        """
        Save thumbnail to cache.

        Args:
            image_path: Original image path
            thumbnail: PIL thumbnail

        Returns:
            True on success
        """
        try:
            with self._lock:
                cache_path = self.get_thumbnail_path(image_path)
                thumbnail.save(cache_path, 'PNG')
            return True
        except Exception as e:
            logger.error(f"Error saving thumbnail cache: {e}")
            return False

    def get_thumbnail(self, image_path: str) -> Optional[Image.Image]:
        """
        Load thumbnail from cache (hit when source file is not newer).
        """
        try:
            with self._lock:
                cache_path = self.get_thumbnail_path(image_path)
                if not cache_path.exists():
                    return None
                src_mtime = Path(image_path).stat().st_mtime
                if cache_path.stat().st_mtime < src_mtime:
                    return None
                with Image.open(cache_path) as im:
                    return im.copy()
        except Exception as e:
            logger.error(f"Error loading thumbnail from cache: {e}")
        return None

    def invalidate_thumbnail(self, image_path: str):
        try:
            cache_path = self.get_thumbnail_path(image_path)
            if cache_path.exists():
                cache_path.unlink()
        except Exception as e:
            logger.error(f"Error invalidating thumbnail cache: {e}")

    def clear_cache(self):
        """Clear all cached thumbnails."""
        try:
            import shutil
            shutil.rmtree(self.thumbnail_cache_dir)
            self.thumbnail_cache_dir.mkdir(exist_ok=True)
            self.metadata_cache.clear()
            logger.info("Cache cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

    def get_cache_size(self) -> int:
        """
        Total cache size in bytes.

        Returns:
            Total size
        """
        try:
            total = 0
            for file in self.thumbnail_cache_dir.rglob('*'):
                if file.is_file():
                    total += file.stat().st_size
            return total
        except Exception:
            return 0


# Global cache instance
image_cache = ImageCache()
