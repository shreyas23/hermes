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
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'pysbd.lang.english',
        'pysbd.lang.common',
        'webview',
        'webview.platforms.cocoa',
        'trafilatura',
        'pymupdf',
        'pymupdf4llm',
        'pymupdf4llm.helpers',
        'pymupdf4llm.helpers.pymupdf_rag',
        'markdown',
        'markdown.extensions',
        'markdown.extensions.tables',
        'docx',
        'striprtf',
        'striprtf.striprtf',
        'bs4',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'onnxruntime', 'pymupdf_layout',
        'torch', 'torchaudio', 'torchvision',
        'spacy', 'thinc', 'blis', 'cymem', 'preshed', 'murmurhash', 'srsly',
        'babel',
        'hf_xet', 'huggingface_hub', 'safetensors', 'tokenizers', 'transformers',
        'soundfile', 'sounddevice',
        'scipy', 'pandas', 'matplotlib', 'PIL', 'cv2',
        'IPython', 'notebook', 'jupyter',
    ],
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
    strip=True,
    upx=True,
    console=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='Hermes',
)

app = BUNDLE(
    coll,
    name='Hermes.app',
    icon='assets/icon.icns',
    bundle_identifier='com.hermes.app',
    info_plist={
        'CFBundleName': 'Hermes',
        'CFBundleDisplayName': 'Hermes',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '13.0',
        'LSApplicationCategoryType': 'public.app-category.productivity',
        'NSHumanReadableCopyright': 'Copyright © 2026 Shreyas Niradi. AGPL-3.0.',
        'NSAppTransportSecurity': {'NSAllowsArbitraryLoads': True},
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'PDF Document',
                'CFBundleTypeExtensions': ['pdf'],
                'CFBundleTypeRole': 'Viewer',
            },
            {
                'CFBundleTypeName': 'Word Document',
                'CFBundleTypeExtensions': ['docx'],
                'CFBundleTypeRole': 'Viewer',
            },
            {
                'CFBundleTypeName': 'Text Document',
                'CFBundleTypeExtensions': ['txt', 'md', 'rtf', 'html', 'htm'],
                'CFBundleTypeRole': 'Viewer',
            },
        ],
    },
)
