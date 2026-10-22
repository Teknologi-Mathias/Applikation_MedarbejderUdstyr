"""Applikationens opsætning (composition root).

Her – og kun her – vælges konkrete implementeringer: hvilke repositories
services skal bruge. Brugerfladen får et færdigt Tjenester-objekt og kender
aldrig til JSON-filer eller databaser.

Når Supabase/PostgreSQL implementeres, er det denne fil, der skal vælge de
nye repositories (se app/infrastructure/database/README.md).
"""
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from app import session
from app.domain import historik
from app.domain.offboarding import Medarbejder
from app.domain.onboarding import OnboardingForloeb
from app.infrastructure import stier
from app.repositories.fejl import DataFejl
from app.repositories.json.bruger_repository import JsonBrugerRepository
from app.repositories.json.datakilde import Datakilde
from app.repositories.json.json_fil import tjek_skriveadgang
from app.repositories.json.opsaetning_repository import (
    JsonIndstillingRepository,
    JsonLokalFil,
    JsonPraeferenceRepository,
    JsonSkabelonRepository,
)
from app.repositories.json.sag_repository import JsonSagRepository
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService
from app.services.indstillinger_service import IndstillingerService
from app.services.lagring_service import LagringService
from app.services.offboarding_service import OffboardingService
from app.services.onboarding_service import OnboardingService
from app.services.paamindelser import PaamindelsesService
from app.services.rapport_service import RapportService
from app.services.skabelon_service import SkabelonService

log = logging.getLogger(__name__)

SAGSTYPER = {
    Medarbejder.PROCES: (Medarbejder, stier.OFFBOARDING_AKTIVE, stier.OFFBOARDING_ARKIV),
    OnboardingForloeb.PROCES: (OnboardingForloeb, stier.ONBOARDING_AKTIVE, stier.ONBOARDING_ARKIV),
}


@dataclass
class Tjenester:
    datakilde: Datakilde
    lagring: LagringService
    auth: AuthService
    indstillinger: IndstillingerService
    skabeloner: SkabelonService
    offboarding: OffboardingService
    onboarding: OnboardingService
    backup: BackupService
    paamindelser: PaamindelsesService
    rapporter: RapportService

    def modul(self, proces: str):
        return self.onboarding if proces == OnboardingForloeb.PROCES else self.offboarding


def byg_tjenester(central_mappe: Path = stier.CENTRAL_DATA_MAPPE,
                  lokal_mappe: Path = stier.LOKAL_MAPPE) -> Tjenester:
    """Bygger alle services. Mapperne kan angives (bruges af tests)."""
    historik.saet_brugerkilde(session.brugernavn)
    konfig = JsonLokalFil(lokal_mappe / stier.LAGRING_FIL.name)
    datakilde = Datakilde(central_mappe, lokal_mappe / stier.OFFLINE_MAPPE.name,
                          offline=bool(konfig.hent().get("offline")))
    sag_repos = {
        proces: JsonSagRepository(datakilde, sagstype, aktiv, arkiv)
        for proces, (sagstype, aktiv, arkiv) in SAGSTYPER.items()
    }
    indstillinger = IndstillingerService(
        JsonIndstillingRepository(datakilde),
        JsonPraeferenceRepository(lokal_mappe / stier.PRAEFERENCE_FIL.name),
    )
    return Tjenester(
        datakilde=datakilde,
        lagring=LagringService(datakilde, konfig, SAGSTYPER),
        auth=AuthService(JsonBrugerRepository(datakilde)),
        indstillinger=indstillinger,
        skabeloner=SkabelonService(JsonSkabelonRepository(datakilde)),
        offboarding=OffboardingService(sag_repos[Medarbejder.PROCES]),
        onboarding=OnboardingService(sag_repos[OnboardingForloeb.PROCES]),
        backup=BackupService(datakilde, indstillinger),
        paamindelser=PaamindelsesService(
            JsonLokalFil(lokal_mappe / stier.NOTIFIKATIONSLOG_FIL.name)
        ),
        rapporter=RapportService(),
    )


def klargoer(tjenester: Tjenester) -> None:
    """Kaldes én gang ved opstart (før log på). Kaster DataFejl ved problemer.

    Online: tjekker skriveadgang, kopierer evt. data fra %APPDATA% (≤ V0.5.1)
    og migrerer ældre dataformater – efter en backup.
    """
    datakilde = tjenester.datakilde
    if datakilde.offline:
        if not tjenester.lagring.offline_kopi_findes():
            raise DataFejl("Offline-tilstand er valgt, men der findes ingen lokal kopi.")
        log.info("Starter offline på %s", datakilde.offline_mappe)
        return
    try:
        tjek_skriveadgang(datakilde.central_mappe)
        _kopier_gamle_data(datakilde)
    except OSError as fejl:
        raise DataFejl(
            f"Programmet kan ikke skrive i datamappen:\n{datakilde.central_mappe}\n\n"
            f"({fejl})\n\n"
            "Ligger programmet i C:\\Program Files, kræver det "
            "administratorrettigheder. Flyt i stedet programmet til en mappe "
            "som C:\\IN-BASE. Ligger data på et netværksdrev, så tjek forbindelsen."
        ) from fejl
    _migrer(tjenester)
    tjenester.auth.klargoer()


def _kopier_gamle_data(datakilde: Datakilde) -> None:
    """Kopierer data fra %APPDATA% første gang (kun den færdige .exe)."""
    if not stier.ER_FROSSET or stier.GAMMEL_DATA_MAPPE == datakilde.central_mappe:
        return
    for filnavn in (stier.OFFBOARDING_AKTIVE, stier.OFFBOARDING_ARKIV):
        gammel = stier.GAMMEL_DATA_MAPPE / filnavn
        ny = datakilde.central_mappe / filnavn
        if gammel.exists() and not ny.exists():
            shutil.copy2(gammel, ny)


def _migrer(tjenester: Tjenester) -> None:
    repos = [tjenester.offboarding.repo, tjenester.onboarding.repo]
    if not any(repo.kraever_migrering() for repo in repos):
        return
    # Sikkerhedskopi FØR ældre data skrives i det nye format.
    info = tjenester.backup.tag_backup("foer-migrering")
    log.info("Backup før migrering: %s", info.sti)
    for repo in repos:
        repo.migrer()
