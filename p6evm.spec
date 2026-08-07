# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for P6 EVM Tool
#
# Build with:
#   pyinstaller p6evm.spec
#
# Output: dist\P6EVMTool.exe  (single self-contained executable)

import sys
from pathlib import Path

block_cipher = None

# ── Data files bundled into the .exe ──────────────────────────────────────
datas = [
    ('ui',          'ui'),          # HTML / CSS / JS
    ('p6_evm',      'p6_evm'),      # Python package
    ('config.json', '.'),           # Config at root of bundle
]

# ── Hidden imports pywebview / webview2 needs ──────────────────────────────
hiddenimports = [
    # pywebview backends (Windows ships EdgeChromium / CEF)
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.cef',
    'webview.platforms.edgechromium',
    'clr',           # pythonnet — needed by pywebview WinForms backend
    # stdlib used at runtime that PyInstaller sometimes misses
    'http.server',
    'email.mime.text',
    'xml.etree.ElementTree',
    # EVM v2: E1 Log Excel reader
    'openpyxl',
    'et_xmlfile',
    # EVM v2 + audit engine packages (collected via import graph, listed for safety)
    'p6_audit',
    'p6_evm.e1_log',
    'p6_evm.gap',
    'p6_evm.evm_report',
    'p6_evm.engineering_p6',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused heavy packages to keep exe smaller
        'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL',
        'tkinter', '_tkinter',
        'PyQt5', 'PyQt6', 'wx',
    ],
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
    name='P6EVMTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window — pure GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='ui/icon.ico',   # uncomment and add icon.ico to use a custom icon
)
