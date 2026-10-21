"""Programindstillinger i Data/indstillinger.json (backup og slettepolitik)."""
from pathlib import Path

from app.data_manager import gem_json, hent_json
from app.stier import INDSTILLINGER_FIL, STANDARD_BACKUP_MAPPE

STANDARD = {
    # Arkiverede sager slettes efter så mange måneder (aftal perioden med HR).
    "opbevaring_maaneder": 12,
    # Antal sikkerhedskopier der gemmes, før de ældste slettes.
    "backup_antal": 30,
    # Tom = Data/Backup. Bør helst være et andet drev, fx et netværksdrev.
    "backup_mappe": "",
}


def hent():
    data = hent_json(INDSTILLINGER_FIL, forventet=dict)
    return {**STANDARD, **{k: v for k, v in data.items() if k in STANDARD}}


def gem(indstillinger):
    gem_json({k: indstillinger[k] for k in STANDARD}, INDSTILLINGER_FIL)


def backup_mappe(indstillinger):
    sti = str(indstillinger.get("backup_mappe") or "").strip()
    return Path(sti) if sti else STANDARD_BACKUP_MAPPE
