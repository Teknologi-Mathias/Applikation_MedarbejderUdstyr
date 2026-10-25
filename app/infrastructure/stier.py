"""Alle stier programmet bruger, samlet ét sted.

- KONFIG_FIL (%APPDATA%\\IN-BASE\\.env): forbindelsen til Supabase (URL og
  offentlig nøgle). Læses af app/infrastructure/database/config.py.
- LOKAL_MAPPE: data, der hører til denne pc – log-filer, notifikationslog og
  (kun JSON-tilstand) offline-kopi og præferencer. Den færdige .exe bruger
  %LOCALAPPDATA%\\IN-BASE (aldrig mappen inde i/ved siden af programmet, som
  kan være skrivebeskyttet); fra kildekoden bruges Lokal/ i projektet.
  Kan flyttes med INBASE_LOKAL.
- CENTRAL_DATA_MAPPE ("Data"): kun JSON-tilstanden (INBASE_BACKEND=json).
  I Supabase-tilstand er databasen den eneste fælles datakilde.

Filnavnene er konstanter; den konkrete mappe vælges af Datakilde
(app/repositories/json/datakilde.py), så offline-tilstand kan skifte mappe.
"""
import os
import sys
from pathlib import Path

ER_FROSSET = getattr(sys, "frozen", False)

if ER_FROSSET:
    # Mappen hvor .exe-filen ligger.
    PROGRAM_MAPPE = Path(sys.executable).resolve().parent
    # PyInstaller pakker medfølgende filer (assets) ud i en midlertidig mappe.
    RESSOURCE_MAPPE = Path(getattr(sys, "_MEIPASS", PROGRAM_MAPPE))
else:
    PROGRAM_MAPPE = Path(__file__).resolve().parents[2]
    RESSOURCE_MAPPE = PROGRAM_MAPPE

_APPDATA = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")

KONFIG_MAPPE = _APPDATA / "IN-BASE"
KONFIG_FIL = KONFIG_MAPPE / ".env"

CENTRAL_DATA_MAPPE = Path(os.environ.get("INBASE_DATA") or PROGRAM_MAPPE / "Data")
LOKAL_MAPPE = Path(
    os.environ.get("INBASE_LOKAL")
    or (_LOCALAPPDATA / "IN-BASE" if ER_FROSSET else PROGRAM_MAPPE / "Lokal")
)

# Filnavne i en datamappe (central eller offline-kopi).
OFFBOARDING_AKTIVE = "medarbejdere.json"
OFFBOARDING_ARKIV = "arkiv.json"
ONBOARDING_AKTIVE = "onboarding.json"
ONBOARDING_ARKIV = "onboarding_arkiv.json"
SKABELONER = "skabeloner.json"
INDSTILLINGER = "indstillinger.json"
BRUGERE = "brugere.json"
OENSKER = "oensker.json"            # Ønsker & Udvikling
DATAFILER = (
    OFFBOARDING_AKTIVE, OFFBOARDING_ARKIV, ONBOARDING_AKTIVE, ONBOARDING_ARKIV,
    SKABELONER, INDSTILLINGER, BRUGERE, OENSKER,
)

# Filer i den lokale mappe.
OFFLINE_MAPPE = LOKAL_MAPPE / "Offline"
LOG_MAPPE = LOKAL_MAPPE / "Logs"
PRAEFERENCE_FIL = LOKAL_MAPPE / "praeferencer.json"
LAGRING_FIL = LOKAL_MAPPE / "lagring.json"
NOTIFIKATIONSLOG_FIL = LOKAL_MAPPE / "notifikationslog.json"

ASSETS_MAPPE = RESSOURCE_MAPPE / "assets"
