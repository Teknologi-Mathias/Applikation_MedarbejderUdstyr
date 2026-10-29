"""Central opdatering af klienten. Reglerne står i app/domain/opdatering.py.

- kontroller_skema(): kaldes ved opstart (før log på). Er databasen ældre end
  KRAEVET_SKEMA, kastes KompatibilitetsFejl – programmet må ikke skrive, fordi
  nye felter ellers forsvinder lydløst.
- find(): efter log på og hver 4. time (hovedvinduet). Hvilken version brugeren
  skal have, og om opdateringen er tvungen.
- hent(): henter og kontrollerer installeren (i baggrunden); en allerede hentet
  og kontrolleret fil genbruges.
- installer(): starter installeren – kun i den installerede app (ikke fra kildekoden).
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app import KRAEVET_SKEMA, __version__
from app.domain import opdatering as op
from app.infrastructure import opdatering as filer
from app.infrastructure import stier
from app.repositories.base import OpdateringRepository
from app.repositories.fejl import DataFejl, KompatibilitetsFejl, ValideringsFejl

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Status:
    krav: op.Krav
    maal: Optional[op.Udgivelse]       # None = ingen opdatering
    tvungen: bool


class OpdateringService:
    def __init__(self, repo: OpdateringRepository, mappe: Path, version: str = __version__,
                 kraevet_skema: int = KRAEVET_SKEMA, kan_installere: bool = stier.ER_FROSSET):
        self.repo = repo
        self.mappe = mappe
        self.version = version
        self.kraevet_skema = kraevet_skema
        self.kan_installere = kan_installere

    def kontroller_skema(self) -> op.Krav:
        krav = op.Krav.fra_dict(self.repo.krav())
        fejl = op.skema_fejl(krav, self.kraevet_skema)
        if fejl:
            log.error("Skemaversion %s < krævet %s", krav.skema, self.kraevet_skema)
            raise KompatibilitetsFejl(fejl)
        return krav

    def find(self, bruger: dict) -> Status:
        krav = self.kontroller_skema()
        udgivelser = self.repo.udgivelser()
        maal = op.vaelg_maal(self.version, udgivelser, str(bruger.get("id", "")),
                             bruger.get("kanal") or op.STABIL, krav.skema)
        tvungen = op.skal_tvinges(self.version, krav, maal, udgivelser)
        if maal or tvungen:
            log.info("Opdatering: aktuel %s, mål %s, tvungen %s", self.version,
                     maal.version if maal else "ingen", tvungen)
        return Status(krav, maal, tvungen)

    def filsti(self, udgivelse: op.Udgivelse) -> Path:
        return self.mappe / f"IN-BASE-Setup-v{udgivelse.version}.exe"

    def er_hentet(self, udgivelse: op.Udgivelse) -> bool:
        fil = self.filsti(udgivelse)
        return fil.is_file() and filer.sha256_fil(fil) == udgivelse.sha256

    def hent(self, udgivelse: op.Udgivelse,
             fremdrift: Optional[Callable[[int, int], None]] = None) -> Path:
        maal = self.filsti(udgivelse)
        if not self.er_hentet(udgivelse):
            try:
                filer.hent_fil(self.repo.download_url(udgivelse.sti), maal, udgivelse.sha256,
                               fremdrift)
            except filer.OpdateringsFejl as fejl:
                raise DataFejl(str(fejl)) from fejl
        filer.ryd_gamle(self.mappe, {maal.name})
        return maal

    def installer(self, installer: Path) -> None:
        if not self.kan_installere:
            raise ValideringsFejl("Opdateringer installeres kun i den installerede app – "
                                  "ikke når IN-BASE køres fra kildekoden.")
        filer.start_installer(installer, self.mappe / "installer.log")

    def rapporter(self) -> None:
        """Melder den kørende version (Indstillinger → Brugere). Fejl stopper intet."""
        try:
            self.repo.rapporter(self.version)
        except DataFejl:
            log.warning("Programversionen kunne ikke meldes", exc_info=True)
