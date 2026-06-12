@echo off
title ARJUN SUS — Build EXE
color 0A
echo.
echo  ============================================
echo   ARJUN SUS  —  Building single .exe
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from python.org and tick "Add to PATH".
    pause & exit /b 1
)

echo [1/3] Installing dependencies...
pip install opencv-python Pillow numpy pygame pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)

echo [2/3] Building ArjunSUS.exe  ^(this takes 1-3 minutes^)...
pyinstaller sentinel.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause & exit /b 1
)

echo [3/3] Done!
echo.
echo  Your exe is at:
echo    dist\ArjunSUS.exe
echo.
echo  Just double-click it — no Python needed, no console, all in one file.
echo.

:: Open the dist folder automatically
explorer dist

pause
