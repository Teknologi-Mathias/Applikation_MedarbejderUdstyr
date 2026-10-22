"""Sikkerhedskopier, kontrolleret gendannelse og slettepolitik.

Arbejder altid på den CENTRALE datamappe (aldrig offline-kopien).

- tag_backup()   kopierer alle datafiler til en tidsstemplet mappe med en
                 manifest-fil (SHA-256 pr. fil) og tester straks, at kopien
                 kan gendannes.
- test_backup()  kontrollerer en backup: filerne er uændrede, kan læses som
                 JSON, og alle sager kan indlæses af programmet.
- gendan()       tester backuppen, tager en backup af de nuværende data og
                 lægger derefter backuppen på plads.
- udloebne()     arkiverede sager, hvis opbevaringsperiode er udløbet.
"""
import calendar
import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app import VERSION
from app.domain.historik import nuvaerende_bruger
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.domain.opgave import laes_iso_dato
from app.infrastructure import stier
from app.repositories.fejl import DataFejl
from app.repositories.json.datakilde import Datakilde
from app.services.indstillinger_service import IndstillingerService

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"
# Sagsfiler og den type, der skal kunne indlæse dem (bruges ved test af backup).
_SAGSFILER = {
    stier.OFFBOARDING_AKTIVE: Medarbejder,
    stier.OFFBOARDING_ARKIV: Medarbejder,
    stier.ONBOARDING_AKTIVE: OnboardingForloeb,
    stier.ONBOARDING_ARKIV: OnboardingForloeb,
}


@dataclass
class BackupInfo:
    sti: Path
    tid: datetime
    aarsag: str
    bruger: str
    antal_aktive: int
    antal_arkiv: int
    antal_onboarding: int = 0


def _sha256(fil: Path) -> str:
    return hashlib.sha256(Path(fil).read_bytes()).hexdigest()


def _antal(fil: Path) -> int:
    try:
        data = json.loads(Path(fil).read_text(encoding="utf-8") or "[]")
        return len(data) if isinstance(data, list) else 0
    except (OSError, ValueError):
        return 0


def _plus_maaneder(dato: date, maaneder: int) -> date:
    aar, maaned = divmod(dato.month - 1 + maaneder, 12)
    aar += dato.year
    dag = min(dato.day, calendar.monthrange(aar, maaned + 1)[1])
    return date(aar, maaned + 1, dag)


def slettedato(sag, maaneder: int):
    """Hvornår sagen må slettes: arkiveringsdato (ellers startdato) + periode."""
    start = laes_iso_dato(sag.arkiveret) or laes_iso_dato(sag.startdato())
    return _plus_maaneder(start, int(maaneder)) if start else None


def udloebne(arkiv, maaneder: int, i_dag: date) -> list:
    """Arkiverede sager, hvis opbevaringsperiode er udløbet: [(sag, slettedato)]."""
    resultat = []
    for sag in arkiv:
        dato = slettedato(sag, maaneder)
        if dato is not None and dato <= i_dag:
            resultat.append((sag, dato))
    return resultat


class BackupService:
    def __init__(self, datakilde: Datakilde, indstillinger: IndstillingerService):
        self.datakilde = datakilde
        self.indstillinger = indstillinger

    @property
    def data_mappe(self) -> Path:
        return self.datakilde.central_mappe

    def mappe(self) -> Path:
        """Valgt backupmappe – ellers Backup/ i den centrale datamappe."""
        sti = str(self.indstillinger.hent().get("backup_mappe") or "").strip()
        return Path(sti) if sti else self.data_mappe / "Backup"

    ### ----- backup ---------------------------------------------------------

    def tag_backup(self, aarsag: str = "manuel") -> BackupInfo:
        """Tager og verificerer en backup. Kaster DataFejl, hvis den ikke kan gendannes."""
        mappe = self.mappe()
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
        for filnavn in stier.DATAFILER:
            kilde = self.data_mappe / filnavn
            if kilde.exists():
                shutil.copy2(kilde, tmp / filnavn)
                filer[filnavn] = _sha256(tmp / filnavn)
        manifest = {
            "tid": datetime.now().isoformat(timespec="seconds"),
            "aarsag": aarsag,
            "bruger": nuvaerende_bruger(),
            "version": VERSION,
            "filer": filer,
            "antal_aktive": _antal(tmp / stier.OFFBOARDING_AKTIVE),
            "antal_arkiv": _antal(tmp / stier.OFFBOARDING_ARKIV),
            "antal_onboarding": _antal(tmp / stier.ONBOARDING_AKTIVE)
            + _antal(tmp / stier.ONBOARDING_ARKIV),
        }
        (tmp / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=4),
                                    encoding="utf-8")
        tmp.rename(endelig)

        ok, besked = self.test_backup(endelig)
        if not ok:
            raise DataFejl(f"Sikkerhedskopien {endelig.name} kunne ikke verificeres:\n{besked}")
        info = self._info(endelig)
        self.ryd_gamle(behold=endelig)
        log.info("Backup taget: %s (%s)", endelig.name, besked)
        return info

    @staticmethod
    def _laes_manifest(sti: Path) -> dict:
        return json.loads((Path(sti) / MANIFEST).read_text(encoding="utf-8"))

    def _info(self, sti: Path) -> BackupInfo:
        manifest = self._laes_manifest(sti)
        try:
            tid = datetime.fromisoformat(manifest.get("tid", ""))
        except ValueError:
            tid = datetime.fromtimestamp(Path(sti).stat().st_mtime)
        return BackupInfo(
            Path(sti), tid, manifest.get("aarsag", ""), manifest.get("bruger", ""),
            manifest.get("antal_aktive", 0), manifest.get("antal_arkiv", 0),
            manifest.get("antal_onboarding", 0),
        )

    def liste(self) -> list[BackupInfo]:
        """Alle gyldige backups, nyeste først."""
        mappe = self.mappe()
        if not mappe.exists():
            return []
        resultat = []
        for sti in mappe.iterdir():
            if sti.is_dir() and not sti.name.endswith(".tmp") and (sti / MANIFEST).exists():
                try:
                    resultat.append(self._info(sti))
                except (OSError, ValueError):
                    log.warning("Ulæselig backup ignoreret: %s", sti)
        return sorted(resultat, key=lambda b: (b.tid, b.sti.name), reverse=True)

    def ryd_gamle(self, behold: Path | None = None) -> None:
        """Sletter de ældste backups ud over det tilladte antal (og .tmp-rester)."""
        mappe = self.mappe()
        for tmp in mappe.glob("*.tmp"):
            shutil.rmtree(tmp, ignore_errors=True)
        antal = max(1, int(self.indstillinger.hent().get("backup_antal") or 1))
        for gammel in self.liste()[antal:]:
            if gammel.sti != behold:
                shutil.rmtree(gammel.sti, ignore_errors=True)

    def daglig_backup(self) -> BackupInfo | None:
        """Tager en backup, hvis der ikke allerede er taget en i dag (kun online)."""
        if self.datakilde.offline:
            return None
        i_dag = date.today()
        if any(b.tid.date() == i_dag for b in self.liste()):
            return None
        return self.tag_backup("daglig")

    ### ----- test og gendannelse --------------------------------------------

    def test_backup(self, sti: Path) -> tuple[bool, str]:
        """(ok, besked): kan backuppen gendannes uden fejl?"""
        sti = Path(sti)
        try:
            manifest = self._laes_manifest(sti)
        except (OSError, ValueError) as fejl:
            return False, f"Manifest mangler eller er ødelagt ({fejl})."

        filer = manifest.get("filer") or {}
        if not filer:
            # En ny installation uden sager er gyldig – men en backup uden filer er ikke.
            return False, "Backuppen indeholder ingen datafiler."

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
            if navn in _SAGSFILER:
                if not isinstance(data, list):
                    return False, f"{navn} indeholder ikke en liste af sager."
                try:
                    for post in data:
                        _SAGSFILER[navn].fra_dict(post)
                except Exception as fejl:
                    return False, f"En sag i {navn} kan ikke indlæses ({fejl})."
                antal[navn] = len(data)

        onboarding = antal.get(stier.ONBOARDING_AKTIVE, 0) + antal.get(stier.ONBOARDING_ARKIV, 0)
        return True, (
            f"Kan gendannes: {antal.get(stier.OFFBOARDING_AKTIVE, 0)} aktive og "
            f"{antal.get(stier.OFFBOARDING_ARKIV, 0)} arkiverede offboardingsager, "
            f"{onboarding} onboardingforløb, {len(filer)} filer."
        )

    def gendan(self, sti: Path) -> str:
        """Gendanner en backup. De nuværende data gemmes først som en ny backup."""
        if self.datakilde.offline:
            raise DataFejl("Gendannelse kræver forbindelse til den centrale datamappe.")
        ok, besked = self.test_backup(sti)
        if not ok:
            raise DataFejl(f"Backuppen kan ikke gendannes:\n{besked}")
        self.tag_backup("foer-gendannelse")

        for navn in self._laes_manifest(sti)["filer"]:
            maal = self.data_mappe / navn
            tmp = maal.with_name(maal.name + ".gendan.tmp")
            shutil.copy2(Path(sti) / navn, tmp)
            os.replace(tmp, maal)
        log.warning("Backup gendannet fra %s", Path(sti).name)
        return besked
