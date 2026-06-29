# -*- mode: python ; coding: utf-8 -*-
"""CompareX PyInstaller spec — lean bundle, no conda ML stack."""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

# Packages CompareX never imports — exclude to avoid pulling torch/transformers from conda.
EXCLUDES = [
    'torch', 'torchvision', 'torchaudio', 'torchgen', 'functorch',
    'transformers', 'tokenizers', 'safetensors', 'accelerate', 'diffusers',
    'gradio', 'gradio_client', 'huggingface_hub', 'datasets',
    'tensorflow', 'keras', 'jax', 'flax',
    'onnx', 'onnxruntime', 'onnxruntime_gpu',
    'pandas', 'polars', 'pyarrow', 'fastparquet',
    'sklearn', 'scikit-learn', 'timm', 'einops',
    'pytest', 'py', '_pytest', 'pygments',
    'IPython', 'jupyter', 'jupyterlab', 'notebook', 'ipykernel',
    'numba', 'llvmlite', 'sympy', 'mpmath',
    'tiktoken', 'sentencepiece', 'openai', 'anthropic',
    'fastapi', 'uvicorn', 'starlette', 'pydantic', 'httpx',
    'boto3', 'botocore', 'sqlalchemy', 'alembic',
    'tkinter', '_tkinter',
    'torchtext', 'torchdata', 'triton',
    'xformers', 'bitsandbytes', 'peft',
    'wandb', 'tensorboard', 'mlflow',
    'selenium', 'playwright',
]

# OpenCV: ship native libs + config, fix frozen bootstrap via runtime hook.
cv2_datas = collect_data_files('cv2', include_py_files=True)
cv2_binaries = collect_dynamic_libs('cv2')

hidden = [
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtDBus',
    'PyQt6.sip',
    'qfluentwidgets', 'qframelesswindow', 'darkdetect',
    'cv2', 'numpy', 'PIL', 'PIL.Image',
    'scipy', 'scipy.special', 'scipy.ndimage',
    'skimage', 'skimage.metrics', 'skimage.metrics._structural_similarity',
    'skimage.metrics.simple_metrics',
    'matplotlib', 'matplotlib.backends.backend_qtagg',
    'lazy_loader', 'imageio', 'networkx', 'tifffile',
    'objc', 'AppKit', 'Cocoa',  # macOS fullscreen helper (optional at runtime)
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=cv2_binaries,
    datas=[
        ('ui', 'ui'),
        ('core', 'core'),
        ('utils', 'utils'),
        ('i18n', 'i18n'),
        ('extensions', 'extensions'),
        ('assets', 'assets'),
        *cv2_datas,
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join('packaging', 'pyi_rth_cv2.py')],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

# Drop duplicate source trees PyInstaller may add as datas (keep lean).
_SKIP_DATA_PREFIXES = (
    'torch', 'transformers', 'gradio', 'pandas', 'pyarrow', 'polars',
    'onnxruntime', 'sklearn', 'timm', 'pytest',
)
a.datas = [
    entry for entry in a.datas
    if not any(
        entry[1].startswith(prefix + os.sep) or entry[1] == prefix
        for prefix in _SKIP_DATA_PREFIXES
    )
]

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CompareX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/comparex_icon.icns'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CompareX',
)

app = BUNDLE(
    coll,
    name='CompareX.app',
    icon='assets/comparex_icon.icns',
    bundle_identifier='com.comparex.app',
)
