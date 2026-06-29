"""
File and path utilities.
"""
import os
from pathlib import Path
from typing import List, Tuple
from config import SUPPORTED_FORMATS


def get_image_files(folder_path: str, recursive: bool = False) -> List[str]:
    """
    List image files in a folder.

    Args:
        folder_path: Folder path
        recursive: Search subfolders

    Returns:
        Sorted image path list
    """
    folder = Path(folder_path)
    if not folder.exists():
        return []

    pattern = '**/*' if recursive else '*'
    images = []

    for ext in SUPPORTED_FORMATS:
        images.extend(folder.glob(f'{pattern}{ext}'))
        images.extend(folder.glob(f'{pattern}{ext.upper()}'))

    # Sort by filename
    return sorted([str(p) for p in images if p.is_file()])


def get_folder_structure(folder_path: str) -> dict:
    """
    Folder structure summary.

    Args:
        folder_path: Folder path

    Returns:
        Structure dict
    """
    folder = Path(folder_path)
    if not folder.exists():
        return {}

    structure = {
        'name': folder.name,
        'path': str(folder),
        'images': get_image_files(folder_path),
        'subfolders': []
    }

    # Subfolders
    try:
        for item in sorted(folder.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                structure['subfolders'].append({
                    'name': item.name,
                    'path': str(item),
                    'images': get_image_files(str(item))
                })
    except PermissionError:
        pass

    return structure


def validate_folder_path(path: str) -> bool:
    """
    Check folder path is valid.

    Args:
        path: Folder path

    Returns:
        True if valid directory
    """
    try:
        folder = Path(path)
        return folder.exists() and folder.is_dir()
    except Exception:
        return False


def validate_image_path(path: str) -> bool:
    """
    Check image path is valid.

    Args:
        path: Image file path

    Returns:
        True if valid image file
    """
    try:
        path_obj = Path(path)
        return path_obj.exists() and path_obj.suffix.lower() in SUPPORTED_FORMATS
    except Exception:
        return False


def get_relative_path(file_path: str, base_path: str) -> str:
    """
    Relative path from base.

    Args:
        file_path: Full file path
        base_path: Base directory

    Returns:
        Relative path string
    """
    try:
        return str(Path(file_path).relative_to(Path(base_path)))
    except ValueError:
        return file_path


def format_file_size(size_bytes: int) -> str:
    """
    Human-readable file size.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"
