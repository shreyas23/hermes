import os
import sys

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
    ],
    hiddenimports=[
        'pysbd.lang.english',
        'pysbd.lang.common',
        'webview',
        'webview.platforms.cocoa',
        'trafilatura',
        'pymupdf',
        'docx',
        'striprtf',
        'striprtf.striprtf',
        'bs4',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Hermes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Hermes',
)

app = BUNDLE(
    coll,
    name='Hermes.app',
    icon=None,
    bundle_identifier='com.hermes.app',
    info_plist={
        'CFBundleName': 'Hermes',
        'CFBundleDisplayName': 'Hermes',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'NSHighResolutionCapable': True,
    },
)
