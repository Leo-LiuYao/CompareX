"""
Image processing utilities.
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict
from PIL import Image, ImageDraw
import logging

logger = logging.getLogger(__name__)


def load_image_cv2(image_path: str) -> Optional[np.ndarray]:
    """
    Load image with OpenCV.

    Args:
        image_path: Image path

    Returns:
        BGR array, or None on failure
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            logger.warning(f"Failed to load image: {image_path}")
            return None
        return img
    except Exception as e:
        logger.error(f"Error loading image {image_path}: {e}")
        return None


def load_image_pil(image_path: str) -> Optional[Image.Image]:
    """
    Load image with PIL.

    Args:
        image_path: Image path

    Returns:
        PIL Image, or None on failure
    """
    try:
        return Image.open(image_path)
    except Exception as e:
        logger.error(f"Error loading image with PIL {image_path}: {e}")
        return None


def get_image_resolution(image_path: str) -> Optional[Tuple[int, int]]:
    """
    Get image resolution.

    Args:
        image_path: Image path

    Returns:
        (width, height), or None on failure
    """
    try:
        img = load_image_pil(image_path)
        if img is None:
            return None
        return img.size
    except Exception as e:
        logger.error(f"Error getting resolution for {image_path}: {e}")
        return None


def get_image_info(image_path: str) -> Dict:
    """
    Read image metadata from headers only (no pixel decode; faster for large imports).
    """
    try:
        path = Path(image_path)
        st = path.stat()
        info = {
            'path': str(path),
            'name': path.name,
            'size': st.st_size,
            'modified': st.st_mtime,
        }
        with Image.open(image_path) as img:
            info['resolution'] = img.size
            info['format'] = img.format
            info['mode'] = img.mode
        return info
    except Exception as e:
        logger.error(f"Error getting info for {image_path}: {e}")
        return {}


def rotate_image_file(image_path: str, degrees: int) -> bool:
    """
    Rotate image in place. degrees is PIL convention: positive = counter-clockwise.
    """
    try:
        path = Path(image_path)
        img = load_image_pil(image_path)
        if img is None:
            return False
        rotated = img.rotate(degrees, expand=True, resample=Image.Resampling.BICUBIC)
        suffix = path.suffix.lower()
        save_img = rotated
        if suffix in ('.jpg', '.jpeg') and save_img.mode in ('RGBA', 'P', 'LA'):
            save_img = rotated.convert('RGB')
        save_kwargs = {}
        if suffix in ('.jpg', '.jpeg'):
            save_kwargs = {'quality': 95, 'subsampling': 0}
        elif suffix == '.png':
            save_kwargs = {'compress_level': 1}
        save_img.save(path, **save_kwargs)
        img.close()
        if rotated is not save_img:
            rotated.close()
        return True
    except Exception as e:
        logger.error(f"Error rotating image {image_path}: {e}")
        return False


def create_thumbnail(image_path: str, size: Tuple[int, int]) -> Optional[Image.Image]:
    """
    Create thumbnail. JPEG etc. use draft downscale when possible to avoid full decode.
    """
    try:
        max_dim = max(size)
        with Image.open(image_path) as img:
            if hasattr(img, 'draft'):
                img.draft('RGB', (max_dim, max_dim))
            img.load()
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            thumb = img.copy()
        thumb.thumbnail(size, Image.Resampling.LANCZOS)
        return thumb
    except Exception as e:
        logger.error(f"Error creating thumbnail for {image_path}: {e}")
        return None


def crop_image(image_path: str, roi: Tuple[int, int, int, int]) -> Optional[Image.Image]:
    """
    Crop image.

    Args:
        image_path: Image path
        roi: Region (x, y, width, height)

    Returns:
        Cropped PIL Image
    """
    try:
        img = load_image_pil(image_path)
        if img is None:
            return None

        x, y, w, h = roi
        # PIL crop uses (left, top, right, bottom)
        return img.crop((x, y, x + w, y + h))
    except Exception as e:
        logger.error(f"Error cropping image {image_path}: {e}")
        return None


def crop_image_shaped(
    image_path: str,
    roi: Tuple[int, int, int, int],
    shape: str = 'rect',
) -> Optional[Image.Image]:
    """Crop with shape: rect / square / circle."""
    try:
        cropped = crop_image(image_path, roi)
        if cropped is None:
            return None
        if shape != 'circle':
            return cropped

        x, y, w, h = roi
        if w <= 0 or h <= 0:
            return None
        if cropped.mode != 'RGBA':
            cropped = cropped.convert('RGBA')
        mask = Image.new('L', (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, w - 1, h - 1), fill=255)
        cropped.putalpha(mask)
        return cropped
    except Exception as e:
        logger.error(f"Error cropping shaped image {image_path}: {e}")
        return None


def _align_rgb_arrays(img1: np.ndarray, img2: np.ndarray) -> Tuple[np.ndarray, np.ndarray, int, int]:
    h = min(img1.shape[0], img2.shape[0])
    w = min(img1.shape[1], img2.shape[1])
    f1 = img1[:h, :w, :3].astype(np.float32)
    f2 = img2[:h, :w, :3].astype(np.float32)
    return f1, f2, w, h


def compute_scalar_diff(f1: np.ndarray, f2: np.ndarray, method: str) -> np.ndarray:
    if method == 'euclidean':
        return np.sqrt(np.sum((f1 - f2) ** 2, axis=2))
    if method == 'l1':
        return np.sum(np.abs(f1 - f2), axis=2)
    if method == 'mse':
        return np.mean((f1 - f2) ** 2, axis=2)
    if method == 'abs_subtract':
        return np.mean(np.abs(f1 - f2), axis=2)
    if method == 'max_abs':
        return np.max(np.abs(f1 - f2), axis=2)
    return np.sqrt(np.sum((f1 - f2) ** 2, axis=2))


DIFF_METHODS = (
    ('euclidean', '欧式距离 L2'),
    ('l1', 'L1 曼哈顿'),
    ('mse', '均方误差 MSE'),
    ('abs_subtract', '绝对差 |A−B|'),
    ('max_abs', '通道最大差'),
)


def compute_diff_map(
    img1: np.ndarray,
    img2: np.ndarray,
    method: str = 'euclidean',
    sensitivity: float = 0.5,
) -> Dict:
    """Compute diff heatmap between two images (Beyond Compare style, with sensitivity)."""
    try:
        f1, f2, w, h = _align_rgb_arrays(img1, img2)
        diff = compute_scalar_diff(f1, f2, method)
        max_val = float(diff.max()) if diff.max() > 0 else 1.0
        sens = max(0.0, min(1.0, sensitivity))
        threshold = max_val * (1.0 - sens * 0.9)
        diff_vis = np.clip((diff - threshold) / (max_val - threshold + 1e-6), 0, 1)
        diff_uint8 = (diff_vis * 255).astype(np.uint8)
        heatmap_bgr = cv2.applyColorMap(diff_uint8, cv2.COLORMAP_JET)
        heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)
        return {
            'heatmap_rgb': heatmap_rgb,
            'heatmap_bgr': heatmap_bgr,
            'mean_diff': float(diff.mean()),
            'max_diff': max_val,
            'min_diff': float(diff.min()),
            'std_diff': float(diff.std()),
            'diff_pct': float((diff > threshold).sum() / diff.size * 100),
            'size': (w, h),
            'threshold': threshold,
        }
    except Exception as e:
        logger.error(f"Error computing diff map: {e}")
        return {}


def compute_pixel_diff(img1_path: str, img2_path: str, method: str = 'euclidean') -> Dict:
    """
    Pixel difference between two images.

    Args:
        img1_path: First image path
        img2_path: Second image path
        method: Method ('euclidean', 'l1', 'mse')

    Returns:
        Statistics dict
    """
    try:
        img1 = load_image_cv2(img1_path)
        img2 = load_image_cv2(img2_path)

        if img1 is None or img2 is None:
            return {}

        result = compute_diff_map(
            cv2.cvtColor(img1, cv2.COLOR_BGR2RGB),
            cv2.cvtColor(img2, cv2.COLOR_BGR2RGB),
            method=method,
            sensitivity=0.0,
        )
        if not result:
            return {}
        return {
            'mean_diff': result['mean_diff'],
            'max_diff': result['max_diff'],
            'min_diff': result['min_diff'],
            'std_diff': result['std_diff'],
            'heatmap': result['heatmap_bgr'],
            'diff_map': compute_scalar_diff(
                *_align_rgb_arrays(
                    cv2.cvtColor(img1, cv2.COLOR_BGR2RGB),
                    cv2.cvtColor(img2, cv2.COLOR_BGR2RGB),
                )[:2],
                method,
            ),
        }
    except Exception as e:
        logger.error(f"Error computing pixel diff: {e}")
        return {}


def compute_histogram(image_path: str, channels: Optional[list] = None) -> Dict:
    """
    Compute image histogram.

    Args:
        image_path: Image path
        channels: Channels to use ([0, 1, 2] = BGR)

    Returns:
        Histogram dict
    """
    try:
        img = load_image_cv2(image_path)
        if img is None:
            return {}

        if channels is None:
            channels = [0, 1, 2]  # BGR

        histograms = {}
        channel_names = ['Blue', 'Green', 'Red']

        for ch in channels:
            hist = cv2.calcHist([img], [ch], None, [256], [0, 256])
            histograms[channel_names[ch]] = hist.flatten().tolist()

        return histograms
    except Exception as e:
        logger.error(f"Error computing histogram: {e}")
        return {}


def resize_image(image_path: str, new_size: Tuple[int, int]) -> Optional[Image.Image]:
    """
    Resize image.

    Args:
        image_path: Image path
        new_size: (width, height)

    Returns:
        Resized PIL Image
    """
    try:
        img = load_image_pil(image_path)
        if img is None:
            return None

        return img.resize(new_size, Image.Resampling.LANCZOS)
    except Exception as e:
        logger.error(f"Error resizing image {image_path}: {e}")
        return None


def convert_color_space(image_path: str, target_space: str = 'RGB') -> Optional[Image.Image]:
    """
    Convert color space.

    Args:
        image_path: Image path
        target_space: Target mode ('RGB', 'RGBA', 'L', 'LAB', etc.)

    Returns:
        Converted PIL Image
    """
    try:
        img = load_image_pil(image_path)
        if img is None:
            return None

        if target_space == 'RGB' and img.mode != 'RGB':
            return img.convert('RGB')
        elif target_space == 'RGBA' and img.mode != 'RGBA':
            return img.convert('RGBA')
        elif target_space == 'L' and img.mode != 'L':
            return img.convert('L')

        return img
    except Exception as e:
        logger.error(f"Error converting color space: {e}")
        return None
