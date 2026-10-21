"""Alle stier programmet bruger, samlet ét sted.

Som færdig .exe (PyInstaller) gemmes data i en "Data"-mappe ved siden af
programfilen, fx C:\\MedarbejderUdstyr\\Data. Under udvikling bruges
projektets egen Data-mappe.
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
    PROGRAM_MAPPE = Path(__file__).resolve().parent.parent
    RESSOURCE_MAPPE = PROGRAM_MAPPE

# Miljøvariablen INBASE_DATA kan pege på en anden datamappe (fx til test).
DATA_MAPPE = Path(os.environ.get("INBASE_DATA") or PROGRAM_MAPPE / "Data")
AKTIVE_FIL = DATA_MAPPE / "medarbejdere.json"
ARKIV_FIL = DATA_MAPPE / "arkiv.json"
SKABELON_FIL = DATA_MAPPE / "skabeloner.json"
INDSTILLINGER_FIL = DATA_MAPPE / "indstillinger.json"
BRUGER_FIL = DATA_MAPPE / "brugere.json"
# Standardplacering for sikkerhedskopier (kan ændres under Data & sikkerhed).
STANDARD_BACKUP_MAPPE = DATA_MAPPE / "Backup"

ASSETS_MAPPE = RESSOURCE_MAPPE / "assets"

# Til og med V0.5.1 lå data i %APPDATA%. Bruges kun til en engangskopi ved opstart.
GAMMEL_DATA_MAPPE = (
    Path(os.environ.get("APPDATA", str(Path.home())))
    / "MedarbejderUdstyr"
    / "Data"
)
