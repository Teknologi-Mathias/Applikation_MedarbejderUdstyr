"""Sikkerhedskopier, kontrolleret gendannelse og slettepolitik.

- tag_backup()   kopierer alle datafiler til en tidsstemplet mappe med en
                 manifest-fil (SHA-256 pr. fil) og tester straks, at kopien
                 kan gendannes.
- test_backup()  kontrollerer en backup: filerne er uændrede, kan læses som
                 JSON, og alle medarbejdere kan indlæses af programmet.
- gendan()       tester backuppen, tager en backup af de nuværende data og
                 lægger derefter backuppen på plads.
- udloebne()     arkiverede sager, hvis opbevaringsperiode er udløbet.
"""
import calendar
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app import VERSION
from app.data_manager import DataFejl
from app.historik import nuvaerende_bruger
from app.indstillinger import backup_mappe
from app.medarbejder import Medarbejder
from app.opgave import laes_iso_dato
from app.stier import (
    AKTIVE_FIL,
    ARKIV_FIL,
    BRUGER_FIL,
    DATA_MAPPE,
    INDSTILLINGER_FIL,
    SKABELON_FIL,
)

DATAFILER = (AKTIVE_FIL, ARKIV_FIL, SKABELON_FIL, INDSTILLINGER_FIL, BRUGER_FIL)
MANIFEST = "manifest.json"


@dataclass
class BackupInfo:
    sti: Path
    tid: datetime
    aarsag: str
    bruger: str
    antal_aktive: int
    antal_arkiv: int


### ----- backup -------------------------------------------------------------

def _sha256(fil):
    return hashlib.sha256(Path(fil).read_bytes()).hexdigest()


def _antal(fil):
    try:
        data = json.loads(Path(fil).read_text(encoding="utf-8") or "[]")
        return len(data) if isinstance(data, list) else 0
    except (OSError, ValueError):
        return 0


def tag_backup(indstillinger, aarsag="manuel"):
    """Tager og verificerer en backup. Kaster DataFejl, hvis den ikke kan gendannes."""
    mappe = backup_mappe(indstillinger)
    mappe.mkdir(parents=True, exist_ok=True)
    navn = f"{datetime.now():%Y-%m-%d_%H%M%S}_{aarsag}"
    endelig = mappe / navn
    nummer = 2
    while endelig.exists():
        endelig = mappe / f"{navn}-{nummer}"
        nummer += 1

    # Kopieres først til en .tmp-mappe, så halve backups aldrig vises.
    tmp = endelig.with_name(endelig.name + ".tmp")
    tmp.mkdir()
    filer = {}
    for fil in DATAFILER:
        if fil.exists():
            shutil.copy2(fil, tmp / fil.name)
            filer[fil.name] = _sha256(tmp / fil.name)
    manifest = {
        "tid": datetime.now().isoformat(timespec="seconds"),
        "aarsag": aarsag,
        "bruger": nuvaerende_bruger(),
        "version": VERSION,
        "filer": filer,
        "antal_aktive": _antal(tmp / AKTIVE_FIL.name),
        "antal_arkiv": _antal(tmp / ARKIV_FIL.name),
    }
    (tmp / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    tmp.rename(endelig)

    ok, besked = test_backup(endelig)
    if not ok:
        raise DataFejl(f"Sikkerhedskopien {endelig.name} kunne ikke verificeres:\n{besked}")
    info = _info(endelig)
    ryd_gamle(indstillinger, behold=endelig)
    return info


def _laes_manifest(sti):
    return json.loads((Path(sti) / MANIFEST).read_text(encoding="utf-8"))


def _info(sti):
    manifest = _laes_manifest(sti)
    try:
        tid = datetime.fromisoformat(manifest.get("tid", ""))
    except ValueError:
        tid = datetime.fromtimestamp(Path(sti).stat().st_mtime)
    return BackupInfo(
        Path(sti),
        tid,
        manifest.get("aarsag", ""),
        manifest.get("bruger", ""),
        manifest.get("antal_aktive", 0),
        manifest.get("antal_arkiv", 0),
    )


def liste(indstillinger):
    """Alle gyldige backups, nyeste først."""
    mappe = backup_mappe(indstillinger)
    if not mappe.exists():
        return []
    resultat = []
    for sti in mappe.iterdir():
        if sti.is_dir() and not sti.name.endswith(".tmp") and (sti / MANIFEST).exists():
            try:
                resultat.append(_info(sti))
            except (OSError, ValueError):
                continue
    return sorted(resultat, key=lambda b: (b.tid, b.sti.name), reverse=True)


def ryd_gamle(indstillinger, behold=None):
    """Sletter de ældste backups ud over det tilladte antal (og efterladte .tmp-mapper).

    behold: en backup der aldrig slettes (den der lige er taget).
    """
    mappe = backup_mappe(indstillinger)
    for tmp in mappe.glob("*.tmp"):
        shutil.rmtree(tmp, ignore_errors=True)
    antal = max(1, int(indstillinger.get("backup_antal") or 1))
    for gammel in liste(indstillinger)[antal:]:
        if gammel.sti != behold:
            shutil.rmtree(gammel.sti, ignore_errors=True)


def daglig_backup(indstillinger):
    """Tager en backup, hvis der ikke allerede er taget en i dag."""
    i_dag = date.today()
    if any(b.tid.date() == i_dag for b in liste(indstillinger)):
        return None
    return tag_backup(indstillinger, "daglig")


### ----- test og gendannelse ------------------------------------------------

def test_backup(sti):
    """(ok, besked): kan backuppen gendannes uden fejl?"""
    sti = Path(sti)
    try:
        manifest = _laes_manifest(sti)
    except (OSError, ValueError) as fejl:
        return False, f"Manifest mangler eller er ødelagt ({fejl})."

    filer = manifest.get("filer") or {}
    if AKTIVE_FIL.name not in filer:
        return False, "Backuppen indeholder ikke medarbejderfilen."

    antal = {}
    for navn, forventet_hash in filer.items():
        fil = sti / navn
        if not fil.exists():
            return False, f"{navn} mangler i backuppen."
        if _sha256(fil) != forventet_hash:
            return False, f"{navn} er ændret, efter backuppen blev taget."
        try:
            data = json.loads(fil.read_text(encoding="utf-8") or "null")
        except ValueError as fejl:
            return False, f"{navn} er ikke gyldig JSON ({fejl})."
        if navn in (AKTIVE_FIL.name, ARKIV_FIL.name):
            if not isinstance(data, list):
                return False, f"{navn} indeholder ikke en liste af medarbejdere."
            try:
                for post in data:
                    Medarbejder.fra_dict(post)
            except Exception as fejl:
                return False, f"En medarbejder i {navn} kan ikke indlæses ({fejl})."
            antal[navn] = len(data)

    return True, (
        f"Kan gendannes: {antal.get(AKTIVE_FIL.name, 0)} aktive og "
        f"{antal.get(ARKIV_FIL.name, 0)} arkiverede sager, {len(filer)} filer."
    )


def gendan(sti, indstillinger):
    """Gendanner en backup. De nuværende data gemmes først som en ny backup."""
    ok, besked = test_backup(sti)
    if not ok:
        raise DataFejl(f"Backuppen kan ikke gendannes:\n{besked}")
    tag_backup(indstillinger, "foer-gendannelse")

    for navn in _laes_manifest(sti)["filer"]:
        maal = DATA_MAPPE / navn
        tmp = maal.with_name(maal.name + ".gendan.tmp")
        shutil.copy2(Path(sti) / navn, tmp)
        os.replace(tmp, maal)
    return besked


### ----- slettepolitik ------------------------------------------------------

def _plus_maaneder(dato, maaneder):
    aar, maaned = divmod(dato.month - 1 + maaneder, 12)
    aar += dato.year
    dag = min(dato.day, calendar.monthrange(aar, maaned + 1)[1])
    return date(aar, maaned + 1, dag)


def slettedato(medarbejder, maaneder):
    """Hvornår sagen må slettes: arkiveringsdato (ellers sidste arbejdsdag) + periode."""
    start = laes_iso_dato(medarbejder.arkiveret) or laes_iso_dato(
        medarbejder.fratraedelsesdato
    )
    return _plus_maaneder(start, int(maaneder)) if start else None


def udloebne(arkiv, maaneder, i_dag):
    """Arkiverede sager, hvis opbevaringsperiode er udløbet: [(medarbejder, slettedato)]."""
    resultat = []
    for m in arkiv:
        dato = slettedato(m, maaneder)
        if dato is not None and dato <= i_dag:
            resultat.append((m, dato))
    return resultat
