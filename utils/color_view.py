"""Compare view color / brightness / channel processing (display only, not written to disk)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

CHANNEL_ORDER_PRESETS: Tuple[Tuple[str, str, Tuple[int, int, int]], ...] = (
    ('rgb', 'RGB', (0, 1, 2)),
    ('bgr', 'BGR', (2, 1, 0)),
    ('rbg', 'RBG', (0, 2, 1)),
    ('grb', 'GRB', (1, 0, 2)),
    ('gbr', 'GBR', (1, 2, 0)),
    ('brg', 'BRG', (2, 0, 1)),
)

VIEW_MODES: Tuple[Tuple[str, str], ...] = (
    ('color', '彩色'),
    ('r', '仅 R'),
    ('g', '仅 G'),
    ('b', '仅 B'),
    ('luma', '亮度 Y'),
)


@dataclass
class ColorViewParams:
    order_key: str = 'rgb'
    view_mode: str = 'color'
    channel_mono: bool = False   # False=RGB (only selected channel nonzero); True=single-channel gray
    brightness: int = 0       # -100 .. 100
    contrast: int = 100       # 0 .. 200, 100 = original
    gamma: float = 1.0        # 0.10 .. 3.00

    def is_identity(self) -> bool:
        return (
            self.order_key == 'rgb'
            and self.view_mode == 'color'
            and not self.channel_mono
            and self.brightness == 0
            and self.contrast == 100
            and abs(self.gamma - 1.0) < 0.01
        )


def order_indices(order_key: str) -> Tuple[int, int, int]:
    for key, _, order in CHANNEL_ORDER_PRESETS:
        if key == order_key:
            return order
    return (0, 1, 2)


def _isolate_channel(rgb: np.ndarray, channel: int, mono: bool) -> np.ndarray:
    """Single-channel view: mono copies gray; else only that channel is nonzero (RGB display)."""
    if mono:
        ch = rgb[:, :, channel:channel + 1]
        return np.repeat(ch, 3, axis=2)
    out = np.zeros_like(rgb)
    out[:, :, channel] = rgb[:, :, channel]
    return out


def apply_color_view(source: np.ndarray, params: ColorViewParams) -> np.ndarray:
    """Convert source array to view RGB (uint8, H×W×3)."""
    if source is None:
        return source

    rgb_u8 = source[:, :, :3]
    if params.is_identity():
        if rgb_u8.dtype == np.uint8 and rgb_u8.flags['C_CONTIGUOUS']:
            return rgb_u8
        return np.ascontiguousarray(rgb_u8.astype(np.uint8, copy=False))

    rgb = rgb_u8.astype(np.float32, copy=False)

    order = order_indices(params.order_key)
    rgb = rgb[:, :, order]

    mode = params.view_mode
    mono = params.channel_mono
    if mode == 'r':
        rgb = _isolate_channel(rgb, 0, mono)
    elif mode == 'g':
        rgb = _isolate_channel(rgb, 1, mono)
    elif mode == 'b':
        rgb = _isolate_channel(rgb, 2, mono)
    elif mode == 'luma':
        y = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        rgb = np.stack([y, y, y], axis=2)

    contrast = max(0.0, params.contrast) / 100.0
    offset = params.brightness * 2.55
    rgb = (rgb - 128.0) * contrast + 128.0 + offset
    rgb = np.clip(rgb, 0.0, 255.0)

    gamma = max(0.1, min(3.0, params.gamma))
    if abs(gamma - 1.0) > 0.01:
        rgb = 255.0 * np.power(rgb / 255.0, 1.0 / gamma)

    return np.clip(rgb, 0, 255).astype(np.uint8)
