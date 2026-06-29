"""
Folder manager - single/multi-folder comparison.
"""
from typing import List, Dict, Optional, Tuple, Set
from pathlib import Path
from dataclasses import dataclass
import logging
from utils.file_utils import get_image_files, validate_folder_path
from core.image_loader import ImageInfo, ImageLoader

logger = logging.getLogger(__name__)


@dataclass
class FolderInfo:
    """Folder metadata."""
    path: str
    name: str
    images: List[ImageInfo]

    def __len__(self):
        return len(self.images)


class FolderManager:
    """
    Manage images from one or more folders.
    Supports two modes:
    1. Single-folder - load from one folder
    2. Multi-folder - load from multiple folders, aligned by filename
    """

    def __init__(self, image_loader: Optional[ImageLoader] = None):
        self.folders: List[FolderInfo] = []
        self.image_loader = image_loader or ImageLoader()
        self.mode = 'single'  # 'single' or 'multi'
        self.grid_align = 'name'  # 'name' align rows by filename | 'index' top-align by order
        self.active_folder_index = 0
        # Images hidden in preview/compare (session only; files on disk unchanged)
        self._excluded_paths: Set[str] = set()

    def add_folder(self, folder_path: str) -> bool:
        """
        Add a folder.

        Args:
            folder_path: Folder path

        Returns:
            True on success
        """
        if not validate_folder_path(folder_path):
            logger.error(f"Invalid folder path: {folder_path}")
            return False

        folder = Path(folder_path)

        # Skip if already added
        if any(f.path == str(folder) for f in self.folders):
            logger.warning(f"Folder already added: {folder_path}")
            return False

        # Collect images in folder
        image_paths = get_image_files(folder_path)
        if not image_paths:
            logger.warning(f"No images found in folder: {folder_path}")
            return False

        # Load image metadata
        images = []
        for img_path in image_paths:
            img_info = self.image_loader.load_image_info(img_path)
            if img_info:
                images.append(img_info)

        if not images:
            logger.error(f"Failed to load any images from {folder_path}")
            return False

        # Build folder info
        folder_info = FolderInfo(
            path=str(folder),
            name=folder.name,
            images=images
        )

        self.folders.append(folder_info)
        logger.info(f"Folder added successfully: {folder_path} ({len(images)} images)")

        if len(self.folders) == 1:
            self.active_folder_index = 0
        self.mode = 'multi' if len(self.folders) > 1 else 'single'

        return True

    def remove_folder(self, folder_path: str) -> bool:
        """
        Remove a folder.

        Args:
            folder_path: Folder path

        Returns:
            True on success
        """
        for i, folder in enumerate(self.folders):
            if folder.path == folder_path:
                for img in folder.images:
                    self._excluded_paths.discard(img.path)
                self.folders.pop(i)
                if self.active_folder_index >= len(self.folders):
                    self.active_folder_index = max(0, len(self.folders) - 1)
                self.mode = 'multi' if len(self.folders) > 1 else 'single'
                logger.info(f"Folder removed: {folder_path}")
                return True
        return False

    def reorder_folders(self, from_index: int, to_index: int) -> bool:
        """Reorder folders."""
        n = len(self.folders)
        if n < 2 or from_index == to_index:
            return False
        if not (0 <= from_index < n and 0 <= to_index < n):
            return False

        active_path = self.folders[self.active_folder_index].path
        item = self.folders.pop(from_index)
        self.folders.insert(to_index, item)

        for i, folder in enumerate(self.folders):
            if folder.path == active_path:
                self.active_folder_index = i
                break
        logger.info(f"Folders reordered: {from_index} -> {to_index}")
        return True

    def reload_image(self, image_path: str) -> bool:
        """Reload metadata for one image (e.g. after rotation)."""
        for folder in self.folders:
            for i, img in enumerate(folder.images):
                if img.path == image_path:
                    new_info = self.image_loader.load_image_info(image_path)
                    if new_info:
                        folder.images[i] = new_info
                        return True
                    return False
        return False

    def set_active_folder_by_path(self, folder_path: str) -> bool:
        for i, folder in enumerate(self.folders):
            if folder.path == folder_path:
                self.active_folder_index = i
                return True
        return False

    def set_active_folder_index(self, index: int) -> bool:
        if 0 <= index < len(self.folders):
            self.active_folder_index = index
            return True
        return False

    def get_active_folder(self) -> Optional[FolderInfo]:
        if not self.folders:
            return None
        idx = max(0, min(self.active_folder_index, len(self.folders) - 1))
        return self.folders[idx]

    def clear_folders(self):
        """Clear all folders."""
        self.folders.clear()
        self.mode = 'single'
        self.active_folder_index = 0
        self._excluded_paths.clear()

    def is_excluded(self, image_path: str) -> bool:
        return image_path in self._excluded_paths

    def exclude_image(self, image_path: str) -> bool:
        """Hide image in preview/compare without deleting the file."""
        if not self.get_image_by_path(image_path):
            return False
        self._excluded_paths.add(image_path)
        return True

    def restore_image(self, image_path: str) -> bool:
        if image_path not in self._excluded_paths:
            return False
        self._excluded_paths.discard(image_path)
        return True

    def restore_folder_hidden(self, folder_path: str) -> int:
        """Restore all hidden images in a folder; returns count restored."""
        folder = next((f for f in self.folders if f.path == folder_path), None)
        if not folder:
            return 0
        restored = 0
        for img in folder.images:
            if img.path in self._excluded_paths:
                self._excluded_paths.discard(img.path)
                restored += 1
        return restored

    def get_excluded_count_for_folder(self, folder_path: str) -> int:
        folder = next((f for f in self.folders if f.path == folder_path), None)
        if not folder:
            return 0
        return sum(1 for img in folder.images if img.path in self._excluded_paths)

    def get_visible_images(self, folder: FolderInfo) -> List[ImageInfo]:
        return [img for img in folder.images if img.path not in self._excluded_paths]

    def get_visible_images_flat(self, folder_index: Optional[int] = None) -> List[ImageInfo]:
        if not self.folders:
            return []
        idx = folder_index if folder_index is not None else self.active_folder_index
        idx = max(0, min(idx, len(self.folders) - 1))
        return self.get_visible_images(self.folders[idx])

    def get_folder_count(self) -> int:
        """Return folder count."""
        return len(self.folders)

    def get_total_images(self) -> int:
        """Return total visible images in preview."""
        return sum(len(self.get_visible_images(f)) for f in self.folders)

    def get_images_flat(self, folder_index: Optional[int] = None) -> List[ImageInfo]:
        """
        Flat image list (single-folder mode).
        Defaults to the active folder.
        """
        if not self.folders:
            return []
        idx = folder_index if folder_index is not None else self.active_folder_index
        idx = max(0, min(idx, len(self.folders) - 1))
        return self.get_visible_images_flat(folder_index)

    def set_grid_align(self, align: str) -> bool:
        if align not in ('name', 'index'):
            return False
        self.grid_align = align
        return True

    def get_images_grid(self) -> List[List[Optional[ImageInfo]]]:
        """
        Grid image list (multi-folder mode).

        grid_align='name': align same filenames to one row
        grid_align='index': each column top-aligned by folder order
        """
        if not self.folders:
            return []

        if len(self.folders) == 1:
            return [[img] for img in self.get_visible_images(self.folders[0])]

        if self.grid_align == 'index':
            columns = [self.get_visible_images(f) for f in self.folders]
            max_rows = max((len(col) for col in columns), default=0)
            return [
                [
                    columns[col_idx][row_idx] if row_idx < len(columns[col_idx]) else None
                    for col_idx in range(len(columns))
                ]
                for row_idx in range(max_rows)
            ]

        folder_image_names = []
        for folder in self.folders:
            names = {
                Path(img.path).stem: img
                for img in self.get_visible_images(folder)
            }
            folder_image_names.append(names)

        # Collect all unique image names
        all_names = set()
        for names_dict in folder_image_names:
            all_names.update(names_dict.keys())

        # Sort by name
        sorted_names = sorted(all_names)

        # Build grid
        grid = []
        for name in sorted_names:
            row = []
            for names_dict in folder_image_names:
                if name in names_dict:
                    row.append(names_dict[name])
                else:
                    # Missing image: placeholder
                    row.append(None)
            grid.append(row)

        return grid

    def get_folder_info(self, index: int) -> Optional[FolderInfo]:
        """
        Get folder info by index.

        Args:
            index: Folder index

        Returns:
            FolderInfo or None
        """
        if 0 <= index < len(self.folders):
            return self.folders[index]
        return None

    def get_image_by_path(self, image_path: str) -> Optional[ImageInfo]:
        """
        Get ImageInfo by path.

        Args:
            image_path: Image path

        Returns:
            ImageInfo or None
        """
        for folder in self.folders:
            for img in folder.images:
                if img.path == image_path:
                    return img
        return None

    def search_images(self, keyword: str) -> List[ImageInfo]:
        """
        Search images by keyword.

        Args:
            keyword: Search term

        Returns:
            Matching ImageInfo list
        """
        results = []
        keyword_lower = keyword.lower()
        for folder in self.folders:
            for img in self.get_visible_images(folder):
                if keyword_lower in img.name.lower():
                    results.append(img)
        return results

    def __len__(self):
        return len(self.folders)

    def __getitem__(self, index: int) -> Optional[FolderInfo]:
        if 0 <= index < len(self.folders):
            return self.folders[index]
        return None
