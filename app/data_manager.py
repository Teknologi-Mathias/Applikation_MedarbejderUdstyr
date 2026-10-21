"""Læsning og skrivning af JSON-filerne med aktive og arkiverede medarbejdere."""
import json
import os
import shutil
import tempfile
from datetime import datetime

from app.medarbejder import Medarbejder
from app.stier import (
    AKTIVE_FIL,
    ARKIV_FIL,
    DATA_MAPPE,
    ER_FROSSET,
    GAMMEL_DATA_MAPPE,
)


class DataFejl(Exception):
    """Datafilen kan ikke læses eller skrives (fx ødelagt JSON)."""


### ----- opstart -------------------------------------------------------------

def klargoer_data_mappe():
    """Kaldes én gang ved opstart.

    Opretter Data-mappen, kopierer evt. data fra den gamle placering i
    %APPDATA% og tjekker at programmet må skrive i mappen.
    """
    try:
        DATA_MAPPE.mkdir(parents=True, exist_ok=True)
        _kopier_gamle_data()
        _tjek_skriveadgang()
    except OSError as fejl:
        raise DataFejl(
            f"Programmet kan ikke skrive i datamappen:\n{DATA_MAPPE}\n\n"
            f"({fejl})\n\n"
            "Ligger programmet i C:\\Program Files, kræver det "
            "administratorrettigheder. Flyt i stedet programmet til en mappe "
            "som C:\\MedarbejderUdstyr."
        ) from fejl


def _kopier_gamle_data():
    """Kopierer data fra %APPDATA% første gang den nye version startes.

    Der kopieres (ikke flyttes), så de gamle filer bliver liggende som backup.
    """
    if not ER_FROSSET or GAMMEL_DATA_MAPPE == DATA_MAPPE:
        return
    for fil in (AKTIVE_FIL, ARKIV_FIL):
        gammel = GAMMEL_DATA_MAPPE / fil.name
        if gammel.exists() and not fil.exists():
            shutil.copy2(gammel, fil)


def _tjek_skriveadgang():
    fd, sti = tempfile.mkstemp(dir=DATA_MAPPE, prefix=".skrivetest-")
    os.close(fd)
    os.remove(sti)


### ----- filhåndtering ------------------------------------------------------

def _sikre_data_mappe():
    DATA_MAPPE.mkdir(parents=True, exist_ok=True)


def _hent_json(fil):
    _sikre_data_mappe()

    if not fil.exists():
        return []

    tekst = fil.read_text(encoding="utf-8")
    if not tekst.strip():
        return []

    try:
        data = json.loads(tekst)
        if not isinstance(data, list):
            raise ValueError("Forventede en liste af medarbejdere.")
        return data
    except ValueError as fejl:
        # Gem en kopi, så intet går tabt, og stop i stedet for at overskrive.
        tidsstempel = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = fil.with_name(f"{fil.stem}.korrupt-{tidsstempel}{fil.suffix}")
        shutil.copy2(fil, backup)
        raise DataFejl(
            f"Filen {fil.name} kunne ikke læses ({fejl}).\n\n"
            f"En kopi er gemt som {backup.name}. Ret eller slet filen, "
            "og start programmet igen."
        ) from fejl


def _gem_json(data, fil):
    _sikre_data_mappe()

    fd, tmp_sti = tempfile.mkstemp(
        dir=fil.parent, prefix=fil.stem + ".", suffix=".tmp"
    )
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


def _til_medarbejdere(data):
    return [Medarbejder.fra_dict(post) for post in data]


def _uden_loennr(data, loennr):
    return [post for post in data if str(post.get("loennr")) != str(loennr)]


def fil_signatur():
    """Ændrer sig, når en af datafilerne ændres (bruges til synkronisering)."""
    signatur = []
    for fil in (AKTIVE_FIL, ARKIV_FIL):
        try:
            stat = fil.stat()
            signatur.append((stat.st_mtime_ns, stat.st_size))
        except OSError:
            signatur.append(None)
    return tuple(signatur)


### ----- offentlige funktioner ----------------------------------------------

def hent_medarbejdere():
    return _til_medarbejdere(_hent_json(AKTIVE_FIL))


def hent_arkiverede_medarbejdere():
    return _til_medarbejdere(_hent_json(ARKIV_FIL))


def gem_medarbejdere(medarbejdere):
    _gem_json([m.til_dict() for m in medarbejdere], AKTIVE_FIL)


def gem_arkiv(medarbejdere):
    _gem_json([m.til_dict() for m in medarbejdere], ARKIV_FIL)


def arkiver_medarbejder(medarbejder):
    """Flytter en medarbejder fra aktive til arkiv (matcher på lønnr.)."""
    arkiv = _uden_loennr(_hent_json(ARKIV_FIL), medarbejder.loennr)
    aktive = _uden_loennr(_hent_json(AKTIVE_FIL), medarbejder.loennr)

    arkiv.append(medarbejder.til_dict())

    # Arkivet gemmes først: går noget galt midtvejs, er personen hellere i
    # begge filer end i ingen af dem.
    _gem_json(arkiv, ARKIV_FIL)
    _gem_json(aktive, AKTIVE_FIL)


def aktiver_medarbejder(medarbejder):
    """Flytter en medarbejder fra arkiv tilbage til aktive."""
    arkiv = _uden_loennr(_hent_json(ARKIV_FIL), medarbejder.loennr)
    aktive = _uden_loennr(_hent_json(AKTIVE_FIL), medarbejder.loennr)

    aktive.append(medarbejder.til_dict())

    _gem_json(aktive, AKTIVE_FIL)
    _gem_json(arkiv, ARKIV_FIL)


def slet_fra_arkiv(medarbejder):
    arkiv = _uden_loennr(_hent_json(ARKIV_FIL), medarbejder.loennr)
    _gem_json(arkiv, ARKIV_FIL)
