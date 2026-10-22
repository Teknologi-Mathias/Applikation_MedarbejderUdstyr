"""Sikker læsning og skrivning af JSON-filer.

- Skrivning sker atomisk via en midlertidig fil + os.replace, så en afbrudt
  skrivning aldrig efterlader en halv fil.
- En ødelagt fil kopieres til <navn>.korrupt-<tid>.json, før der meldes fejl,
  så intet går tabt, og programmet overskriver den ikke.
"""
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from app.repositories.fejl import DataFejl

log = logging.getLogger(__name__)


def hent_json(fil: Path, forventet=list):
    """Læser en JSON-fil. forventet = list, dict eller en tuple af typer.

    En manglende eller tom fil giver en tom værdi af den forventede type
    (None, hvis flere typer er tilladt).
    """
    tom = forventet() if isinstance(forventet, type) else None
    if not fil.exists():
        return tom
    try:
        tekst = fil.read_text(encoding="utf-8")
    except OSError as fejl:
        raise DataFejl(f"Filen {fil} kunne ikke læses ({fejl}).") from fejl
    if not tekst.strip():
        return tom

    try:
        data = json.loads(tekst)
        if not isinstance(data, forventet):
            raise ValueError("Filen har ikke det forventede indhold.")
        return data
    except ValueError as fejl:
        tidsstempel = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = fil.with_name(f"{fil.stem}.korrupt-{tidsstempel}{fil.suffix}")
        shutil.copy2(fil, backup)
        log.error("Ødelagt datafil %s – kopi gemt som %s (%s)", fil, backup.name, fejl)
        raise DataFejl(
            f"Filen {fil.name} kunne ikke læses ({fejl}).\n\n"
            f"En kopi er gemt som {backup.name}. Ret eller slet filen, "
            "og start programmet igen."
        ) from fejl


def gem_json(data, fil: Path) -> None:
    fil.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_sti = tempfile.mkstemp(dir=fil.parent, prefix=fil.stem + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_sti, fil)
    except BaseException:
        if os.path.exists(tmp_sti):
            os.remove(tmp_sti)
        raise


def tjek_skriveadgang(mappe: Path) -> None:
    """Opretter mappen og tjekker, at programmet må skrive i den (kaster OSError)."""
    mappe.mkdir(parents=True, exist_ok=True)
    fd, sti = tempfile.mkstemp(dir=mappe, prefix=".skrivetest-")
    os.close(fd)
    os.remove(sti)


def fil_signatur(*filer: Path) -> tuple:
    """Ændrer sig, når en af filerne ændres (bruges til at opdage andres ændringer)."""
    signatur = []
    for fil in filer:
        try:
            stat = fil.stat()
            signatur.append((stat.st_mtime_ns, stat.st_size))
        except OSError:
            signatur.append(None)
    return tuple(signatur)
