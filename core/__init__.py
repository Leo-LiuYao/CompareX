"""
Core package initialization.
"""
from .image_loader import ImageLoader, ImageInfo
from .folder_manager import FolderManager, FolderInfo
from .tools import ComparisonTools, Rect

__all__ = [
    'ImageLoader',
    'ImageInfo',
    'FolderManager',
    'FolderInfo',
    'ComparisonTools',
    'Rect',
]
