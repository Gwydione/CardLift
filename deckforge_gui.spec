# -*- mode: python ; coding: utf-8 -*-
# Discovery build: smallest spec that produces a runnable one-folder
# DeckForge GUI bundle. No installer/signing/versioning yet -- see
# DEVELOPER.md packaging notes for follow-up stabilization steps.

a = Analysis(
    ['gui_app.py'],
    pathex=['src'],
    binaries=[],
    datas=[('sample_decks/DeckForge_Demo_Deck.pdf', 'sample_decks')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DeckForge',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='DeckForge',
)
