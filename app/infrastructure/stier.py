"""Alle stier programmet bruger, samlet ét sted.

To mapper er vigtige:

- CENTRAL_DATA_MAPPE ("Data"): de fælles data. Som færdig .exe ligger den ved
  siden af programfilen (fx C:\\IN-BASE\\Data) og kan pege på et netværksdrev
  via miljøvariablen INBASE_DATA. Senere erstattes den af Supabase/PostgreSQL.
- LOKAL_MAPPE ("Lokal"): data, der hører til denne pc – offline-kopi,
  ændringslog, log-filer og brugerpræferencer. Ligger også ved siden af
  programmet (ikke i %APPDATA%) og kan flyttes med INBASE_LOKAL.

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

CENTRAL_DATA_MAPPE = Path(os.environ.get("INBASE_DATA") or PROGRAM_MAPPE / "Data")
LOKAL_MAPPE = Path(os.environ.get("INBASE_LOKAL") or PROGRAM_MAPPE / "Lokal")

# Filnavne i en datamappe (central eller offline-kopi).
OFFBOARDING_AKTIVE = "medarbejdere.json"
OFFBOARDING_ARKIV = "arkiv.json"
ONBOARDING_AKTIVE = "onboarding.json"
ONBOARDING_ARKIV = "onboarding_arkiv.json"
SKABELONER = "skabeloner.json"
INDSTILLINGER = "indstillinger.json"
BRUGERE = "brugere.json"
DATAFILER = (
    OFFBOARDING_AKTIVE, OFFBOARDING_ARKIV, ONBOARDING_AKTIVE, ONBOARDING_ARKIV,
    SKABELONER, INDSTILLINGER, BRUGERE,
)

# Filer i den lokale mappe.
OFFLINE_MAPPE = LOKAL_MAPPE / "Offline"
LOG_MAPPE = LOKAL_MAPPE / "Logs"
PRAEFERENCE_FIL = LOKAL_MAPPE / "praeferencer.json"
LAGRING_FIL = LOKAL_MAPPE / "lagring.json"
NOTIFIKATIONSLOG_FIL = LOKAL_MAPPE / "notifikationslog.json"

ASSETS_MAPPE = RESSOURCE_MAPPE / "assets"

# Til og med V0.5.1 lå data i %APPDATA%. Bruges kun til en engangskopi ved opstart.
GAMMEL_DATA_MAPPE = (
    Path(os.environ.get("APPDATA", str(Path.home())))
    / "MedarbejderUdstyr"
    / "Data"
)
