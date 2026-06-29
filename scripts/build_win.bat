@echo off
REM Windows packaging — produce EXE
setlocal

cd /d "%~dp0\.."
echo === CompareX Windows packaging ===

python -m pip install -r requirements.txt -q

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller ^
    --name CompareX ^
    --windowed ^
    --noconfirm ^
    --clean ^
    --add-data "ui;ui" ^
    --add-data "core;core" ^
    --add-data "utils;utils" ^
    --add-data "assets;assets" ^
    --icon "assets\comparex_icon.png" ^
    --hidden-import PyQt6 ^
    --hidden-import cv2 ^
    --hidden-import matplotlib ^
    --hidden-import matplotlib.backends.backend_qtagg ^
    main.py

echo.
echo Done: dist\CompareX\CompareX.exe
pause
