# PyInstaller onefile spec for OctoDesk (built by .github/workflows/build-windows.yml).
# Includes the web page and fixture data so the .exe runs fully offline-capable.
from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "octodesk" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "octodesk" / "web"), "octodesk/web"),
        (str(root / "octodesk" / "data"), "octodesk/data"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OctoDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "assets" / "icon.ico") if (root / "assets" / "icon.ico").exists() else None,
)
