# sentinel.spec  —  PyInstaller build spec
# Produces a single .exe with no console window.
# All assets (alert.mp3) are bundled inside.

import sys, os
block_cipher = None

a = Analysis(
    ['sentinel.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('alert.mp3', '.'),      # bundle the alert sound next to sentinel.py
    ],
    hiddenimports=[
        'cv2',
        'numpy',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'pygame',
        'pygame.mixer',
        'winsound',
        'ctypes',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ArjunSUS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # ← NO console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
