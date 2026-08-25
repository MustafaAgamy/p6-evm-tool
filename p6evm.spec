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
from PyInstaller.utils.hooks import collect_submodules

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# ── Data files bundled into the .exe ──────────────────────────────────────
datas = [
    ('ui',             'ui'),             # HTML / CSS / JS
    ('p6_evm',         'p6_evm'),         # Python package
    ('p6_audit',       'p6_audit'),       # Schedule-audit engine (Dangling/Float/OOS/Lag) — bundle
                                          # the whole package like p6_evm, so every submodule
                                          # (e.g. modules/lag_lead.py) ships even though server.py
                                          # only imports it deferred inside handlers.
    ('config.json',    '.'),              # Config at root of bundle
    ('knowledge_base', 'knowledge_base'), # Construction Knowledge Base (data files)
    ('report_theme.py', '.'),             # Shared report appearance themes — imported at
                                          # runtime by the report renderers (which run after
                                          # sys.path.insert(resource_path('.'))); ship as root
                                          # data so `import report_theme` resolves in the bundle.
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
    # server.py imports p6_audit only via deferred (in-function) imports, which PyInstaller's
    # graph can miss — force every submodule (engine, report, exporters, modules/lag_lead, …).
    *collect_submodules('p6_audit'),
    'p6_evm.e1_log',
    'p6_evm.gap',
    'p6_evm.evm_report',
    'p6_evm.engineering_p6',
    # Constructability engine (rule-based + knowledge base)
    'p6_kb',
    'p6_kb.review',
    'p6_kb.kb',
    'p6_kb.detect',
    'p6_kb.model',
    'p6_kb.scoring',
    # Shared report appearance themes (imported by every report renderer)
    'report_theme',
]

# Collect EVERY submodule of the in-tree packages so nothing loaded via a deferred /
# in-function import (server.py loads p6_report and several p6_kb modules lazily) is
# dropped from the .exe — this bit us before (an empty catalog / missing feature that
# only showed on the built exe, never in dev or tests). p6_report registers the
# Global Print-Preview features on import, so its submodules must ship.
for _pkg in ('p6_kb', 'p6_report', 'p6_evm', 'p6_audit', 'p6_compare'):
    try:
        hiddenimports += collect_submodules(_pkg)
    except Exception:
        pass

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
