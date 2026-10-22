# -*- mode: python ; coding: utf-8 -*-
# Normal release: .\scripts\build_windows.ps1 (bygger med denne fil + installer).
# Byg (mappe, anbefalet først):  pyinstaller --noconfirm MedarbejderUdstyr.spec
#                                -> dist/IN-BASE/IN-BASE.exe
# Byg (én .exe):                 set INBASE_ONEFILE=1 && pyinstaller --noconfirm MedarbejderUdstyr.spec
#                                -> dist/IN-BASE.exe
# Kontrol uden GUI/netværk:      dist\IN-BASE\IN-BASE.exe --selvtest  (exit-kode 0 = OK)
#
# Konfigurationen (%APPDATA%\IN-BASE\.env) indlejres ALDRIG – kun assets/ pakkes med.
# Ikon (proceslinje, Jobliste, Stifinder): assets/IN-BASE.ico
#   (genereres fra logoet med: python tools/lav_ikon.py)
# Version og navn i Jobliste/Egenskaber læses fra app/__init__.py.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

sys.path.insert(0, str(Path(SPECPATH)))
from app import APP_BESKRIVELSE, APP_NAVN, __version__, version_tupel  # noqa: E402

_tal = version_tupel() + (0,)          # Windows vil have fire tal: x.y.z.0
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
            StringStruct("ProductVersion", __version__),
            StringStruct("Comments", APP_BESKRIVELSE),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0406, 1200])]),
    ],
)

EN_FIL = os.environ.get("INBASE_ONEFILE") == "1"

# Supabase-klienten består af flere pakker med dynamiske imports; tag dem alle med.
_skjulte = []
for pakke in ("supabase", "supabase_auth", "supabase_functions", "postgrest", "storage3",
              "realtime", "app.repositories.supabase"):
    _skjulte += collect_submodules(pakke)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')] + collect_data_files('certifi'),   # SSL-rodcertifikater
    hiddenimports=_skjulte + ['dotenv'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'tools'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    *([a.binaries, a.datas] if EN_FIL else []),
    [],
    exclude_binaries=not EN_FIL,
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

if not EN_FIL:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='IN-BASE')
