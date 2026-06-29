"""
Image loader - async loading and cache management.
"""
from typing import List, Optional, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass
import threading
import queue
from PIL import Image
import logging
from utils.image_utils import load_image_pil, get_image_info, create_thumbnail
from utils.cache import image_cache
from config import MAX_CACHE_IMAGES, THUMBNAIL_SIZE

logger = logging.getLogger(__name__)


@dataclass
class ImageInfo:
    """Image metadata."""
    path: str
    name: str
    resolution: Tuple[int, int]
    file_size: int
    modified_time: float
    thumbnail: Optional[Image.Image] = None
    full_image: Optional[Image.Image] = None

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if isinstance(other, ImageInfo):
            return self.path == other.path
        return False


class ImageLoader:
    """
    Async image loader with caching and batch preload.
    """

    def __init__(self, max_threads: int = 4):
        self.max_threads = max_threads
        self.load_queue = queue.Queue()
        self.image_cache = {}
        self.loading_threads = []
        self.running = False

    def load_image_info(
        self,
        image_path: str,
        *,
        with_thumbnail: bool = False,
    ) -> Optional[ImageInfo]:
        """
        Load metadata for one image. Batch import uses with_thumbnail=False;
        thumbnails load asynchronously in the grid.
        """
        try:
            info_dict = get_image_info(image_path)
            if not info_dict:
                return None

            thumbnail = None
            if with_thumbnail:
                thumbnail = image_cache.get_thumbnail(image_path)
                if thumbnail is None:
                    thumbnail = create_thumbnail(image_path, THUMBNAIL_SIZE)
                    if thumbnail:
                        image_cache.save_thumbnail(image_path, thumbnail)

            return ImageInfo(
                path=info_dict['path'],
                name=info_dict['name'],
                resolution=info_dict.get('resolution', (0, 0)),
                file_size=info_dict['size'],
                modified_time=info_dict['modified'],
                thumbnail=thumbnail,
            )
        except Exception as e:
            logger.error(f"Error loading image info for {image_path}: {e}")
            return None

    def load_full_image(self, image_path: str) -> Optional[Image.Image]:
        """
        Load full-resolution image.

        Args:
            image_path: Image path

        Returns:
            PIL Image or None
        """
        try:
            mtime = Path(image_path).stat().st_mtime
        except OSError:
            mtime = None

        cached = self.image_cache.get(image_path)
        if cached is not None:
            img, cached_mtime = cached
            if mtime is not None and cached_mtime == mtime:
                return img
            del self.image_cache[image_path]

        img = load_image_pil(image_path)
        if img is None:
            return None

        if len(self.image_cache) >= MAX_CACHE_IMAGES:
            oldest_key = next(iter(self.image_cache))
            del self.image_cache[oldest_key]

        self.image_cache[image_path] = (img, mtime)
        return img

    def invalidate_image(self, image_path: str):
        """Clear full-image cache after file change (e.g. rotation)."""
        self.image_cache.pop(image_path, None)

    def preload_images(self, image_paths: List[str], callback: Optional[Callable] = None):
        """
        Preload a set of images.

        Args:
            image_paths: Image path list
            callback: Called when each load finishes (path, status)
        """
        def load_worker():
            for path in image_paths:
                if not self.running:
                    break
                try:
                    self.load_full_image(path)
                    if callback:
                        callback(path, 'success')
                except Exception as e:
                    logger.error(f"Error preloading {path}: {e}")
                    if callback:
                        callback(path, 'error')

        thread = threading.Thread(target=load_worker, daemon=True)
        thread.start()
        self.loading_threads.append(thread)

    def clear_cache(self):
        """Clear in-memory image cache."""
        self.image_cache.clear()

    def shutdown(self):
        """Shut down loader threads."""
        self.running = False
        for thread in self.loading_threads:
            thread.join(timeout=1)
