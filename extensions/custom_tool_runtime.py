"""Custom tool runtime: execute user Python in a restricted environment."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from ui.compare_dialog import CompareCanvas

_ALLOWED_IMPORT_ROOTS = frozenset({
    'numpy', 'np', 'cv2', 'math', 'PIL',
})
_BLOCKED_BUILTINS = frozenset({
    'open', 'eval', 'exec', 'compile', 'input', 'breakpoint', 'exit', 'quit',
})
_RUN_CACHE: Dict[str, Any] = {}


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split('.')[0]
    if root not in _ALLOWED_IMPORT_ROOTS and name not in _ALLOWED_IMPORT_ROOTS:
        allowed = ', '.join(sorted(_ALLOWED_IMPORT_ROOTS))
        raise ImportError(f'模块 "{name}" 不在允许列表中（可用: {allowed}）')
    return __import__(name, globals, locals, fromlist, level)


def _safe_builtins() -> dict:
    import builtins
    safe = {k: v for k, v in vars(builtins).items() if k not in _BLOCKED_BUILTINS}
    safe['__import__'] = _restricted_import
    return safe


def _exec_globals() -> dict:
    globs = {'__builtins__': _safe_builtins()}
    globs.update({
        'np': np,
        'numpy': np,
        'cv2': cv2,
        'math': math,
    })
    return globs


def load_run_function(code: str, *, cache_key: str, force_reload: bool = False):
    if not force_reload and cache_key in _RUN_CACHE:
        return _RUN_CACHE[cache_key]

    compiled = compile(code, '<custom_tool>', 'exec')
    namespace: dict = {}
    exec(compiled, _exec_globals(), namespace)
    run_fn = namespace.get('run')
    if not callable(run_fn):
        raise ValueError('脚本须定义 run(ctx) 函数')

    if cache_key != '__validate__':
        _RUN_CACHE[cache_key] = run_fn
    return run_fn


def invalidate_tool_cache(tool_id: str) -> None:
    _RUN_CACHE.pop(tool_id, None)


@dataclass
class CustomToolSlot:
    index: int
    name: str
    folder: str
    source: np.ndarray
    display: np.ndarray


class CustomToolContext:
    """Context object passed to user run(ctx)."""

    def __init__(
        self,
        slots: List[CustomToolSlot],
        *,
        target_index: int = 0,
        ref_index: int = 0,
        cmp_index: int = 1,
    ):
        self.slots = slots
        self.slot_count = len(slots)
        self.target_index = target_index
        self.ref_index = ref_index
        self.cmp_index = cmp_index
        self.np = np
        self.numpy = np
        self.cv2 = cv2
        self.math = math

    def slot(self, index: int) -> Optional[CustomToolSlot]:
        for item in self.slots:
            if item.index == index:
                return item
        return None

    def target(self) -> Optional[CustomToolSlot]:
        return self.slot(self.target_index)

    def ref(self) -> Optional[CustomToolSlot]:
        return self.slot(self.ref_index)

    def cmp(self) -> Optional[CustomToolSlot]:
        return self.slot(self.cmp_index)


def build_context(
    canvas: 'CompareCanvas',
    *,
    target_index: int,
    ref_index: int,
    cmp_index: int,
) -> CustomToolContext:
    slots: List[CustomToolSlot] = []
    for i, slot in enumerate(canvas.slots):
        if slot.source_array is None and slot.array is None:
            continue
        name = slot.info.name if slot.info else f'分区 {i + 1}'
        folder = ''
        if slot.info and slot.info.path:
            folder = canvas._folder_name_map.get(slot.info.path, '')
            if not folder:
                from pathlib import Path
                folder = Path(slot.info.path).parent.name
        source = slot.source_array
        display = slot.array if slot.array is not None else source
        if source is None:
            source = display
        if display is None:
            continue
        slots.append(CustomToolSlot(
            index=i,
            name=name,
            folder=folder,
            source=source[:, :, :3] if source.ndim == 3 else source,
            display=display[:, :, :3] if display.ndim == 3 else display,
        ))
    return CustomToolContext(
        slots, target_index=target_index, ref_index=ref_index, cmp_index=cmp_index,
    )


def run_custom_tool(
    tool_id: str,
    code: str,
    canvas: 'CompareCanvas',
    *,
    target_index: int,
    ref_index: int,
    cmp_index: int,
) -> Dict[str, Any]:
    run_fn = load_run_function(code, cache_key=tool_id)
    ctx = build_context(
        canvas,
        target_index=target_index,
        ref_index=ref_index,
        cmp_index=cmp_index,
    )
    raw = run_fn(ctx)
    return normalize_result(raw)


def _as_rgb_u8(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=2)
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(arr)


def normalize_result(result: Any) -> Dict[str, Any]:
    if result is None:
        return {'message': '', 'image': None, 'images': []}
    if isinstance(result, str):
        return {'message': result, 'image': None, 'images': []}
    if isinstance(result, np.ndarray):
        return {'message': '', 'image': _as_rgb_u8(result), 'images': []}
    if not isinstance(result, dict):
        return {'message': str(result), 'image': None, 'images': []}

    message = str(result.get('message', '') or '')
    image = result.get('image')
    images = result.get('images') or []
    apply_slot = result.get('apply_slot')
    norm_images: List[np.ndarray] = []
    if image is not None:
        norm_images.append(_as_rgb_u8(image))
    for item in images:
        if item is not None:
            norm_images.append(_as_rgb_u8(item))
    primary = norm_images[0] if norm_images else None
    out = {'message': message, 'image': primary, 'images': norm_images}
    if apply_slot is not None:
        out['apply_slot'] = int(apply_slot)
    return out
