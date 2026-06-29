"""Batch metrics computation and CSV export (wide table: one row per compare row)."""
from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.image_loader import ImageInfo, ImageLoader
from utils.image_metrics import METRIC_PSNR, METRIC_SSIM, compute_image_metrics, normalize_psnr

logger = logging.getLogger(__name__)


def _load_rgb(loader: ImageLoader, path: str) -> Optional[np.ndarray]:
    pil = loader.load_full_image(path)
    if pil is None:
        return None
    try:
        if pil.mode == 'RGBA':
            arr = np.array(pil)
            return arr[:, :, :3] if arr.shape[2] == 4 else arr
        if pil.mode != 'RGB':
            pil = pil.convert('RGB')
        return np.array(pil)
    except OSError as exc:
        logger.warning('Failed to decode image %s: %s', path, exc)
        loader.invalidate_image(path)
        return None


def compute_current_group_metrics(
    slots_source: List[Optional[np.ndarray]],
    baseline_idx: int,
    metrics: Sequence[str],
    *,
    preview: bool = False,
) -> Dict[int, Dict[str, Optional[float]]]:
    out: Dict[int, Dict[str, Optional[float]]] = {}
    if baseline_idx < 0 or baseline_idx >= len(slots_source):
        return out
    base = slots_source[baseline_idx]
    if base is None:
        return out
    for i, arr in enumerate(slots_source):
        if i == baseline_idx or arr is None:
            continue
        out[i] = compute_image_metrics(base, arr, list(metrics), preview=preview)
    return out


def _col_key(label: str, index: int) -> str:
    safe = re.sub(r'[^\w\-]+', '_', label.strip())[:20].strip('_')
    return safe or f'col{index + 1}'


def build_metrics_table_rows(
    groups: List[List[ImageInfo]],
    baseline_idx: int,
    metrics: Sequence[str],
    image_loader: ImageLoader,
    folder_labels: Optional[List[str]] = None,
) -> Tuple[List[str], List[Dict[str, object]]]:
    """
    Wide table: one record per compare row.
    Columns: row | baseline_image | {col}_image | {col}_PSNR | {col}_SSIM ...
    Baseline column appears only in baseline_image; no metrics computed for it.
    """
    if not groups or baseline_idx < 0:
        return [], []

    slot_count = max(len(g) for g in groups)
    labels = list(folder_labels or [])
    while len(labels) < slot_count:
        labels.append(f'col{len(labels) + 1}')

    col_keys: List[str] = []
    headers = ['row', 'baseline_image']
    for si in range(slot_count):
        if si == baseline_idx:
            continue
        key = _col_key(labels[si], si)
        col_keys.append(key)
        headers.append(f'{key}_image')
        if METRIC_PSNR in metrics:
            headers.append(f'{key}_PSNR')
        if METRIC_SSIM in metrics:
            headers.append(f'{key}_SSIM')

    rows: List[Dict[str, object]] = []
    for gi, group in enumerate(groups):
        if baseline_idx >= len(group):
            continue
        base_info = group[baseline_idx]
        base_arr = _load_rgb(image_loader, base_info.path)
        if base_arr is None:
            continue

        row: Dict[str, object] = {
            'row': gi + 1,
            'baseline_image': base_info.name,
        }
        key_i = 0
        for si in range(min(slot_count, len(group))):
            if si == baseline_idx:
                continue
            key = col_keys[key_i] if key_i < len(col_keys) else f'col{si + 1}'
            key_i += 1
            info = group[si]
            row[f'{key}_image'] = info.name
            arr = _load_rgb(image_loader, info.path)
            if arr is None:
                if METRIC_PSNR in metrics:
                    row[f'{key}_PSNR'] = ''
                if METRIC_SSIM in metrics:
                    row[f'{key}_SSIM'] = ''
                continue
            vals = compute_image_metrics(base_arr, arr, list(metrics), preview=False)
            if METRIC_PSNR in metrics:
                v = normalize_psnr(vals.get(METRIC_PSNR))
                row[f'{key}_PSNR'] = '' if v is None else round(v, 4)
            if METRIC_SSIM in metrics:
                v = vals.get(METRIC_SSIM)
                row[f'{key}_SSIM'] = '' if v is None else round(v, 6)
        rows.append(row)
    return headers, rows


def export_metrics_csv(
    path: str,
    groups: List[List[ImageInfo]],
    baseline_idx: int,
    metrics: Sequence[str],
    image_loader: ImageLoader,
    folder_labels: Optional[List[str]] = None,
) -> Tuple[int, Optional[str]]:
    try:
        headers, rows = build_metrics_table_rows(
            groups, baseline_idx, metrics, image_loader, folder_labels,
        )
    except Exception as exc:
        logger.exception('build metrics table failed')
        return 0, str(exc)
    if not rows:
        return 0, 'no_data'

    try:
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return len(rows), None
    except OSError as exc:
        logger.error('export metrics csv failed: %s', exc)
        return 0, str(exc)
