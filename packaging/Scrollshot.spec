# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / 'scrollshot.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtWebEngineQuick', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets'],
    noarchive=False,
)

# Some development machines have Poppler on PATH. Its ICU binaries shadow Qt's.
a.binaries = [entry for entry in a.binaries
              if not (entry[0].lower() in ('icuuc.dll', 'icudt78.dll')
                      and 'poppler' in entry[1].lower())]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Scrollshot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / 'packaging' / 'scrollshot.ico'),
    disable_windowed_traceback=False,
)
