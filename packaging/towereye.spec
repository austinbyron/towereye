# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: freezes the towereye CLI into dist/towereye-core/ (onedir),
# which the Electron app ships in its Resources. Build from the repo root:
#     .venv/bin/pyinstaller --noconfirm packaging/towereye.spec
import os

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, ".."))

hidden = (
    collect_submodules("websockets")
    + ["objc", "Vision", "Quartz", "AVFoundation", "Foundation", "CoreMedia"]
)

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[REPO],
    binaries=[],
    datas=[(os.path.join(REPO, "towereye", "static"), os.path.join("towereye", "static"))],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PIL.ImageTk", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="towereye-core",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="towereye-core")
