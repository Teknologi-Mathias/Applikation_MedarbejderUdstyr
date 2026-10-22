# -*- mode: python ; coding: utf-8 -*-
# Byg: pyinstaller MedarbejderUdstyr.spec  ->  dist/IN-BASE.exe
#
# Ikon (proceslinje, Jobliste, Stifinder): assets/IN-BASE.ico
#   (genereres fra logoet med: python tools/lav_ikon.py)
# Version og navn i Jobliste/Egenskaber læses fra app/__init__.py.
import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

sys.path.insert(0, str(Path(SPECPATH)))
from app import APP_BESKRIVELSE, APP_NAVN, VERSION  # noqa: E402

_tal = [int(x) for x in VERSION.lstrip("V").split(".")]
_tal = tuple((_tal + [0, 0, 0, 0])[:4])
_tekst = ".".join(str(x) for x in _tal)

versionsinfo = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_tal, prodvers=_tal),
    kids=[
        StringFileInfo([StringTable("040604B0", [
            StringStruct("CompanyName", "MASAN"),
            StringStruct("FileDescription", APP_NAVN),   # navnet i Jobliste
            StringStruct("FileVersion", _tekst),
            StringStruct("InternalName", APP_NAVN),
            StringStruct("LegalCopyright", "© Mathias Sander"),
            StringStruct("OriginalFilename", f"{APP_NAVN}.exe"),
            StringStruct("ProductName", APP_NAVN),
            StringStruct("ProductVersion", VERSION),
            StringStruct("Comments", APP_BESKRIVELSE),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0406, 1200])]),
    ],
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='IN-BASE',
    icon='assets/IN-BASE.ico',
    version=versionsinfo,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
