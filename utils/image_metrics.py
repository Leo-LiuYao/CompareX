"""Image quality metrics: PSNR / SSIM (downscale for preview speed)."""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

METRIC_PSNR = 'psnr'
METRIC_SSIM = 'ssim'
ALL_METRICS = (METRIC_PSNR, METRIC_SSIM)
METRICS_PREVIEW_MAX_SIDE = 384
PSNR_CAP_DB = 99.99


def normalize_psnr(value: Optional[float]) -> Optional[float]:
    """When images are identical skimage returns inf; cap to a displayable value."""
    if value is None:
        return None
    if math.isinf(value) or math.isnan(value):
        return PSNR_CAP_DB
    return min(float(value), PSNR_CAP_DB)


def downscale_for_metrics(arr: np.ndarray, max_side: int = METRICS_PREVIEW_MAX_SIDE) -> np.ndarray:
    if arr is None or arr.size == 0:
        return arr
    h, w = arr.shape[:2]
    if max(h, w) <= max_side:
        return arr
    scale = max_side / max(h, w)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    if arr.ndim == 2:
        return cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_AREA)
    return cv2.resize(arr[:, :, :3], (nw, nh), interpolation=cv2.INTER_AREA)


def _align_rgb_uint8(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=2)
    if b.ndim == 2:
        b = np.stack([b, b, b], axis=2)
    if a.shape[2] == 4:
        a = a[:, :, :3]
    if b.shape[2] == 4:
        b = b[:, :, :3]
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    if h <= 0 or w <= 0:
        raise ValueError('invalid image size')
    return a[:h, :w].astype(np.uint8), b[:h, :w].astype(np.uint8)


def compute_psnr(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    try:
        img1, img2 = _align_rgb_uint8(a, b)
        if np.array_equal(img1, img2):
            return PSNR_CAP_DB
        from skimage.metrics import peak_signal_noise_ratio
        return normalize_psnr(float(peak_signal_noise_ratio(img1, img2, data_range=255)))
    except Exception as exc:
        logger.warning('PSNR failed: %s', exc)
        return None


def compute_ssim(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    try:
        img1, img2 = _align_rgb_uint8(a, b)
        from skimage.metrics import structural_similarity
        return float(structural_similarity(
            img1, img2, channel_axis=2, data_range=255,
        ))
    except Exception as exc:
        logger.warning('SSIM failed: %s', exc)
        return None


def compute_image_metrics(
    baseline: np.ndarray,
    target: np.ndarray,
    metrics: List[str],
    *,
    preview: bool = False,
) -> Dict[str, Optional[float]]:
    if preview:
        baseline = downscale_for_metrics(baseline)
        target = downscale_for_metrics(target)
    result: Dict[str, Optional[float]] = {}
    for key in metrics:
        if key == METRIC_PSNR:
            result[key] = compute_psnr(baseline, target)
        elif key == METRIC_SSIM:
            result[key] = compute_ssim(baseline, target)
    return result


def format_metric_value(key: str, value: Optional[float]) -> str:
    if value is None:
        return f'{key.upper()}: —'
    if key == METRIC_PSNR:
        value = normalize_psnr(value)
        if value is None:
            return 'PSNR: —'
        if value >= PSNR_CAP_DB - 0.01:
            from i18n import tr
            return tr('metrics_psnr_max')
        return f'PSNR: {value:.2f} dB'
    if key == METRIC_SSIM:
        return f'SSIM: {value:.4f}'
    return f'{key}: {value}'
