"""Trackpad pinch zoom — equivalent to Ctrl/Command + wheel (trackpad pixelDelta)."""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QNativeGestureEvent, QWheelEvent
from PyQt6.QtWidgets import QWidget, QPinchGesture

from config import (
    THUMB_WHEEL_PIXEL_THRESHOLD, THUMB_PINCH_SENSITIVITY,
    ZOOM_WHEEL_FACTOR, ZOOM_WHEEL_DEGREES,
)


def enable_pinch_gestures(widget: QWidget) -> None:
    widget.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
    widget.grabGesture(Qt.GestureType.PinchGesture)


def wheel_event_pixel_delta(event: QWheelEvent) -> float:
    pd = event.pixelDelta()
    if pd.y() != 0:
        return float(pd.y())
    if pd.x() != 0:
        return float(pd.x())
    return float(event.angleDelta().y())


def native_gesture_zoom_pixels(value: float) -> float:
    """Map NativeGesture Zoom value to trackpad-equivalent pixel delta."""
    return value * THUMB_WHEEL_PIXEL_THRESHOLD


def pinch_scale_factor_to_pixels(scale_factor: float) -> float:
    """QPinchGesture.scaleFactor() -> equivalent wheel pixelDelta."""
    if not math.isfinite(scale_factor) or scale_factor <= 0.0:
        return 0.0
    if abs(scale_factor - 1.0) < 1e-6:
        return 0.0
    steps = math.log(scale_factor) / math.log(ZOOM_WHEEL_FACTOR)
    return steps * ZOOM_WHEEL_DEGREES


def zoom_factor_from_pixels(pixels: float) -> float:
    steps = pixels / ZOOM_WHEEL_DEGREES
    return ZOOM_WHEEL_FACTOR ** steps


def try_handle_pinch_event(event, *, thumb_mode: bool = False) -> Optional[float]:
    """Handle pinch/native zoom; return equivalent pixelDelta or None if unhandled."""
    sensitivity = THUMB_PINCH_SENSITIVITY if thumb_mode else 1.0
    et = event.type()

    if et == QEvent.Type.NativeGesture:
        if not isinstance(event, QNativeGestureEvent):
            return None
        if event.gestureType() != Qt.NativeGestureType.ZoomNativeGesture:
            return None
        if event.isBeginEvent() or event.isEndEvent():
            event.accept()
            return 0.0
        delta = event.value()
        if abs(delta) < 1e-8:
            event.accept()
            return 0.0
        pixels = native_gesture_zoom_pixels(delta) * sensitivity
        event.accept()
        return pixels

    if et == QEvent.Type.Gesture:
        pinch = event.gesture(Qt.GestureType.PinchGesture)
        if pinch is None:
            return None
        st = pinch.state()
        if st == Qt.GestureState.GestureCanceled:
            event.accept(pinch)
            return 0.0
        if st not in (Qt.GestureState.GestureUpdated, Qt.GestureState.GestureFinished):
            return None
        scale_factor = pinch.scaleFactor()
        if not math.isfinite(scale_factor) or scale_factor <= 0.0:
            event.accept(pinch)
            return 0.0
        pixels = pinch_scale_factor_to_pixels(scale_factor) * sensitivity
        event.accept(pinch)
        return pixels

    return None
