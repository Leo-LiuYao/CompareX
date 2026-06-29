"""
Comparison and analysis tools.
"""
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import logging
from PIL import Image, ImageDraw

from utils.image_utils import (
    compute_pixel_diff,
    compute_histogram,
    crop_image,
    crop_image_shaped,
    load_image_pil,
)
from core.image_loader import ImageInfo

logger = logging.getLogger(__name__)


@dataclass
class Rect:
    """Rectangle (x, y, width, height)."""
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self):
        if self.width < 0:
            self.x += self.width
            self.width = abs(self.width)
        if self.height < 0:
            self.y += self.height
            self.height = abs(self.height)

    def as_pil_box(self):
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class CropRegion:
    """Crop region (bounding rect + shape)."""
    rect: Rect
    shape: str = 'rect'  # rect | square | circle

class ComparisonTools:
    """Image comparison and analysis helpers."""

    @staticmethod
    def pixel_diff(image_path1: str, image_path2: str, method: str = 'euclidean') -> Dict:
        try:
            return compute_pixel_diff(image_path1, image_path2, method)
        except Exception as e:
            logger.error(f"Error in pixel_diff: {e}")
            return {}

    @staticmethod
    def crop_images(image_paths: List[str], roi: Rect) -> Dict[str, Optional[Any]]:
        results = {}
        for path in image_paths:
            try:
                cropped = crop_image(path, (roi.x, roi.y, roi.width, roi.height))
                results[path] = cropped
            except Exception as e:
                logger.error(f"Error cropping image {path}: {e}")
                results[path] = None
        return results

    @staticmethod
    def draw_red_crop_box(image_path: str, roi: Rect, shape: str = 'rect') -> Optional[Image.Image]:
        """Draw red crop outline on original at full resolution."""
        try:
            img = load_image_pil(image_path)
            if img is None:
                return None
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
            elif img.mode == 'RGB':
                img = img.convert('RGBA')

            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            box = roi.as_pil_box()
            line_w = max(2, min(img.size) // 200)
            if shape == 'circle':
                draw.ellipse(box, outline=(255, 0, 0, 255), width=line_w)
            else:
                draw.rectangle(box, outline=(255, 0, 0, 255), width=line_w)

            result = Image.alpha_composite(img, overlay)
            return result.convert('RGB')
        except Exception as e:
            logger.error(f"Error drawing crop box on {image_path}: {e}")
            return None

    @staticmethod
    def _save_pil_image(img: Image.Image, path: Path, suffix: str):
        if suffix.lower() in ('.jpg', '.jpeg'):
            save_img = img
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                save_img = bg
            elif img.mode != 'RGB':
                save_img = img.convert('RGB')
            save_img.save(str(path), quality=100, subsampling=0)
        else:
            save_img = img
            if img.mode not in ('RGB', 'RGBA'):
                save_img = img.convert('RGBA')
            if suffix.lower() == '.png':
                save_img.save(str(path), compress_level=1)
            else:
                save_img.save(str(path))

    @staticmethod
    def export_crops(
        images: List[ImageInfo],
        region: CropRegion,
        out_dir: str,
        is_multi_folder: bool,
        folder_name_map: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Export crops and marked originals.
        Single folder: name + name_crop / name_marked
        Multi folder: folder_name + name / folder_name_crop_name
        """
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        count = 0
        folder_name_map = folder_name_map or {}
        roi = region.rect
        shape = region.shape

        for img in images:
            path = Path(img.path)
            stem, suffix = path.stem, path.suffix or '.png'
            if shape == 'circle' and suffix.lower() in ('.jpg', '.jpeg'):
                crop_suffix = '.png'
            else:
                crop_suffix = suffix

            if is_multi_folder:
                folder = folder_name_map.get(img.path, 'folder')
                marked_name = f"{folder}_{img.name}"
                crop_name = f"{folder}_crop_{path.stem}{crop_suffix}"
            else:
                marked_name = f"{stem}_marked{suffix}"
                crop_name = f"{stem}_crop{crop_suffix}"

            cropped = crop_image_shaped(
                img.path, (roi.x, roi.y, roi.width, roi.height), shape
            )
            if cropped:
                ComparisonTools._save_pil_image(cropped, out / crop_name, crop_suffix)
                count += 1

            marked = ComparisonTools.draw_red_crop_box(img.path, roi, shape)
            if marked:
                ComparisonTools._save_pil_image(marked, out / marked_name, suffix)
                count += 1

        return count

    @staticmethod
    def get_histogram(image_path: str, channels: Optional[List[int]] = None) -> Dict:
        try:
            return compute_histogram(image_path, channels)
        except Exception as e:
            logger.error(f"Error computing histogram: {e}")
            return {}

    @staticmethod
    def compare_histograms(image_paths: List[str]) -> Dict:
        results = {}
        for path in image_paths:
            results[path] = ComparisonTools.get_histogram(path)
        return results

    @staticmethod
    def get_image_metadata(image_info: ImageInfo) -> Dict:
        return {
            'name': image_info.name,
            'path': image_info.path,
            'resolution': image_info.resolution,
            'file_size': image_info.file_size,
            'modified_time': image_info.modified_time,
        }

    @staticmethod
    def batch_crop(image_infos: List[ImageInfo], roi: Rect) -> Dict:
        return ComparisonTools.crop_images([img.path for img in image_infos], roi)
