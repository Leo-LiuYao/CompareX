"""PyInstaller runtime hook: load OpenCV native module before cv2/__init__.py bootstrap."""
import importlib.machinery
import importlib.util
import os
import sys

if getattr(sys, 'frozen', False):
    base = getattr(sys, '_MEIPASS', '')
    so_name = 'cv2.abi3.so'
    so_path = os.path.join(base, 'cv2', so_name)
    if os.path.isfile(so_path) and 'cv2' not in sys.modules:
        loader = importlib.machinery.ExtensionFileLoader('cv2', so_path)
        spec = importlib.util.spec_from_loader('cv2', loader, origin=so_path)
        if spec is not None:
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            sys.modules['cv2'] = mod
