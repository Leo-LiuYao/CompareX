"""
Global application configuration.
"""
import os
from pathlib import Path
from typing import Dict

# Application metadata
APP_NAME = "CompareX"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Research Tools"

# Path configuration
_PACKAGE_ROOT = Path(__file__).parent
PROJECT_ROOT = _PACKAGE_ROOT.parent
ASSETS_DIR = _PACKAGE_ROOT / "assets"
APP_ICON_PATH = ASSETS_DIR / "comparex_icon.png"
CACHE_DIR = Path.home() / ".imagecompare_fluent" / "cache"
CONFIG_DIR = Path.home() / ".imagecompare_fluent" / "config"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Image configuration
SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp')
THUMBNAIL_SIZE = (200, 200)
# Grid thumbnail Ctrl+wheel scale presets (default: second-largest)
THUMB_SCALE_PRESETS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5]
DEFAULT_THUMB_SCALE = THUMB_SCALE_PRESETS[-2]
# Preview page Cmd/Ctrl+wheel: trackpad uses pixel accumulation, mouse wheel uses notch count
THUMB_WHEEL_PIXEL_THRESHOLD = 120
THUMB_MOUSE_WHEEL_NOTCHES = 200  # Mouse wheel notches per thumbnail size step
THUMB_PINCH_SENSITIVITY = 0.2  # Preview pinch sensitivity vs Ctrl+trackpad wheel (lower = slower)
MAX_CACHE_IMAGES = 50

# UI configuration
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
DARK_THEME = True

# Compare window configuration
COMPARE_WINDOW_WIDTH = 1200
COMPARE_WINDOW_HEIGHT = 800
MIN_ZOOM = 0.1
MAX_ZOOM = 8192.0
ZOOM_STEP = 0.1
ZOOM_WHEEL_FACTOR = 1.04  # Zoom factor per wheel notch (lower = less sensitive)
ZOOM_WHEEL_DEGREES = 120   # Standard wheel notch angle in degrees
ZOOM_SLIDER_STEPS = 1000     # Internal slider steps (not direct percentage)
ZOOM_SLIDER_UI_MAX = 16.0    # Slider cap; wheel/shortcuts can still zoom to MAX_ZOOM
MAX_SCALE = 256.0  # Max screen pixels per image pixel (scale upper bound)
# Show pixel grid + RGB labels when screen/image pixel ratio reaches threshold (toggle required)
PIXEL_INSPECTOR_MIN_SCALE = 38.0
PIXEL_INSPECTOR_SCALE_PRESETS = [16, 20, 24, 28, 32, 36, 38, 42, 48, 56, 64, 72, 80, 96, 128]
PIXEL_RGB_DETAIL_SCALE = 54.0
MAX_PIXEL_RGB_LABELS = 6000

# Performance configuration
ASYNC_LOAD_THREADS = 4
IMAGE_PRELOAD_COUNT = 10

# Shortcut configuration
SHORTCUTS = {
    'open_folder': 'Ctrl+O',
    'new_compare': 'Ctrl+N',
    'export': 'Ctrl+E',
    'compare': ' ',  # Space
    'next_image': 'Tab',
    'reset_zoom': 'R',
    'histogram': 'H',
    'pixel_compare': 'P',
    'image_info': 'I',
    'toggle_mode': 'Ctrl+M',
    'crop_tool': 'Shift',
    'close': 'Esc',
}

# Color scheme - Ocolor style
COLORS = {
    'background': '#0a0a0a',
    'foreground': '#cccccc',
    'accent': '#1565c0',
    'success': '#4caf50',
    'warning': '#ff9800',
    'error': '#f44336',
    'panel_bg': '#141414',
    'panel_border': '#222222',
}

# Logging configuration
LOG_LEVEL = 'INFO'
LOG_FILE = CONFIG_DIR / 'app.log'
